def tracking_class(tracking_log) -> dict:

    result = {
        "id": str(tracking_log["_id"]),
        "vehicle_id": str(tracking_log.get("vehicle_id", "")),
        "fleet_id": str(tracking_log.get("fleet_id", "")),
        "device_id": str(tracking_log.get("device_id", "")),
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
    # Add moved_point if present
    if "moved_point" in tracking_log:
        result["moved_point"] = tracking_log["moved_point"]
    return result
