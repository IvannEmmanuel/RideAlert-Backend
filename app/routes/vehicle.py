from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from app.database import vehicle_collection, tracking_logs_collection
from bson import ObjectId
from app.dependencies.roles import user_required, admin_required, user_or_admin_required, super_and_admin_required
from app.schemas.vehicle import VehicleTrackResponse, Location, VehicleStatus, VehicleBase, VehicleInDB
from typing import List
from datetime import datetime
import asyncio
from app.utils.ws_manager import vehicle_count_manager, vehicle_all_manager

router = APIRouter(prefix="/vehicles", tags=["Vehicles"])

def serialize_vehicle(vehicle):
    """Serialize a vehicle document, converting ObjectId to string."""
    return {
        "id": str(vehicle["_id"]),
        "fleet_id": str(vehicle.get("fleet_id", "")),
        "location": vehicle.get("location"),
        "vehicle_type": vehicle.get("vehicle_type", ""),
        "capacity": vehicle.get("capacity", 0),
        "available_seats": vehicle.get("available_seats", 0),
        "status": vehicle.get("status", "unavailable"),
        "route": vehicle.get("route", ""),
        "driverName": vehicle.get("driverName", ""),
        "plate": vehicle.get("plate", ""),
        "device_id": vehicle.get("device_id"),
        "bound_for": vehicle.get("bound_for")
    }

async def broadcast_vehicle_list(fleet_id: str):
    """Broadcast the list of vehicles for a specific fleet_id."""
    vehicles = [
        serialize_vehicle(vehicle)
        for vehicle in vehicle_collection.find({"fleet_id": fleet_id})
    ]
    await vehicle_all_manager.broadcast({"vehicles": vehicles}, fleet_id)

async def broadcast_available_vehicle_list(fleet_id: str):
    """Broadcast the list of available vehicles with valid locations for a specific fleet_id."""
    query = {
        "fleet_id": fleet_id,
        "status": "available",
        "location.latitude": {"$ne": None},
        "location.longitude": {"$ne": None}
    }
    vehicles = [
        {
            "id": str(vehicle["_id"]),
            "location": vehicle.get("location"),
            "available_seats": vehicle.get("available_seats", 0),
            "route": vehicle.get("route", ""),
            "driverName": vehicle.get("driverName", ""),
            "plate": vehicle.get("plate", ""),
            "status": vehicle.get("status", "unavailable")
        }
        for vehicle in vehicle_collection.find(query)
    ]
    await vehicle_all_manager.broadcast({"vehicles": vehicles}, fleet_id)

