from fastapi import APIRouter, HTTPException, Body, Depends
from app.models.iot_devices import iot_devices
from app.schemas.iot_devices import IoTDeviceCreate, IoTDevicePublic
from app.database import get_iot_devices_collection, vehicle_collection
from bson import ObjectId
from datetime import datetime
from typing import List, Dict, Optional
from app.dependencies.roles import admin_required

router = APIRouter(prefix="/iot_devices", tags=["IoT Devices"])

@router.post("/", response_model=IoTDevicePublic)
async def create_iot_device(
    payload: Optional[IoTDeviceCreate] = Body(None),
    current_user: Dict = Depends(admin_required)
):
    doc = {
        "vehicle_id": payload.vehicle_id if payload else None,
        "is_active": payload.is_active if payload else None,
        "device_name": payload.device_name if payload else None,
        "createdAt": datetime.utcnow(),
        "last_update": None
    }

    if doc["vehicle_id"]:
        vehicle = vehicle_collection.find_one({"_id": ObjectId(doc["vehicle_id"])})
        if not vehicle:
            raise HTTPException(status_code=404, detail="Vehicle not found")

    result = get_iot_devices_collection.insert_one(doc)
    created = get_iot_devices_collection.find_one({"_id": result.inserted_id})

    return iot_devices(created)  # ✅ matches IoTDevicePublic

@router.get("/all", response_model=List[IoTDevicePublic])
def list_iot_devices():
    """
    Get all IoT devices.
    """
    collection = get_iot_devices_collection
    devices = collection.find()
    return [iot_devices(device) for device in devices]

@router.get("/{device_id}", response_model=IoTDevicePublic)
def get_iot_device(device_id: str):
    """
    Get a specific IoT device by ID.
    """
    collection = get_iot_devices_collection
    device = collection.find_one({"_id": ObjectId(device_id)})
    if not device:
        raise HTTPException(status_code=404, detail="IoT device not found")
    return iot_devices(device)

@router.patch("/{device_id}", response_model=IoTDevicePublic)
def update_iot_device(device_id: str, payload: dict = Body(...)):
    """
    Update fields of an IoT device (e.g., is_active, last_update).
    """
    collection = get_iot_devices_collection

    update_fields = {}
    if "is_active" in payload:
        update_fields["is_active"] = payload["is_active"]
    if "last_update" in payload:
        update_fields["last_update"] = payload["last_update"]

    if not update_fields:
        raise HTTPException(status_code=400, detail="No valid fields to update")

    result = collection.update_one(
        {"_id": ObjectId(device_id)},
        {"$set": update_fields}
    )

    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="IoT device not found or not updated")

    updated = collection.find_one({"_id": ObjectId(device_id)})
    return iot_devices(updated)
