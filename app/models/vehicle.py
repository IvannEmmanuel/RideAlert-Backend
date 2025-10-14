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
        # match your Pydantic model, not plate_number of the vehicle
        "plate": vehicle["plate"],
        "device_id": vehicle["device_id"],  # foreign key
        "fleet_id": vehicle["fleet_id"],
        "bound_for": vehicle("bound_for"),
        "status_details": vehicle("status_details"),
        "route_id": vehicle.get("route_id")  # Reference to declared_routes
    }
