from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from app.database import vehicle_collection, tracking_logs_collection
from bson import ObjectId
from app.dependencies.roles import user_required, admin_required, user_or_admin_required, super_and_admin_required
from app.schemas.vehicle import VehicleTrackResponse, Location, VehicleStatus, VehicleBase, VehicleInDB
from typing import List
from datetime import datetime
import asyncio
from app.utils.ws_manager import vehicle_count_manager

router = APIRouter(prefix="/vehicles", tags=["Vehicles"])

@router.post("/create/{fleet_id}", response_model=VehicleInDB)
async def create_vehicle_for_fleet(
    fleet_id: str,
    vehicle: VehicleBase,
    current_user: dict = Depends(super_and_admin_required)
):
    # Ensure fleet_id from path is used
    if vehicle_collection.find_one({"plate": vehicle.plate}):
        raise HTTPException(
            status_code=400,
            detail="This vehicle license plate already exists"
        )

    vehicle_dict = vehicle.dict()
    vehicle_dict["fleet_id"] = fleet_id  # override whatever comes from body

    result = vehicle_collection.insert_one(vehicle_dict)
    created_vehicle = vehicle_collection.find_one({"_id": result.inserted_id})
    if not created_vehicle:
        raise HTTPException(status_code=500, detail="Failed to create vehicle")

    # Broadcast vehicle count after create
    total_vehicles = vehicle_collection.count_documents({})
    await vehicle_count_manager.broadcast({"total_vehicles": total_vehicles})

    created_vehicle_dict = {
        "id": str(created_vehicle["_id"]),
        "fleet_id": str(created_vehicle["fleet_id"]),
        "location": created_vehicle.get("location"),
        "vehicle_type": created_vehicle["vehicle_type"],
        "capacity": created_vehicle["capacity"],
        "available_seats": created_vehicle["available_seats"],
        "status": created_vehicle["status"],
        "route": created_vehicle["route"],
        "driverName": created_vehicle["driverName"],
        "plate": created_vehicle["plate"],
        "device_id": created_vehicle.get("device_id"),
        "bound_for": created_vehicle.get("bound_for")
    }

    return VehicleInDB(**created_vehicle_dict)

# @router.post("/create", response_model=VehicleInDB)
# def create_vehicle(vehicle: VehicleBase, current_user: dict = Depends(admin_required)):

#     if vehicle_collection.find_one({"plate": vehicle.plate}):
#         raise HTTPException(status_code=400, detail="This vehicle license plate is existed already")

#     vehicle_dict = vehicle.dict()
#     result = vehicle_collection.insert_one(vehicle_dict)

#     created_vehicle = vehicle_collection.find_one({"_id": result.inserted_id})
#     if not created_vehicle:
#         raise HTTPException(status_code=500, detail="Failed to create that vehicle")

#     created_vehicle_dict = {
#         "id": str(created_vehicle["_id"]),
#         "fleet_id": str(create_vehicle["fleet_id"]),
#         "location": created_vehicle["location"],
#         "vehicle_type": created_vehicle["vehicle_type"],
#         "capacity": created_vehicle["capacity"],
#         "available_seats": created_vehicle["available_seats"],
#         "status": created_vehicle["status"],
#         "route": created_vehicle["route"],
#         "driverName": created_vehicle["driverName"],
#         "plate": created_vehicle["plate"],
#         "device_id": created_vehicle.get("device_id")
#     }

#     return VehicleInDB(**created_vehicle_dict)

# @router.get("/all", response_model=List[VehicleInDB])
# def get_all_vehicles(current_user: dict = Depends(user_or_admin_required)):
#     try:
#         vehicles_cursor = vehicle_collection.find({})
#         vehicles = []
#         for vehicle in vehicles_cursor:
#             vehicle_data = {
#                 "id": str(vehicle["_id"]),
#                 "location": vehicle.get("location"),
#                 "vehicle_type": vehicle.get("vehicle_type", ""),
#                 "capacity": vehicle.get("capacity", 0),
#                 "available_seats": vehicle.get("available_seats", 0),
#                 "status": vehicle.get("status", "unavailable"),
#                 "route": vehicle.get("route", ""),
#                 "driverName": vehicle.get("driverName", ""),
#                 "plate": vehicle.get("plate", ""),
#                 "device_id": vehicle.get("device_id")
#             }
#             vehicles.append(VehicleInDB(**vehicle_data))
#         return vehicles
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Error retrieving vehicles: {str(e)}")

