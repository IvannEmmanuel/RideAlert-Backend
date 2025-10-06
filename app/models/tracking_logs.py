def tracking_class(tracking_log) -> dict:
    return {
        "id": str(tracking_log["_id"]),
        # Foreign Key reference to vehicle._id
        "vehicle_id": str(tracking_log.get("vehicle_id", "")),
        "fleet_id": str(tracking_log.get("fleet_id", "")),
        # Fix: device_id should map to device_id, not fleet_id
        "device_id": str(tracking_log.get("device_id", "")),
        # Expose normalized speed in m/s if present
        "SpeedMps": tracking_log.get("SpeedMps"),
        "gps_data": [
            {
                "latitude": entry["latitude"],
                "longitude": entry["longitude"],
                "timestamp": entry["timestamp"]
            }
            for entry in tracking_log.get("gps_data", [])
        ]
    }
