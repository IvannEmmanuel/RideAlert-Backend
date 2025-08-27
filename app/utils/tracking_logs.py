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
            "longitude": 124.769874,  # ML-corrected longitude
            "latitude": 8.585123,     # ML-corrected latitude
            "altitude": 3.0,          # Original altitude from raw_altitude
            "cn0": 57                 # Carrier-to-noise ratio (Cn0DbHz/SNR)
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
    timestamp_ms = int(time.time() * 1000)

    # Build the log entry according to your specification
    log_entry = {
        "_id": ObjectId(),  # MongoDB will auto-generate if not provided
        "vehicle_id": vehicle_id,
        "device_id": device_id,
        "gps_data": {
            "longitude": corrected_coordinates["longitude"],  # ML-corrected
            "latitude": corrected_coordinates["latitude"],    # ML-corrected
            # ML-corrected or original
            "altitude": corrected_coordinates["altitude"],
            "cn0": ml_request_data["Cn0DbHz"]  # Carrier-to-noise ratio (SNR)
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
        f"📝 Tracking log inserted: Vehicle {vehicle_id}, Device {device_id}, Timestamp {timestamp_ms}")

    return result.inserted_id  # Return the inserted document ID
