import inspect
from fastapi import APIRouter, HTTPException
import asyncio
import time
import os
import math
from bson import ObjectId
from datetime import datetime
from typing import Optional
from app.database import db
from app.utils.tracking_logs import insert_gps_log
from app.utils.background_loader import background_loader
from pydantic import BaseModel, Field, root_validator
import time as _time
from shapely.geometry import LineString, Point
import threading

# Route cache and lock
_route_cache = {"line": None, "last_refresh": 0}
_route_cache_lock = threading.Lock()


async def get_route_line_from_db(route_id: Optional[str] = None):
    """
    Load and cache the route LineString from MongoDB (db.declared_routes) for a specific route_id, refreshing every hour.
    Returns a Shapely LineString or None if not available.
    """
    global _route_cache
    now = _time.time()
    cache_key = route_id if route_id else "default"
    with _route_cache_lock:
        cache_entry = _route_cache.get(cache_key)
        if cache_entry and cache_entry["line"] is not None and now - cache_entry["last_refresh"] < 3600:
            return cache_entry["line"]
        try:
            query = {}
            if route_id:
                if ObjectId.is_valid(route_id):
                    query["_id"] = ObjectId(route_id)
                else:
                    query["_id"] = route_id
            else:
                # fallback: no route_id provided
                print("⚠️ No route_id provided to get_route_line_from_db.")
                _route_cache[cache_key] = {"line": None, "last_refresh": now}
                return None
            route_doc = db.declared_routes.find_one(query)
            if not route_doc:
                print(f"⚠️ No route found for query: {query}")
                _route_cache[cache_key] = {"line": None, "last_refresh": now}
                return None
            try:
                features = route_doc["route_geojson"].get("features", [])
                line_coords = None
                for feature in features:
                    geom = feature.get("geometry", {})
                    if geom.get("type") == "LineString" and "coordinates" in geom:
                        line_coords = geom["coordinates"]
                        break
                if not line_coords or not isinstance(line_coords, list):
                    print("⚠️ No LineString coordinates found in route_geojson.")
                    _route_cache[cache_key] = {
                        "line": None, "last_refresh": now}
                    return None
                line = LineString([(lon, lat) for lon, lat in line_coords])
                _route_cache[cache_key] = {"line": line, "last_refresh": now}
                print(
                    f"✅ Loaded geomap from DB with {len(line_coords)} points for route_id={route_id}")
                return line
            except Exception as e:
                print(f"⚠️ Error parsing route_geojson: {e}")
                _route_cache[cache_key] = {"line": None, "last_refresh": now}
                return None
        except Exception as e:
            print(f"⚠️ Error loading route from DB: {e}")
            _route_cache[cache_key] = {"line": None, "last_refresh": now}
            return None


def snap_to_route(lat: float, lon: float, route: LineString):
    if route is None:
        return lat, lon
    point = Point(lon, lat)
    nearest_point = route.interpolate(route.project(point))
    return nearest_point.y, nearest_point.x


router = APIRouter()

# Configuration variables for ML prediction logging
ENABLE_GROUND_TRUTH_COMPARISON = False  # Change to False for production


