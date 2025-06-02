def tracking_class(tracking_log) -> dict:
    return {
        "id": str(tracking_log["_id"]),
        "vehicle_id": str(tracking_log["vehicle_id"]),  # FK reference to vehicle._id
        "gps_data": [
            {
                "latitude": entry["latitude"],
                "longitude": entry["longitude"],
                "timestamp": entry["timestamp"]
            }
            for entry in tracking_log.get("gps_data", [])
        ]
    }