@router.get("/all/{fleet_id}", response_model=List[VehicleInDB])
def get_all_vehicles(fleet_id: str, current_user: dict = Depends(user_or_admin_required)):
    try:
        vehicles_cursor = vehicle_collection.find({
            "$or": [
                {"fleet_id": fleet_id},
                {"fleet_id": ObjectId(fleet_id)} if ObjectId.is_valid(fleet_id) else {}
            ]
        })

        vehicles = []
        for vehicle in vehicles_cursor:
            vehicle_data = {
                "id": str(vehicle["_id"]),
                "location": vehicle.get("location"),
                "vehicle_type": vehicle.get("vehicle_type", ""),
                "capacity": vehicle.get("capacity", 0),
                "available_seats": vehicle.get("available_seats", 0),
                "status": vehicle.get("status", "unavailable"),
                "route": vehicle.get("route", ""),
                "driverName": vehicle.get("driverName", ""),
                "plate": vehicle.get("plate", ""),
                "device_id": vehicle.get("device_id"),
                "fleet_id": str(vehicle.get("fleet_id", ""))
            }
            vehicles.append(VehicleInDB(**vehicle_data))

        return vehicles

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving vehicles: {str(e)}")
    
@router.get("/track/{id}", response_model=VehicleTrackResponse)
def track_vehicle(id: str, current_user: dict = Depends(user_or_admin_required)):
    try:
        vehicle = vehicle_collection.find_one({"_id": ObjectId(id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid vehicle ID format")

    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")

    vehicle_location = vehicle.get("location", {})
    if not vehicle_location.get("latitude") or not vehicle_location.get("longitude"):
        raise HTTPException(status_code=400, detail="Vehicle location unavailable")

    return VehicleTrackResponse(
        id=str(vehicle["_id"]),
        location=Location(
            latitude=vehicle_location["latitude"],
            longitude=vehicle_location["longitude"]
        ),
        available_seats=vehicle.get("available_seats", 0),
        status=VehicleStatus(vehicle["status"]),
        route=vehicle.get("route", ""),
        driverName=vehicle.get("driverName", ""),
        plate=vehicle.get("plate", "")
    )
    
# ADDED TO WEBSOCKET

#You can create a separate endpoint to update device_id when the IoT device is registered
@router.put("/assign-device/{vehicle_id}")
def assign_device_id(vehicle_id: str, device_id: str, current_user: dict = Depends(super_and_admin_required)):
    result = vehicle_collection.update_one(
        {"_id": ObjectId(vehicle_id)},
        {"$set": {"device_id": device_id}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    return {"message": "Device ID assigned successfully"}

@router.delete("/{vehicle_id}")
async def delete_vehicle(vehicle_id: str, current_user: dict = Depends(super_and_admin_required)):
    """
    Delete a vehicle and broadcast vehicle count.
    """
    try:
        result = vehicle_collection.delete_one({"_id": ObjectId(vehicle_id)})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Vehicle not found")

        # Broadcast vehicle count after delete
        total_vehicles = vehicle_collection.count_documents({})
        await vehicle_count_manager.broadcast({"total_vehicles": total_vehicles})

        return {"message": "Vehicle deleted"}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid vehicle ID format")

@router.websocket("/ws/count-vehicles")
async def websocket_count_vehicles(websocket: WebSocket):
    await vehicle_count_manager.connect(websocket)
    collection = vehicle_collection

    # Send initial count right after connect
    total_vehicles = collection.count_documents({})
    await websocket.send_json({"total_vehicles": total_vehicles})

    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        vehicle_count_manager.disconnect(websocket)
        print("Client disconnected from /ws/count-vehicles")