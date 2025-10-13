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
        print(
            f"[StatusChecker] --- Checking IoT device statuses at {now_ms} ---")
        iot_devices = db.iot_devices.find({})
        for device in iot_devices:
            # Use last_updated if present, else fallback to last_update
            last_updated = device.get("last_updated")
            if last_updated is None:
                last_updated = device.get("last_update")
                # If last_update is a dict with $numberLong, extract value
                if isinstance(last_updated, dict) and "$numberLong" in last_updated:
                    last_updated = int(last_updated["$numberLong"])
                # If last_update is a datetime, convert to epoch ms
                elif hasattr(last_updated, "timestamp"):
                    last_updated = int(last_updated.timestamp() * 1000)
            is_active = device.get("is_active")
            device_id = device.get("_id")
            print(
                f"[StatusChecker] Device {device_id}: last_updated={last_updated}, is_active={is_active}")
            if last_updated is None:
                print(
                    f"[StatusChecker] Device {device_id} has no last_updated or last_update field.")
            elif not isinstance(last_updated, int):
                print(
                    f"[StatusChecker] Device {device_id} last_updated is not int: {last_updated} (type={type(last_updated)})")
            if last_updated is None or not isinstance(last_updated, int):
                print(
                    f"[StatusChecker] Device {device_id} cannot be checked for inactivity (missing/invalid timestamp)")
            elif now_ms - last_updated > INACTIVITY_THRESHOLD_MS:
                print(
                    f"[StatusChecker] Device {device_id} is INACTIVE (last_updated {last_updated}, now {now_ms}, diff {now_ms - last_updated} ms)")
                if is_active != "inactive":
                    print(
                        f"[StatusChecker] Setting device {device_id} to inactive.")
                    db.iot_devices.update_one(
                        {"_id": device_id},
                        {"$set": {"is_active": "inactive"}}
                    )
            else:
                print(
                    f"[StatusChecker] Device {device_id} is ACTIVE (last_updated {last_updated}, now {now_ms}, diff {now_ms - last_updated} ms)")
                if is_active != "active":
                    print(
                        f"[StatusChecker] Setting device {device_id} to active.")
                    db.iot_devices.update_one(
                        {"_id": device_id},
                        {"$set": {"is_active": "active"}}
                    )
        print(
            f"[StatusChecker] --- Updating vehicles linked to inactive IoT devices ---")
        inactive_devices = db.iot_devices.find({"is_active": "inactive"})
        for device in inactive_devices:
            vehicle_id = device.get("vehicle_id")
            print(
                f"[StatusChecker] Inactive device {device.get('_id')}, vehicle_id={vehicle_id}")
            if vehicle_id:
                print(
                    f"[StatusChecker] Setting vehicle {vehicle_id} status to unavailable.")
                db.vehicles.update_one(
                    {"_id": vehicle_id},
                    {"$set": {"status": VEHICLE_UNAVAILABLE,
                              "status_details": VEHICLE_UNAVAILABLE}}
                )
        print(f"[StatusChecker] --- Sleeping for 60 seconds ---\n")
        time.sleep(60)  # Run every minute


def start_background_status_checker():
    thread = threading.Thread(target=background_status_checker, daemon=True)
    thread.start()

# Call start_background_status_checker() during app startup (e.g., in main.py)