@router.post("/create/{fleet_id}", response_model=VehicleInDB)
async def create_vehicle_for_fleet(
    fleet_id: str,
    vehicle: VehicleBase,
    current_user: dict = Depends(super_and_admin_required)
):
    # Ensure plate is unique
    if vehicle_collection.find_one({"plate": vehicle.plate}):
        raise HTTPException(
            status_code=400,
            detail="This vehicle license plate already exists"
        )

    # Convert to dict and enforce fleet_id
    vehicle_dict = vehicle.dict()
    vehicle_dict["fleet_id"] = fleet_id

    # Insert into DB
    result = vehicle_collection.insert_one(vehicle_dict)
    created_vehicle = vehicle_collection.find_one({"_id": result.inserted_id})
    if not created_vehicle:
        raise HTTPException(status_code=500, detail="Failed to create vehicle")

    # Broadcast updated vehicle count and list
    total_vehicles = vehicle_collection.count_documents({})
    await vehicle_count_manager.broadcast({"total_vehicles": total_vehicles})
    await broadcast_vehicle_list(fleet_id)

    # Safe location check before broadcasting available list
    location = created_vehicle.get("location")
    if (
        created_vehicle.get("status") == "available"
        and isinstance(location, dict)
        and location.get("latitude") is not None
        and location.get("longitude") is not None
    ):
        await broadcast_available_vehicle_list(fleet_id)

    # Return serialized vehicle
    created_vehicle_dict = serialize_vehicle(created_vehicle)
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
            vehicle_data = serialize_vehicle(vehicle)
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
async def assign_device_id(vehicle_id: str, device_id: str, current_user: dict = Depends(super_and_admin_required)):
    try:
        result = vehicle_collection.update_one(
            {"_id": ObjectId(vehicle_id)},
            {"$set": {"device_id": device_id}}
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Vehicle not found")

        # Broadcast vehicle lists if the vehicle is available and has a valid location
        vehicle = vehicle_collection.find_one({"_id": ObjectId(vehicle_id)})
        fleet_id = str(vehicle.get("fleet_id", ""))
        await broadcast_vehicle_list(fleet_id)
        if vehicle.get("status") == "available" and vehicle.get("location", {}).get("latitude") and vehicle.get("location", {}).get("longitude"):
            await broadcast_available_vehicle_list(fleet_id)

        return {"message": "Device ID assigned successfully"}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid vehicle ID format")

@router.delete("/{vehicle_id}")
async def delete_vehicle(vehicle_id: str, current_user: dict = Depends(super_and_admin_required)):
    try:
        vehicle = vehicle_collection.find_one({"_id": ObjectId(vehicle_id)})
        if not vehicle:
            raise HTTPException(status_code=404, detail="Vehicle not found")
        
        fleet_id = str(vehicle.get("fleet_id", ""))
        result = vehicle_collection.delete_one({"_id": ObjectId(vehicle_id)})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Vehicle not found")

        # Broadcast vehicle count and vehicle lists
        total_vehicles = vehicle_collection.count_documents({})
        await vehicle_count_manager.broadcast({"total_vehicles": total_vehicles})
        await broadcast_vehicle_list(fleet_id)
        if vehicle.get("status") == "available" and vehicle.get("location", {}).get("latitude") and vehicle.get("location", {}).get("longitude"):
            await broadcast_available_vehicle_list(fleet_id)

        return {"message": "Vehicle deleted"}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid vehicle ID format")

@router.websocket("/ws/count-vehicles")
async def websocket_count_vehicles(websocket: WebSocket):
    await vehicle_count_manager.connect(websocket)
    collection = vehicle_collection

    try:
        # Try sending initial count
        total_vehicles = collection.count_documents({})
        await websocket.send_json({"total_vehicles": total_vehicles})

        # Keep connection alive (listen for pings/messages)
        while True:
            await websocket.receive_text()

    except WebSocketDisconnect:
        vehicle_count_manager.disconnect(websocket)
        print("Client disconnected from /ws/count-vehicles")

    except Exception as e:
        # Log other errors, but don’t try to send_json here
        print(f"Unexpected error in /ws/count-vehicles: {e}")
        vehicle_count_manager.disconnect(websocket)

@router.websocket("/ws/vehicles/available/{fleet_id}")
async def available_vehicles_ws(websocket: WebSocket, fleet_id: str):
    """Stream only available vehicles that have a location"""
    await vehicle_all_manager.connect(websocket, fleet_id)
    try:
        # Send initial list of available vehicles
        query = {
            "fleet_id": fleet_id,
            "status": "available",
            "location.latitude": {"$ne": None},
            "location.longitude": {"$ne": None}
        }
        vehicles = [
            {
                "id": str(vehicle["_id"]),
                "location": vehicle.get("location"),
                "available_seats": vehicle.get("available_seats", 0),
                "route": vehicle.get("route", ""),
                "driverName": vehicle.get("driverName", ""),
                "plate": vehicle.get("plate", ""),
                "status": vehicle.get("status", "unavailable")
            }
            for vehicle in vehicle_collection.find(query)
        ]
        await websocket.send_json({"vehicles": vehicles})

        while True:
            # Keep connection alive
            await websocket.receive_text()

    except WebSocketDisconnect:
        vehicle_all_manager.disconnect(websocket, fleet_id)
        print(f"Available vehicle stream for fleet {fleet_id} disconnected")
    except Exception as e:
        vehicle_all_manager.disconnect(websocket, fleet_id)
        print(f"Error in available vehicles WebSocket for fleet {fleet_id}: {e}")

#NEWLY ADDED
@router.websocket("/ws/vehicles/all/{fleet_id}")
async def websocket_all_vehicles(websocket: WebSocket, fleet_id: str):
    """
    WebSocket endpoint to stream all vehicles for a specific fleet in real-time.
    """
    await vehicle_all_manager.connect(websocket, fleet_id)
    try:
        # Send initial vehicle list
        vehicles = [
            serialize_vehicle(vehicle)
            for vehicle in vehicle_collection.find({"fleet_id": fleet_id})
        ]
        await websocket.send_json({"vehicles": vehicles})

        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        vehicle_all_manager.disconnect(websocket, fleet_id)
        print(f"Client disconnected from vehicles/all/{fleet_id}")
    except Exception as e:
        vehicle_all_manager.disconnect(websocket, fleet_id)
        print(f"Error in vehicles WebSocket for fleet {fleet_id}: {e}")