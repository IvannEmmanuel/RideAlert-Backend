def notification_log_class(log) -> dict:
    return {
        "id": str(log["_id"]),
        "user_id": str(log["user_id"]),
        "message": log["message"],
        "createdAt": log["createdAt"]
    }