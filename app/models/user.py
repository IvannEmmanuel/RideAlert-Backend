def user_helper(user) -> dict:
    user_data = {
        "id": str(user["_id"]),
        "first_name": user["first_name"],
        "last_name": user["last_name"],
        "email": user["email"],
        "birthday": user["birthday"],
        "address": user["address"],
        "gender": user["gender"],
        "role": user["role"]
    }
    if "location" in user:
        user_data["location"] = user["location"]
    return user_data