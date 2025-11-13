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
from pydantic import BaseModel, Field, root_validator, ValidationError
import time as _time
from shapely.geometry import LineString, Point
import threading
from app.routes.websockets import broadcast_vehicle_location_update
import json
import base64
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

# ===================== ENCRYPTION CONFIGURATION =====================
# IMPORTANT: Keep this key in sync with IoT device
# Must be exactly 32 bytes for AES-256
ENCRYPTION_KEY = b'MySecureKey12345MySecureKey12345'


def decrypt_data(encrypted_payload: str) -> dict:
    """
    Decrypt AES-256-CBC encrypted data from IoT device

    Args:
        encrypted_payload: Base64-encoded string containing IV + encrypted data

    Returns:
        dict: Decrypted JSON payload

    Raises:
        ValueError: If decryption fails
    """
    try:
        # Decode from base64
        combined = base64.b64decode(encrypted_payload)

        # Extract IV (first 16 bytes) and encrypted data (rest)
        iv = combined[:16]
        encrypted_data = combined[16:]

        # Decrypt using AES-256-CBC
        cipher = AES.new(ENCRYPTION_KEY, AES.MODE_CBC, iv)
        decrypted_padded = cipher.decrypt(encrypted_data)

        # Remove PKCS7 padding
        decrypted = unpad(decrypted_padded, AES.block_size)

        # Parse JSON
        payload = json.loads(decrypted.decode('utf-8'))

        print(f"✅ Successfully decrypted payload")
        return payload

    except Exception as e:
        print(f"❌ Decryption error: {e}")
        raise ValueError(f"Failed to decrypt payload: {str(e)}")


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
ENABLE_GROUND_TRUTH_COMPARISON = False

# Toggle for route snapping (1 = enabled, 0 = disabled)
ENABLE_ROUTE_SNAPPING = 0


class EncryptedRequest(BaseModel):
    """Wrapper for encrypted IoT payload"""
    encrypted_data: str


class PredictionRequest(BaseModel):
    # Required identifiers
    device_id: str
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
    SpeedMps: Optional[float] = Field(None, alias="speedMps")
    Speed: Optional[float] = Field(None, alias="speed")

    # Option 1: WLS ECEF coordinates
    WlsPositionXEcefMeters: Optional[float] = None
    WlsPositionYEcefMeters: Optional[float] = None
    WlsPositionZEcefMeters: Optional[float] = None

    # Option 2: Raw coordinates for automatic conversion
    raw_latitude: Optional[float] = None
    raw_longitude: Optional[float] = None
    raw_altitude: Optional[float] = None

    # Ground truth (testing only)
    LatitudeDegrees_gt: Optional[float] = None
    LongitudeDegrees_gt: Optional[float] = None

    class Config:
        allow_population_by_field_name = True

    @root_validator(pre=True)
    def normalize_speed_keys(cls, values):
        if "speed" not in values and "Speed" in values:
            values["speed"] = values["Speed"]
        if "speedMps" not in values and "SpeedMps" in values:
            values["speedMps"] = values["SpeedMps"]
        return values


def convert_latlon_to_ecef(latitude: float, longitude: float, altitude: float):
    """
    Convert latitude, longitude, altitude to ECEF coordinates
    """
    from pyproj import Transformer

    transformer = Transformer.from_crs(
        "EPSG:4326",
        "EPSG:4978",
        always_xy=True
    )

    x_ecef, y_ecef, z_ecef = transformer.transform(
        longitude, latitude, altitude)

    return x_ecef, y_ecef, z_ecef


@router.get("/predict/status")
async def get_prediction_status():
    """Check if the prediction service is ready"""
    status = background_loader.get_status()
    return status


