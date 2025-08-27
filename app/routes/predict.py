from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.utils.background_loader import background_loader
from app.utils.tracking_logs import insert_gps_log
from app.database import db
from typing import Optional
from datetime import datetime
import math
import os

router = APIRouter()

# Configuration variables for ML prediction logging
# These will be updated when integrating with actual vehicle/device management
# Will be replaced with actual vehicle ID from request
DEFAULT_VEHICLE_ID = "vehicle_001"
# Will be replaced with actual IoT device ID from request
DEFAULT_DEVICE_ID = "iot_device_001"

ENABLE_GROUND_TRUTH_COMPARISON = False  # Change to False for production


class PredictionRequest(BaseModel):
    Cn0DbHz: float
    Svid: int
    SvElevationDegrees: float
    SvAzimuthDegrees: float
    IMU_MessageType: str
    MeasurementX: float
    MeasurementY: float
    MeasurementZ: float
    BiasX: float
    BiasY: float
    BiasZ: float

    # Option 1: Provide WLS ECEF coordinates directly (existing format)
    WlsPositionXEcefMeters: Optional[float] = None
    WlsPositionYEcefMeters: Optional[float] = None
    WlsPositionZEcefMeters: Optional[float] = None

    # Option 2: Provide raw coordinates for automatic WLS conversion
    raw_latitude: Optional[float] = None
    raw_longitude: Optional[float] = None
    # altitude in meters above WGS84 ellipsoid
    raw_altitude: Optional[float] = None

    # only used when ENABLE_GROUND_TRUTH_COMPARISON is True
    LatitudeDegrees_gt: Optional[float] = None
    LongitudeDegrees_gt: Optional[float] = None


def convert_latlon_to_ecef(latitude: float, longitude: float, altitude: float):
    """
    Convert latitude, longitude, altitude to ECEF coordinates

    Args:
        latitude: Latitude in decimal degrees
        longitude: Longitude in decimal degrees  
        altitude: Altitude in meters above WGS84 ellipsoid

    Returns:
        tuple: (x_ecef, y_ecef, z_ecef) in meters
    """
    from pyproj import Transformer

    # Transform from WGS84 lat/lng/alt to ECEF
    transformer = Transformer.from_crs(
        "EPSG:4326",  # WGS84 (latitude, longitude, altitude)
        "EPSG:4978",  # ECEF (Earth-Centered, Earth-Fixed)
        always_xy=True  # longitude, latitude order for input
    )

    # Transform coordinates (note: pyproj expects lon, lat, alt order)
    x_ecef, y_ecef, z_ecef = transformer.transform(
        longitude, latitude, altitude)

    return x_ecef, y_ecef, z_ecef


@router.get("/predict/status")
async def get_prediction_status():
    """Check if the prediction service ready"""
    status = background_loader.get_status()
    return status


