import threading
import time
from app.database import db

# Threshold in milliseconds (e.g., 5 minutes)
INACTIVITY_THRESHOLD_MS = 5 * 60 * 1000

# Status values for vehicles
VEHICLE_UNAVAILABLE = "unavailable"


def background_status_checker():
    while True:
        now_ms = int(time.time() * 1000)
        # 1. Update IoT devices
        iot_devices = db.iot_devices.find({})
        for device in iot_devices:
            last_updated = device.get("last_updated")
            is_active = device.get("is_active")
            device_id = device.get("_id")
            if last_updated is None or now_ms - last_updated > INACTIVITY_THRESHOLD_MS:
                if is_active != "inactive":
                    db.iot_devices.update_one(
                        {"_id": device_id},
                        {"$set": {"is_active": "inactive"}}
                    )
            else:
                if is_active != "active":
                    db.iot_devices.update_one(
                        {"_id": device_id},
                        {"$set": {"is_active": "active"}}
                    )
        # 2. Update vehicles linked to inactive IoT devices
        inactive_devices = db.iot_devices.find({"is_active": "inactive"})
        for device in inactive_devices:
            vehicle_id = device.get("vehicle_id")
            if vehicle_id:
                db.vehicles.update_one(
                    {"_id": vehicle_id},
                    {"$set": {"status": VEHICLE_UNAVAILABLE,
                              "status_details": VEHICLE_UNAVAILABLE}}
                )
        time.sleep(60)  # Run every minute


def start_background_status_checker():
    thread = threading.Thread(target=background_status_checker, daemon=True)
    thread.start()

# Call start_background_status_checker() during app startup (e.g., in main.py)
