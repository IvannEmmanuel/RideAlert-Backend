def tracking_class(tracking_log) -> dict:
    return {
        "id": str(tracking_log["_id"]),
        # Foreign Key reference to vehicle._id
        "vehicle_id": str(tracking_log["vehicle_id"]),
        "fleet_id": str(tracking_log["fleet_id"]),
        "device_id": str(tracking_log["fleet_id"]),
        "speed": str(tracking_log["speed"]),
        "gps_data": [
            {
                "latitude": entry["latitude"],
                "longitude": entry["longitude"],
                "timestamp": entry["timestamp"]
            }
            for entry in tracking_log.get("gps_data", [])
        ]
    }