@router.post("/predict")
async def predict(request: PredictionRequest):
    try:
        # Check if models are ready
        status = background_loader.get_status()

        if status["status"] == "error":
            raise HTTPException(
                status_code=503,
                detail=f"Models failed to load: {status.get('error', 'Unknown error')}"
            )

        if status["status"] == "loading":
            raise HTTPException(
                status_code=202,  # Accepted, but processing
                detail="Models are still being downloaded and loaded in the background. Please try again in a moment."
            )

        if status["status"] == "not_started":
            # Fallback: start loading if somehow not started
            background_loader.start_background_loading()
            raise HTTPException(
                status_code=202,
                detail="Model loading initiated. Please try again in a few minutes."
            )

        # Get the ML manager (should be ready now)
        ml_manager = background_loader.get_ml_manager()
        if not ml_manager:
            raise HTTPException(
                status_code=503,
                detail="Models are not ready yet. Please try again."
            )

        # Validate input: either WLS ECEF coordinates OR raw lat/lng/alt must be provided
        wls_provided = all([
            request.WlsPositionXEcefMeters is not None,
            request.WlsPositionYEcefMeters is not None,
            request.WlsPositionZEcefMeters is not None
        ])

        raw_provided = all([
            request.raw_latitude is not None,
            request.raw_longitude is not None,
            request.raw_altitude is not None
        ])

        if not wls_provided and not raw_provided:
            raise HTTPException(
                status_code=400,
                detail="Either WLS ECEF coordinates (WlsPositionXEcefMeters, WlsPositionYEcefMeters, WlsPositionZEcefMeters) OR raw coordinates (raw_latitude, raw_longitude, raw_altitude) must be provided."
            )

        if wls_provided and raw_provided:
            raise HTTPException(
                status_code=400,
                detail="Provide either WLS ECEF coordinates OR raw coordinates, not both."
            )

        # Convert raw coordinates to ECEF if needed
        if raw_provided:
            try:
                wls_x, wls_y, wls_z = convert_latlon_to_ecef(
                    request.raw_latitude,
                    request.raw_longitude,
                    request.raw_altitude
                )
            except Exception as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Error converting raw coordinates to ECEF: {str(e)}"
                )
        else:
            # Use provided WLS ECEF coordinates
            wls_x = request.WlsPositionXEcefMeters
            wls_y = request.WlsPositionYEcefMeters
            wls_z = request.WlsPositionZEcefMeters

        # Prepare input data with the ECEF coordinates
        input_data = request.dict()

        # Use the converted or provided ECEF coordinates
        input_data['WlsPositionXEcefMeters'] = wls_x
        input_data['WlsPositionYEcefMeters'] = wls_y
        input_data['WlsPositionZEcefMeters'] = wls_z

        # Calculate derived features
        input_data['SignalQuality'] = input_data['Cn0DbHz'] * \
            math.sin(math.radians(input_data['SvElevationDegrees']))
        input_data['WLS_Distance'] = math.sqrt(wls_x**2 + wls_y**2 + wls_z**2)

        # Models are loaded, prediction should be fast
        prediction = ml_manager.predict(input_data)

        # Get WLS latitude and longitude from input (ground truth columns are not present, so use WLS ECEF)
        # Use pyproj to convert ECEF to lat/lon
        from pyproj import Transformer
        transformer = Transformer.from_crs(
            "EPSG:4978", "EPSG:4326", always_xy=True)
        wls_lng, wls_lat, _ = transformer.transform(
            input_data['WlsPositionXEcefMeters'],
            input_data['WlsPositionYEcefMeters'],
            input_data['WlsPositionZEcefMeters']
        )
        corrected_lat = wls_lat + prediction[0]
        corrected_lng = wls_lng + prediction[1]

        # Determine altitude (use raw altitude if provided, otherwise estimate from ECEF)
        corrected_altitude = request.raw_altitude if request.raw_altitude is not None else 0.0

        # Minimal response - only corrected coordinates
        response_data = {
            "latitude": corrected_lat,
            "longitude": corrected_lng
        }

        # Log SUCCESSFUL ML prediction to tracking logs
        # This only executes if prediction was successful (no exceptions thrown above)
        try:
            corrected_coordinates = {
                "latitude": corrected_lat,
                "longitude": corrected_lng,
                "altitude": corrected_altitude
            }

            # Convert request to dict for logging
            ml_request_data = request.dict()

            # Insert comprehensive tracking log for this SUCCESSFUL prediction
            log_id = insert_gps_log(
                db=db,
                vehicle_id=DEFAULT_VEHICLE_ID,  # Will be replaced with actual vehicle ID
                device_id=DEFAULT_DEVICE_ID,   # Will be replaced with actual device ID
                ml_request_data=ml_request_data,
                corrected_coordinates=corrected_coordinates
            )

            print(f"✅ Successful ML prediction logged with ID: {log_id}")

        except Exception as e:
            # Don't fail the prediction response if logging fails, but log the error
            print(f"⚠️ Warning: Failed to log successful ML prediction: {e}")
            # Prediction still succeeds, just logging failed        # Add ground truth comparison ONLY if enabled and data provided
        if ENABLE_GROUND_TRUTH_COMPARISON and request.LatitudeDegrees_gt is not None and request.LongitudeDegrees_gt is not None:
            gt_lat = request.LatitudeDegrees_gt
            gt_lng = request.LongitudeDegrees_gt

            # Simple error calculation
            lat_error_m = abs(corrected_lat - gt_lat) * 111320
            lng_error_m = abs(corrected_lng - gt_lng) * 111320 * \
                math.cos(math.radians(abs(corrected_lat)))
            total_error_m = math.sqrt(lat_error_m**2 + lng_error_m**2)

            # Add simple comparison to response
            response_data["testing_analysis"] = {
                "ground_truth_lat": gt_lat,
                "ground_truth_lng": gt_lng,
                "error_meters": round(total_error_m, 2)
            }

        return response_data
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        error_msg = str(e)
        raise HTTPException(
            status_code=500, detail=f"Prediction error: {error_msg}")
