def notification_log_class(log) -> dict:
    return {
        "id": str(log["_id"]),
        "user_id": str(log["user_id"]),
        "fleet_id": str(log["fleet_id"]),
        "vehicle_id": str(log.get("vehicle_id")) if log.get("vehicle_id") else None,
        "message": log.get("message", "No message available"),  # <-- Safe fallback
        "createdAt": log["createdAt"]
    }