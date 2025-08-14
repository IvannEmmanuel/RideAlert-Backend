from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.utils.background_loader import background_loader
import math
import os

router = APIRouter()

# Simple toggle for ground truth comparison - set to True for testing, False for production
ENABLE_GROUND_TRUTH_COMPARISON = True  # Change to False for production


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
    WlsPositionXEcefMeters: float
    WlsPositionYEcefMeters: float
    WlsPositionZEcefMeters: float
    # Ground truth fields - only used when ENABLE_GROUND_TRUTH_COMPARISON is True
    LatitudeDegrees_gt: float = None
    LongitudeDegrees_gt: float = None


@router.get("/predict/status")
async def get_prediction_status():
    """Check if the prediction service is ready"""
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

        input_data = request.dict()
        input_data['SignalQuality'] = input_data['Cn0DbHz'] * \
            math.sin(math.radians(input_data['SvElevationDegrees']))
        input_data['WLS_Distance'] = math.sqrt(
            input_data['WlsPositionXEcefMeters']**2 +
            input_data['WlsPositionYEcefMeters']**2 +
            input_data['WlsPositionZEcefMeters']**2
        )

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

        # Basic response
        response_data = {
            "prediction": prediction,
            "wls_latitude": wls_lat,
            "wls_longitude": wls_lng,
            "corrected_latitude": corrected_lat,
            "corrected_longitude": corrected_lng,
            "model_status": "ready"
        }

        # Add ground truth comparison ONLY if enabled and data provided
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
