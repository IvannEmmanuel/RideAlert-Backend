def user_helper(user) -> dict:
    return {
        "id": str(user["_id"]),
        "first_name": user["first_name"],
        "last_name": user["last_name"],
        "email": user["email"],
        "birthday": user["birthday"],
        "address": user["address"],
        "gender": user["gender"],
    }