from datetime import datetime
from bson import ObjectId
import time


def insert_gps_log(db, device_id: str, fleet_id: str, ml_request_data: dict, corrected_coordinates: dict):
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
        "speed": 10.5,               # Top-level for easy querying

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

    # Extract speed (support both 'Speed' and 'speed' keys)
    speed_value = ml_request_data.get("Speed")
    if speed_value is None:
        speed_value = ml_request_data.get("speed")
    # Try to normalize to float if possible
    try:
        if speed_value is not None:
            speed_value = float(speed_value)
    except (ValueError, TypeError):
        # Leave as-is if it cannot be converted; optional field
        pass

    # Build the enhanced log entry with complete IoT payload and only essential derived data
    log_entry = {
        "_id": ObjectId(),  # MongoDB will auto-generate if not provided
        "device_id": device_id,
        "fleet_id": fleet_id,
        "speed": speed_value,  # Top-level speed for easy querying/aggregation

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

        "timestamp": timestamp_ms  # Timestamp in milliseconds
    }

    # Insert as a new document (not pushing to array)
    result = db["tracking_logs"].insert_one(log_entry)

    print(
        f"📝 Enhanced tracking log inserted: Fleet {fleet_id}, Device {device_id}, Raw: ({raw_latitude:.6f}, {raw_longitude:.6f}), Final: ({corrected_coordinates['latitude']:.6f}, {corrected_coordinates['longitude']:.6f})")

    return result.inserted_id  # Return the inserted document ID
