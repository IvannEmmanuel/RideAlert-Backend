from fastapi import APIRouter, Depends, HTTPException
from app.database import vehicle_collection, tracking_logs_collection
from bson import ObjectId
from app.dependencies.roles import user_required, admin_required, user_or_admin_required
from app.schemas.vehicle import VehicleTrackResponse, Location, VehicleStatus, VehicleBase, VehicleInDB
from typing import List
from datetime import datetime

router = APIRouter(prefix="/vehicles", tags=["Vehicles"])

@router.post("/create", response_model=VehicleInDB)
def create_vehicle(vehicle: VehicleBase, current_user: dict = Depends(admin_required)):
    if vehicle_collection.find_one({"plate": vehicle.plate}):
        raise HTTPException(status_code=400, detail="This vehicle license plate is existed already")

    vehicle_dict = vehicle.dict()
    result = vehicle_collection.insert_one(vehicle_dict)

    # Insert into tracking_logs
    tracking_logs_collection.insert_one({
        "vehicle_id": str(result.inserted_id),
        "gps_data": [{
            "latitude": vehicle.location.latitude,
            "longitude": vehicle.location.longitude,
            "timestamp": datetime.utcnow()
        }]
    })

    created_vehicle = vehicle_collection.find_one({"_id": result.inserted_id})
    if not created_vehicle:
        raise HTTPException(status_code=500, detail="Failed to create that vehicle")

    created_vehicle_dict = {
        "id": str(created_vehicle["_id"]),
        "location": created_vehicle["location"],
        "vehicle_type": created_vehicle["vehicle_type"],
        "capacity": created_vehicle["capacity"],
        "available_seats": created_vehicle["available_seats"],
        "status": created_vehicle["status"],
        "route": created_vehicle["route"],
        "driverName": created_vehicle["driverName"],
        "plate": created_vehicle["plate"]
    }

    return VehicleInDB(**created_vehicle_dict)

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

@router.get("/all", response_model=List[VehicleTrackResponse])
def track_all_vehicles(current_user: dict = Depends(user_or_admin_required)):
    vehicles = []
    for vehicle in vehicle_collection.find():
        vehicle_location = vehicle.get("location", {})
        if vehicle_location.get("latitude") and vehicle_location.get("longitude"):
            vehicles.append(VehicleTrackResponse(
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
            ))
    if not vehicles:
        raise HTTPException(status_code=404, detail="No vehicles with valid locations found")
    return vehicles

@router.get("/count")
def count_vehicles(current_user: dict = Depends(user_or_admin_required)):
    try:
        total = vehicle_collection.count_documents({})
        return {"count": total}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error counting vehicles: {str(e)}")
    
@router.get("/count/available")
def count_available_vehicles(current_user: dict = Depends(user_or_admin_required)):
    try:
        available = vehicle_collection.count_documents({"status": "available"})
        return {"count": available}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error counting available vehicles: {str(e)}")
    
#I think I balhin nani sa websocket para usa ra tanan :>>