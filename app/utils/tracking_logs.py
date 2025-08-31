from datetime import datetime
from bson import ObjectId
import time


def insert_gps_log(db, vehicle_id: str, device_id: str, ml_request_data: dict, corrected_coordinates: dict):
    """
    Insert ML prediction log into MongoDB Atlas with complete sensor data structure

    Expected Payload Before Prediction:
    {
        "Cn0DbHz": 57,                    # SNR (Signal-to-Noise Ratio)
        "Svid": 28,                       # Satellite ID  
        "SvElevationDegrees": 30,
        "SvAzimuthDegrees": 16,
        "IMU_MessageType": "UncalAccel",  # Use accel value for measurements
        "MeasurementX": 0.7854004,
        "MeasurementY": -0.6618652,
        "MeasurementZ": -0.06811523,
        "BiasX": 0.0,
        "BiasY": 0.0,
        "BiasZ": 0.0,
        "raw_latitude": 8.585581,
        "raw_longitude": 124.769386,
        "raw_altitude": 3.0
    }

    MongoDB Document Structure Created:
    {
        "_id": ObjectId("..."),
        "vehicle_id": "vehicle_001", 
        "device_id": "iot_device_001",
        "gps_data": {
            "raw_coordinates": {
                "latitude": 8.585581,    # Original raw GPS from IoT device
                "longitude": 124.769386, # Original raw GPS from IoT device
                "altitude": 3.0          # Original raw GPS from IoT device
            },
            "final_coordinates": {
                "latitude": 8.585123,    # Final = WLS + ML offset prediction
                "longitude": 124.769874  # Final = WLS + ML offset prediction
                # Note: altitude is NOT corrected by ML (uses original raw altitude)
            },
            "cn0": 57                    # Carrier-to-noise ratio (Cn0DbHz/SNR)
        },
        "imu_data": {
            "MeasurementX": 0.7854004,     # From accelerometer 
            "MeasurementY": -0.6618652,    # From accelerometer
            "MeasurementZ": -0.06811523,   # From accelerometer
            "BiasX": 0.0,                  # X-axis sensor offset
            "BiasY": 0.0,                  # Y-axis sensor offset  
            "BiasZ": 0.0,                  # Z-axis sensor offset
            "IMU_MessageType": "UncalAccel" # Accelerometer data type
        },
        "timestamp": 1724717852000  # Milliseconds since epoch
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

    # Build the enhanced log entry with both raw and final corrected coordinates
    log_entry = {
        "_id": ObjectId(),  # MongoDB will auto-generate if not provided
        "vehicle_id": vehicle_id,
        "device_id": device_id,
        "gps_data": {
            "raw_coordinates": {
                "latitude": raw_latitude,      # Original raw GPS reading from IoT device
                "longitude": raw_longitude,    # Original raw GPS reading from IoT device
                "altitude": raw_altitude       # Original raw GPS reading from IoT device
            },
            "final_coordinates": {
                # Final = WLS + ML offset
                "latitude": corrected_coordinates["latitude"],
                # Final = WLS + ML offset
                "longitude": corrected_coordinates["longitude"]
                # Altitude not included since ML doesn't correct it (uses original)
            },
            "cn0": ml_request_data["Cn0DbHz"]  # Signal quality indicator
        },
        "imu_data": {
            "MeasurementX": ml_request_data["MeasurementX"],
            "MeasurementY": ml_request_data["MeasurementY"],
            "MeasurementZ": ml_request_data["MeasurementZ"],
            "BiasX": ml_request_data["BiasX"],
            "BiasY": ml_request_data["BiasY"],
            "BiasZ": ml_request_data["BiasZ"],
            "IMU_MessageType": ml_request_data["IMU_MessageType"]
        },
        "timestamp": timestamp_ms  # Timestamp in milliseconds
    }

    # Insert as a new document (not pushing to array)
    result = db["tracking_logs"].insert_one(log_entry)

    print(
        f"📝 Enhanced tracking log inserted: Vehicle {vehicle_id}, Device {device_id}, Raw: ({raw_latitude:.6f}, {raw_longitude:.6f}), Final: ({corrected_coordinates['latitude']:.6f}, {corrected_coordinates['longitude']:.6f})")

    return result.inserted_id  # Return the inserted document ID
