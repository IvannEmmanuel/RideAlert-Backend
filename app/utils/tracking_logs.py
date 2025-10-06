from datetime import datetime
from bson import ObjectId
import time


def insert_gps_log(db, device_id: str, fleet_id: str, ml_request_data: dict, corrected_coordinates: dict, ecef_coordinates: dict | None = None):
    """
    Insert ML prediction log into MongoDB Atlas with complete sensor data structure

    Expected Payload Before Prediction (Real NEO-6M GPS Structure):
    {
        "fleet_id": "fleet_001",          # Fleet identifier
        "device_id": "device_001",        # IoT device identifier
        "Cn0DbHz": 45.2,                  # Real NEO-6M SNR (Signal-to-Noise Ratio) 
        "Svid": 12,                       # Real satellite ID (PRN number) from GPGSV
        "SvElevationDegrees": 65,         # Real satellite elevation from NEO-6M GPGSV
        "SvAzimuthDegrees": 285,          # Real satellite azimuth from NEO-6M GPGSV  
        "IMU_MessageType": "UncalAccel",  # Accelerometer data type
        "MeasurementX": 0.7854004,        # Real accelerometer X-axis (rounded to 7 decimals)
        "MeasurementY": -0.6618652,       # Real accelerometer Y-axis (rounded to 7 decimals)
        "MeasurementZ": -0.06811523,      # Real accelerometer Z-axis (rounded to 7 decimals)
        "BiasX": 0.0,                     # X-axis bias (typically 0.0)
        "BiasY": 0.0,                     # Y-axis bias (typically 0.0)
        "BiasZ": 0.0,                     # Z-axis bias (typically 0.0)
        "raw_latitude": 8.585581,         # Raw GPS latitude from NEO-6M
        "raw_longitude": 124.769386,      # Raw GPS longitude from NEO-6M
        "raw_altitude": 3.0,              # Raw GPS altitude from NEO-6M
        "speed": 12.5                     # Raw speed from NEO-6M (gps_data['raw_speed'])
    }

    MongoDB Document Structure Created (Non-redundant):
    {
        "_id": ObjectId("..."),
        "device_id": "iot_device_001",
        "fleet_id": "fleet_001",
        "SpeedMps": 3.47,            # Top-level normalized speed in meters/second for ML

        "iot_payload": {             # Complete NEO-6M GPS payload - ALL sensor data
            "fleet_id": "fleet_001",     # Fleet ID (included in IoT payload)
            "device_id": "device_001",   # Device ID (included in IoT payload)
            "Cn0DbHz": 45.2,             # Real NEO-6M SNR from best satellite
            "Svid": 12,                  # Real satellite PRN number from GPGSV
            "SvElevationDegrees": 65,    # Real satellite elevation from NEO-6M
            "SvAzimuthDegrees": 285,     # Real satellite azimuth from NEO-6M
            "IMU_MessageType": "UncalAccel",
            "MeasurementX": 0.7854004,   # Accelerometer X (rounded to 7 decimals)
            "MeasurementY": -0.6618652,  # Accelerometer Y (rounded to 7 decimals)
            "MeasurementZ": -0.06811523, # Accelerometer Z (rounded to 7 decimals)
            "BiasX": 0.0, "BiasY": 0.0, "BiasZ": 0.0,
            "raw_latitude": 8.585581,    # NEO-6M raw GPS latitude
            "raw_longitude": 124.769386, # NEO-6M raw GPS longitude
            "raw_altitude": 3.0,         # NEO-6M raw GPS altitude
            "speed": 12.5                # NEO-6M raw speed (gps_data['raw_speed'])
        },

        "ml_corrected_coordinates": {     # Only the ML-enhanced output (non-redundant)
            "latitude": 8.585123,         # Raw GPS + ML correction
            "longitude": 124.769874       # Raw GPS + ML correction
            # Note: Altitude not corrected (use raw_altitude from iot_payload)
        },

        # ECEF coordinates actually used by the backend for WLS, provided here
        # even if the IoT payload didn't include them (payload fields may be null)
        "wls_ecef": {
            "WlsPositionXEcefMeters": 1100.0,
            "WlsPositionYEcefMeters": 2200.0,
            "WlsPositionZEcefMeters": 3300.0
        },

        "timestamp": 1724717852000        # Milliseconds since epoch
    }

    Args:
        db: Database connection
        vehicle_id: Vehicle identifier 
        device_id: IoT device identifier
        ml_request_data: Original ML request data (the payload above)
        corrected_coordinates: ML-corrected latitude, longitude, altitude
    """

    # Create timestamp in milliseconds since epoch
    timestamp_ms = int(datetime.utcnow().timestamp() * 1000)

    # Extract raw coordinates from the ML request data
    raw_latitude = ml_request_data.get("raw_latitude")
    raw_longitude = ml_request_data.get("raw_longitude")
    raw_altitude = ml_request_data.get("raw_altitude")

    # Determine top-level speed in meters per second (speed_mps)
    speed_mps = None
    # Prefer native meters-per-second field if present in payload
    if ml_request_data.get("speedMps") is not None:
        try:
            speed_mps = float(ml_request_data.get("speedMps"))
        except (ValueError, TypeError):
            speed_mps = None
    # Fallback: legacy 'Speed' (from model input) or 'speed' (kph) -> convert to m/s
    if speed_mps is None:
        legacy_speed = ml_request_data.get("Speed")
        if legacy_speed is None:
            legacy_speed = ml_request_data.get("speed")
        try:
            if legacy_speed is not None:
                speed_mps = float(legacy_speed) / 3.6
        except (ValueError, TypeError):
            speed_mps = None
    # Default to 0.0 if missing
    if speed_mps is None:
        speed_mps = 0.0

    # Build the enhanced log entry with complete IoT payload and only essential derived data
    log_entry = {
        "_id": ObjectId(),  # MongoDB will auto-generate if not provided
        "device_id": device_id,
        "fleet_id": fleet_id,
        # Top-level normalized speed in meters per second for easy querying/aggregation
        "SpeedMps": speed_mps,

        # Complete IoT payload - raw data as received from the IoT device
        "iot_payload": ml_request_data,  # Full original payload for complete traceability

        # Only store the ML-corrected coordinates (non-redundant essential data)
        "ml_corrected_coordinates": {
            # ML-corrected latitude
            "latitude": corrected_coordinates["latitude"],
            # ML-corrected longitude
            "longitude": corrected_coordinates["longitude"]
            # Note: altitude is not corrected by ML, use original from iot_payload
        },

        # ECEF coordinates actually used by backend (computed from raw lat/lon/alt or provided)
        # Included for analysis and retraining; raw payload fields may be null by design
        "wls_ecef": {
            "WlsPositionXEcefMeters": (ecef_coordinates or {}).get("WlsPositionXEcefMeters"),
            "WlsPositionYEcefMeters": (ecef_coordinates or {}).get("WlsPositionYEcefMeters"),
            "WlsPositionZEcefMeters": (ecef_coordinates or {}).get("WlsPositionZEcefMeters"),
        },

        "timestamp": timestamp_ms  # Timestamp in milliseconds
    }

    # Insert as a new document (not pushing to array)
    result = db["tracking_logs"].insert_one(log_entry)

    print(
        f"📝 Enhanced tracking log inserted: Fleet {fleet_id}, Device {device_id}, Raw: ({raw_latitude:.6f}, {raw_longitude:.6f}), Final: ({corrected_coordinates['latitude']:.6f}, {corrected_coordinates['longitude']:.6f})")

    return result.inserted_id  # Return the inserted document ID
