def user_helper(user) -> dict:
    user_data = {
        "id": str(user["_id"]),
        "first_name": user["first_name"],
        "last_name": user["last_name"],
        "email": user["email"],
        "address": user["address"],
        "gender": user["gender"],
        "role": user["role"],
        "fleet_id": str(user["fleet_id"]),
        "notify": user.get("notify", False)  # ✅ NEW FIELD - defaults to False
    }
    if "location" in user:
        user_data["location"] = user["location"]
    if "fcm_token" in user:
        user_data["fcm_token"] = user.get("fcm_token")
    if "selected_vehicle_id" in user:
        user_data["selected_vehicle_id"] = user.get("selected_vehicle_id")
    return user_data