class PredictionRequest(BaseModel):
    # Required identifiers - these should come from the IoT device/client
    device_id: str   # Unique identifier for the IoT device
    fleet_id: str
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
    # New: accept speed in meters per second from IoT as 'speedMps'.
    # For backward compatibility, still accept legacy 'speed' (kph) via alias to Speed.
    # We'll normalize to m/s for the ML feature 'Speed'.
    SpeedMps: Optional[float] = Field(None, alias="speedMps")
    # Legacy kph input; optional now. If provided, we'll convert to m/s.
    Speed: Optional[float] = Field(None, alias="speed")

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

    class Config:
        # Allow either field name ('Speed') or alias ('speed') in input payloads
        allow_population_by_field_name = True

    # Accept capitalized keys from devices (e.g., "Speed" or "SpeedMps") by normalizing
    @root_validator(pre=True)
    def normalize_speed_keys(cls, values):
        # Map "Speed" -> "speed" if alias not present
        if "speed" not in values and "Speed" in values:
            values["speed"] = values["Speed"]
        # Map "SpeedMps" -> "speedMps" if alias not present
        if "speedMps" not in values and "SpeedMps" in values:
            values["speedMps"] = values["SpeedMps"]
        return values


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
    start_time = time.time()

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

        # Prepare input data with the ECEF coordinates; keep field names (e.g., 'Speed') for ML features.
        # We'll compute 'Speed' in meters per second, preferring 'speedMps' if provided,
        # otherwise converting legacy 'speed' (kph) to m/s.
        input_data = request.dict()

        # Use the converted or provided ECEF coordinates
        input_data['WlsPositionXEcefMeters'] = wls_x
        input_data['WlsPositionYEcefMeters'] = wls_y
        input_data['WlsPositionZEcefMeters'] = wls_z

        # Normalize speed to meters per second for ML feature 'Speed'
        speed_mps: Optional[float] = None
        try:
            if request.SpeedMps is not None:
                speed_mps = float(request.SpeedMps)
            elif request.Speed is not None:
                # Legacy kph -> m/s
                speed_mps = float(request.Speed) / 3.6
        except (TypeError, ValueError):
            speed_mps = None

        # Default to 0.0 if not provided to avoid model errors
        if speed_mps is None:
            speed_mps = 0.0

        # ML artifacts expect feature named 'Speed' -> now defined as m/s
        input_data['SpeedMps'] = speed_mps

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

        # --- Scalable route snapping integration ---
        snapped_lat, snapped_lng = corrected_lat, corrected_lng
        snapped = False
        try:
            # Try to get route_id from payload, else from vehicle entity
            route_id = getattr(request, "route_id", None)
            if not route_id:
                # Look up vehicle by device_id
                vehicle = db.vehicles.find_one(
                    {"device_id": request.device_id})
                if vehicle:
                    route_id = vehicle.get("route_id")
            route_line = await get_route_line_from_db(route_id=route_id)
            if route_line:
                snapped_lat, snapped_lng = snap_to_route(
                    corrected_lat, corrected_lng, route_line)
                snapped = True
                print(
                    f"✅ Snapped to route: ({snapped_lat}, {snapped_lng}) [route_id={route_id}]")
            else:
                print("⚠️ No route available, using raw corrected coordinates.")
        except Exception as e:
            print(f"⚠️ Route snapping failed: {e}")

        # Calculate response time
        response_time_ms = (time.time() - start_time) * 1000

        # Minimal response - only corrected coordinates

        response_data = {
            "latitude": snapped_lat,
            "longitude": snapped_lng,
            "snapped": snapped
        }

        # Broadcast prediction to WebSocket subscribers
        try:
            # Import here to avoid circular imports
            from app.routes.websockets import broadcast_prediction

            # Create a background task to broadcast (so it doesn't slow down the HTTP response)
            asyncio.create_task(
                broadcast_prediction(
                    device_id=request.device_id,
                    vehicle_id=None,  # let websocket handler resolve vehicle _id from device_id
                    fleet_id=request.fleet_id,
                    prediction_data=response_data,
                    # Broadcast raw IoT payload using aliases (e.g., speedMps)
                    ml_request_data=request.dict(by_alias=True),
                    response_time_ms=response_time_ms
                )
            )
            # print(f"📡 Broadcasting vehicle location update from {request.vehicle_id}")
        except Exception as e:
            print(f"⚠️ Warning: Failed to broadcast prediction: {e}")

        # Update vehicle location in the vehicles collection with snapped coordinates and last_updated timestamp
        try:
            dev_id = str(request.device_id).strip()
            filter_query = {"$or": [{"device_id": dev_id}]}
            if ObjectId.is_valid(dev_id):
                filter_query["$or"].append({"device_id": ObjectId(dev_id)})

            update_result = db.vehicles.update_one(
                filter_query,
                {
                    "$set": {
                        "location": {
                            "latitude": float(snapped_lat),
                            "longitude": float(snapped_lng),
                            # Unix timestamp in ms
                            "last_updated": int(time.time() * 1000)
                        }
                    }
                }
            )

            if update_result.matched_count > 0:
                print(
                    f"🚗 Vehicle {request.device_id} snapped location updated: lat={snapped_lat:.6f}, lng={snapped_lng:.6f}")
            else:
                print(
                    f"⚠️ Warning: Vehicle {request.device_id} not found in vehicles collection")

        except Exception as e:
            print(f"⚠️ Warning: Failed to update vehicle location: {e}")

        # Log SUCCESSFUL ML prediction to tracking logs
        # This only executes if prediction was successful (no exceptions thrown above)
        try:
            # For logging, use original raw altitude (not corrected since ML doesn't correct altitude)
            original_altitude = request.raw_altitude if request.raw_altitude is not None else 0.0

            corrected_coordinates = {
                "latitude": corrected_lat,
                "longitude": corrected_lng,
                "altitude": original_altitude  # Use original altitude, not corrected
            }

            # Add moved (snapped) point based on declared routes
            moved_point = {
                "latitude": snapped_lat,
                "longitude": snapped_lng
            }

            # Convert request to dict using aliases to store the original IoT payload (e.g., speedMps)
            ml_request_data = request.dict(by_alias=True)
            # Copy ECEF values into the iot_payload for full self-containment
            ml_request_data["WlsPositionXEcefMeters"] = wls_x
            ml_request_data["WlsPositionYEcefMeters"] = wls_y
            ml_request_data["WlsPositionZEcefMeters"] = wls_z

            # Prepare ECEF coordinates used by backend for logging
            ecef_used = {
                "WlsPositionXEcefMeters": wls_x,
                "WlsPositionYEcefMeters": wls_y,
                "WlsPositionZEcefMeters": wls_z,
            }

            # Insert comprehensive tracking log for this SUCCESSFUL prediction
            log_id = insert_gps_log(
                db=db,
                device_id=request.device_id,
                fleet_id=request.fleet_id,
                ml_request_data=ml_request_data,
                corrected_coordinates=corrected_coordinates,
                ecef_coordinates=ecef_used,
                moved_point=moved_point
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
