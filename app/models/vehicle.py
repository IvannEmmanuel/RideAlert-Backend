def vehicle_class(vehicle) -> dict:
    return {
        "id": str(vehicle["_id"]),
        "location": vehicle["location"],
        "vehicle_type": vehicle["vehicle_type"],
        "capacity": vehicle["capacity"],
        "available_seats": vehicle["available_seats"],
        "status": vehicle["status"],
        "route": vehicle["route"],
        "driverName": vehicle["driverName"],
        "plate": vehicle["plate"]  # match your Pydantic model, not plate_number
    }