@router.post("/predict")
async def predict(request: EncryptedRequest):
    """
    Handle sensor data from IoT device (encrypted only)

    Accepts:
    - {"encrypted_data": "base64_string"}
    """
    start_time = time.time()

    try:
        # ===================== DECRYPTION STEP =====================
        print("🔐 Attempting to decrypt IoT payload...")
        try:
            decrypted_dict = decrypt_data(request.encrypted_data)
            print(
                f"✅ Decryption successful. Payload keys: {list(decrypted_dict.keys())}")
            prediction_request = PredictionRequest(**decrypted_dict)
        except ValueError as e:
            # Covers decryption failures, bad padding, invalid base64/IV, or JSON parse issues
            raise HTTPException(
                status_code=400,
                detail=f"Decryption failed: {str(e)}"
            )
        except ValidationError as e:
            # Decrypted payload parsed but failed schema validation
            raise HTTPException(
                status_code=422,
                detail=e.errors()
            )

        # ===================== REST OF PREDICTION LOGIC =====================
        # Check if models are ready
        status = background_loader.get_status()

        if status["status"] == "error":
            raise HTTPException(
                status_code=503,
                detail=f"Models failed to load: {status.get('error', 'Unknown error')}"
            )

        if status["status"] == "loading":
            raise HTTPException(
                status_code=202,
                detail="Models are still being downloaded and loaded in the background. Please try again in a moment."
            )

        if status["status"] == "not_started":
            background_loader.start_background_loading()
            raise HTTPException(
                status_code=202,
                detail="Model loading initiated. Please try again in a few minutes."
            )

        ml_manager = background_loader.get_ml_manager()
        if not ml_manager:
            raise HTTPException(
                status_code=503,
                detail="Models are not ready yet. Please try again."
            )

        # Validate position coordinates
        wls_provided = all([
            prediction_request.WlsPositionXEcefMeters is not None,
            prediction_request.WlsPositionYEcefMeters is not None,
            prediction_request.WlsPositionZEcefMeters is not None
        ])

        raw_provided = all([
            prediction_request.raw_latitude is not None,
            prediction_request.raw_longitude is not None,
            prediction_request.raw_altitude is not None
        ])

        if not wls_provided and not raw_provided:
            raise HTTPException(
                status_code=400,
                detail="Either WLS ECEF coordinates or raw coordinates (raw_latitude, raw_longitude, raw_altitude) must be provided."
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
                    prediction_request.raw_latitude,
                    prediction_request.raw_longitude,
                    prediction_request.raw_altitude
                )
            except Exception as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Error converting raw coordinates to ECEF: {str(e)}"
                )
        else:
            wls_x = prediction_request.WlsPositionXEcefMeters
            wls_y = prediction_request.WlsPositionYEcefMeters
            wls_z = prediction_request.WlsPositionZEcefMeters

        # Prepare input data
        input_data = prediction_request.dict()
        input_data['WlsPositionXEcefMeters'] = wls_x
        input_data['WlsPositionYEcefMeters'] = wls_y
        input_data['WlsPositionZEcefMeters'] = wls_z

        # Normalize speed to m/s
        speed_mps: Optional[float] = None
        try:
            if prediction_request.SpeedMps is not None:
                speed_mps = float(prediction_request.SpeedMps)
            elif prediction_request.Speed is not None:
                speed_mps = float(prediction_request.Speed) / 3.6
        except (TypeError, ValueError):
            speed_mps = None

        if speed_mps is None:
            speed_mps = 0.0

        input_data['SpeedMps'] = speed_mps

        # Calculate derived features
        input_data['SignalQuality'] = input_data['Cn0DbHz'] * \
            math.sin(math.radians(input_data['SvElevationDegrees']))
        input_data['WLS_Distance'] = math.sqrt(wls_x**2 + wls_y**2 + wls_z**2)

        # Get ML prediction
        prediction = ml_manager.predict(input_data)

        # Convert ECEF back to lat/lon
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

        # Route snapping (toggle-able)
        snapped_lat, snapped_lng = corrected_lat, corrected_lng
        snapped = False
        if ENABLE_ROUTE_SNAPPING:
            try:
                route_id = getattr(prediction_request, "route_id", None)
                if not route_id:
                    vehicle = db.vehicles.find_one(
                        {"device_id": prediction_request.device_id})
                    route_id = None
                    if vehicle:
                        current_route = vehicle.get("current_route")
                        if current_route and "route_id" in current_route:
                            route_id = current_route["route_id"]
                        if not route_id:
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
        else:
            print(
                "ℹ️ Route snapping disabled (ENABLE_ROUTE_SNAPPING=0); using corrected coordinates.")

        response_time_ms = (time.time() - start_time) * 1000

        response_data = {
            "latitude": snapped_lat,
            "longitude": snapped_lng,
            "snapped": snapped
        }

        # Update vehicle location
        try:
            dev_id = str(prediction_request.device_id).strip()
            filter_query = {"$or": [{"device_id": dev_id}]}
            if ObjectId.is_valid(dev_id):
                filter_query["$or"].append({"device_id": ObjectId(dev_id)})

            vehicle = db.vehicles.find_one(filter_query)

            if vehicle:
                vehicle_id = str(vehicle["_id"])

                update_result = db.vehicles.update_one(
                    filter_query,
                    {
                        "$set": {
                            "location": {
                                "latitude": float(snapped_lat),
                                "longitude": float(snapped_lng)
                            }
                        }
                    }
                )

                if update_result.matched_count > 0:
                    print(
                        f"🚗 Vehicle {prediction_request.device_id} snapped location updated: lat={snapped_lat:.6f}, lng={snapped_lng:.6f}")

                    await broadcast_vehicle_location_update(
                        vehicle_id=vehicle_id,
                        latitude=float(snapped_lat),
                        longitude=float(snapped_lng),
                        device_id=prediction_request.device_id
                    )
            else:
                print(
                    f"⚠️ Warning: Vehicle {prediction_request.device_id} not found in vehicles collection")

        except Exception as e:
            print(f"⚠️ Warning: Failed to update vehicle location: {e}")

        # Log successful prediction
        try:
            original_altitude = prediction_request.raw_altitude if prediction_request.raw_altitude is not None else 0.0

            corrected_coordinates = {
                "latitude": corrected_lat,
                "longitude": corrected_lng,
                "altitude": original_altitude
            }

            moved_point = {
                "latitude": snapped_lat,
                "longitude": snapped_lng
            }

            ml_request_data = prediction_request.dict(by_alias=True)
            ml_request_data["WlsPositionXEcefMeters"] = wls_x
            ml_request_data["WlsPositionYEcefMeters"] = wls_y
            ml_request_data["WlsPositionZEcefMeters"] = wls_z

            ecef_used = {
                "WlsPositionXEcefMeters": wls_x,
                "WlsPositionYEcefMeters": wls_y,
                "WlsPositionZEcefMeters": wls_z,
            }

            log_id = insert_gps_log(
                db=db,
                device_id=prediction_request.device_id,
                fleet_id=prediction_request.fleet_id,
                ml_request_data=ml_request_data,
                corrected_coordinates=corrected_coordinates,
                ecef_coordinates=ecef_used,
                moved_point=moved_point
            )

            print(f"✅ Successful ML prediction logged with ID: {log_id}")
            print(
                f"   📊 Stored in DB: device_id={prediction_request.device_id}, fleet_id={prediction_request.fleet_id}")
            print(
                f"   📊 Corrected coordinates: lat={corrected_lat:.6f}, lng={corrected_lng:.6f}")

        except Exception as e:
            print(f"⚠️ Warning: Failed to log successful ML prediction: {e}")

        if ENABLE_GROUND_TRUTH_COMPARISON and prediction_request.LatitudeDegrees_gt is not None and prediction_request.LongitudeDegrees_gt is not None:
            gt_lat = prediction_request.LatitudeDegrees_gt
            gt_lng = prediction_request.LongitudeDegrees_gt

            lat_error_m = abs(corrected_lat - gt_lat) * 111320
            lng_error_m = abs(corrected_lng - gt_lng) * 111320 * \
                math.cos(math.radians(abs(corrected_lat)))
            total_error_m = math.sqrt(lat_error_m**2 + lng_error_m**2)

            response_data["testing_analysis"] = {
                "ground_truth_lat": gt_lat,
                "ground_truth_lng": gt_lng,
                "error_meters": round(total_error_m, 2)
            }

        return response_data

    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e)
        print(f"❌ Prediction error: {error_msg}")
        raise HTTPException(
            status_code=500, detail=f"Prediction error: {error_msg}")
