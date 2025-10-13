import threading
import time
from app.database import db
from bson import ObjectId

# Threshold in milliseconds (e.g., 5 minutes)
INACTIVITY_THRESHOLD_MS = 5 * 60 * 1000

# Status values for vehicles
VEHICLE_UNAVAILABLE = "unavailable"


def background_status_checker():
    while True:
        now_ms = int(time.time() * 1000)
        print(
            f"[StatusChecker] --- Checking IoT device statuses at {now_ms} ---")
        iot_devices = db.iot_devices.find({})
        for device in iot_devices:
            # Ensure device_id is ObjectId
            raw_device_id = device.get("_id")
            device_id = raw_device_id
            if isinstance(raw_device_id, dict) and "$oid" in raw_device_id:
                device_id = ObjectId(raw_device_id["$oid"])
            is_active = device.get("is_active")
            # Find the latest tracking log for this device using string device id
            str_device_id = str(device_id)
            latest_log = db.tracking_logs.find_one(
                {"device_id": str_device_id}, sort=[("timestamp", -1)])
            last_log_ts = None
            if latest_log:
                ts = latest_log.get("timestamp")
                if isinstance(ts, dict) and "$numberLong" in ts:
                    last_log_ts = int(ts["$numberLong"])
                elif hasattr(ts, "timestamp"):
                    last_log_ts = int(ts.timestamp() * 1000)
                elif isinstance(ts, int):
                    last_log_ts = ts
            print(
                f"[StatusChecker] Device {device_id}: last_tracking_log_ts={last_log_ts}, is_active={is_active}")
            # If latest log timestamp is recent, set device to active
            if last_log_ts is not None and now_ms - last_log_ts <= INACTIVITY_THRESHOLD_MS:
                print(
                    f"[StatusChecker] Device {device_id} is ACTIVE (last log {last_log_ts}, now {now_ms}, diff {now_ms - last_log_ts} ms)")
                if is_active != "active":
                    print(
                        f"[StatusChecker] Setting device {device_id} to active.")
                    db.iot_devices.update_one(
                        {"_id": device_id}, {"$set": {"is_active": "active"}})
            elif last_log_ts is None:
                print(
                    f"[StatusChecker] Device {device_id} has no tracking_logs.")
                if is_active != "inactive":
                    print(
                        f"[StatusChecker] Setting device {device_id} to inactive (no logs).")
                    db.iot_devices.update_one(
                        {"_id": device_id}, {"$set": {"is_active": "inactive"}})
            else:
                print(
                    f"[StatusChecker] Device {device_id} is INACTIVE (last log {last_log_ts}, now {now_ms}, diff {now_ms - last_log_ts} ms)")
                if is_active != "inactive":
                    print(
                        f"[StatusChecker] Setting device {device_id} to inactive.")
                    db.iot_devices.update_one(
                        {"_id": device_id}, {"$set": {"is_active": "inactive"}})

        print(
            f"[StatusChecker] --- Updating vehicles linked to inactive IoT devices ---")
        inactive_devices = db.iot_devices.find({"is_active": "inactive"})
        for device in inactive_devices:
            raw_vehicle_id = device.get("vehicle_id")
            vehicle_id = None
            # Handle dict with $oid
            if isinstance(raw_vehicle_id, dict) and "$oid" in raw_vehicle_id:
                vehicle_id = ObjectId(raw_vehicle_id["$oid"])
            # Handle string that looks like ObjectId
            elif isinstance(raw_vehicle_id, str):
                try:
                    vehicle_id = ObjectId(raw_vehicle_id)
                except Exception:
                    vehicle_id = raw_vehicle_id
            # Already ObjectId
            elif isinstance(raw_vehicle_id, ObjectId):
                vehicle_id = raw_vehicle_id
            print(
                f"[StatusChecker] Inactive device {device.get('_id')}, vehicle_id={vehicle_id} (type={type(vehicle_id)})")
            if vehicle_id:
                print(
                    f"[StatusChecker] Setting vehicle {vehicle_id} status to unavailable.")
                result = db.vehicles.update_one(
                    {"_id": vehicle_id},
                    {"$set": {"status": VEHICLE_UNAVAILABLE,
                              "status_detail": VEHICLE_UNAVAILABLE}}
                )
                print(
                    f"[StatusChecker] Vehicle update matched: {result.matched_count}, modified: {result.modified_count}, query _id type: {type(vehicle_id)}")
        print(f"[StatusChecker] --- Sleeping for 30 seconds ---\n")
        time.sleep(30)  # Run every 30 seconds


def start_background_status_checker():
    thread = threading.Thread(target=background_status_checker, daemon=True)
    thread.start()

# Call start_background_status_checker() during app startup (e.g., in main.py)
