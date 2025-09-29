from fastapi import APIRouter, HTTPException, Body, Depends, WebSocket, WebSocketDisconnect
from app.models.iot_devices import iot_devices
from app.schemas.iot_devices import IoTDeviceCreate, IoTDevicePublic
from app.database import get_iot_devices_collection, vehicle_collection, get_fleets_collection
from bson import ObjectId
from datetime import datetime
from typing import List, Dict, Optional
from app.dependencies.roles import super_admin_required, admin_required, user_or_admin_required
from app.schemas.iot_devices import IoTDeviceModel
from app.utils.ws_manager import iot_device_all_manager, FleetConnectionManager

router = APIRouter(prefix="/iot_devices", tags=["IoT Devices"])

# Add fleet-specific IoT device manager
iot_device_fleet_manager = FleetConnectionManager()

def serialize_datetime(obj):
    """Convert datetime and ObjectId objects to strings."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, ObjectId):
        return str(obj)
    return obj

async def broadcast_iot_device_list():
    """Broadcast the list of all IoT devices to connected /ws/all clients."""
    collection = get_iot_devices_collection
    devices = collection.find()
    device_list = [
        {
            key: serialize_datetime(value) if isinstance(value, (datetime, ObjectId)) else value
            for key, value in iot_devices(device).items()
        } for device in devices
    ]
    await iot_device_all_manager.broadcast({"devices": device_list})

async def broadcast_fleet_iot_devices(fleet_id: str):
    """Broadcast IoT devices assigned to a specific fleet."""
    collection = get_iot_devices_collection
    fleets_collection = get_fleets_collection
    
    # Get fleet company name
    fleet_doc = fleets_collection.find_one({"_id": ObjectId(fleet_id)})
    if not fleet_doc:
        return
    
    company_name = fleet_doc.get("company_name", "")
    
    # Find devices assigned to this company
    devices = collection.find({"company_name": company_name})
    device_list = [
        {
            key: serialize_datetime(value) if isinstance(value, (datetime, ObjectId)) else value
            for key, value in iot_devices(device).items()
        } for device in devices
    ]
    await iot_device_fleet_manager.broadcast({"devices": device_list}, fleet_id)

@router.post("/change-route-bound-status/{vehicle_id}")
async def change_route_status(
    vehicle_id: str,
    new_status: str = Body(..., embed=True),
):
    # Update the vehicle's status in the database
    result = vehicle_collection.update_one(
        {"_id": ObjectId(vehicle_id)},
        {"$set": {"bound_for": new_status}}
    )
    if result.modified_count == 0:
        raise HTTPException(
            status_code=404, detail="Vehicle not found or status not changed")

    return {"message": "Vehicle status updated successfully"}

@router.post("/", response_model=IoTDevicePublic)
async def create_iot_device(
    payload: Optional[IoTDeviceCreate] = Body(None),
    current_user: Dict = Depends(super_admin_required)
):
    if not payload:
        raise HTTPException(status_code=400, detail="IoT device data is required")

    doc = {
        "vehicle_id": payload.vehicle_id if payload else None,
        "is_active": payload.is_active if payload else None,
        "device_name": payload.device_name if payload else None,
        "device_model": payload.device_model,
        "company_name": payload.company_name if payload else None,
        "notes": payload.notes if payload else None,
        "createdAt": datetime.utcnow(),
        "last_update": datetime.utcnow()
    }

    if doc["vehicle_id"]:
        try:
            vehicle = vehicle_collection.find_one({"_id": ObjectId(doc["vehicle_id"])})
            if not vehicle:
                raise HTTPException(status_code=404, detail="Vehicle not found")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid vehicle ID format")

    result = get_iot_devices_collection.insert_one(doc)
    created = get_iot_devices_collection.find_one({"_id": result.inserted_id})

    # Broadcast updated IoT device list
    await broadcast_iot_device_list()
    

    #NEWLY ADDED
    # If assigned to a company, broadcast to that fleet too 
    if doc["company_name"]:
        fleets_collection = get_fleets_collection
        fleet_doc = fleets_collection.find_one({"company_name": doc["company_name"]})
        if fleet_doc:
            await broadcast_fleet_iot_devices(str(fleet_doc["_id"]))

    return iot_devices(created)

@router.get("/device-models", response_model=List[str])
async def get_device_models():
    return [model.value for model in IoTDeviceModel]

@router.websocket("/ws/all")
async def websocket_all_iot_devices(websocket: WebSocket):
    """
    WebSocket endpoint to stream all IoT devices in real-time.
    """
    await iot_device_all_manager.connect(websocket)
    try:
        # Send initial IoT device list
        collection = get_iot_devices_collection
        devices = collection.find()
        device_list = [
            {
                key: serialize_datetime(value) if isinstance(value, (datetime, ObjectId)) else value
                for key, value in iot_devices(device).items()
            } for device in devices
        ]
        await websocket.send_json({"devices": device_list})

        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        iot_device_all_manager.disconnect(websocket)
        print("Client disconnected from /iot_devices/ws/all")
    except Exception as e:
        iot_device_all_manager.disconnect(websocket)
        print(f"Error in IoT devices WebSocket: {e}")
        await websocket.send_json({"error": str(e)})
        await websocket.close()

#NEWLY ADDED
@router.websocket("/ws/fleet/{fleet_id}")
async def websocket_fleet_iot_devices(websocket: WebSocket, fleet_id: str):
    """
    WebSocket endpoint to stream IoT devices assigned to a specific fleet.
    """
    await iot_device_fleet_manager.connect(websocket, fleet_id)
    try:
        # Get fleet company name
        fleets_collection = get_fleets_collection
        fleet_doc = fleets_collection.find_one({"_id": ObjectId(fleet_id)})
        if not fleet_doc:
            await websocket.send_json({"error": "Fleet not found"})
            return
        
        company_name = fleet_doc.get("company_name", "")
        
        # Send initial IoT device list for this fleet
        collection = get_iot_devices_collection
        devices = collection.find({"company_name": company_name})
        device_list = [
            {
                key: serialize_datetime(value) if isinstance(value, (datetime, ObjectId)) else value
                for key, value in iot_devices(device).items()
            } for device in devices
        ]
        await websocket.send_json({"devices": device_list})

        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        iot_device_fleet_manager.disconnect(websocket, fleet_id)
        print(f"Client disconnected from /iot_devices/ws/fleet/{fleet_id}")
    except Exception as e:
        iot_device_fleet_manager.disconnect(websocket, fleet_id)
        print(f"Error in IoT devices fleet WebSocket: {e}")
        await websocket.send_json({"error": str(e)})
        await websocket.close()

@router.get("/{device_id}", response_model=IoTDevicePublic)
def get_iot_device(device_id: str):
    """
    Get a specific IoT device by ID.
    """
    try:
        collection = get_iot_devices_collection
        device = collection.find_one({"_id": ObjectId(device_id)})
        if not device:
            raise HTTPException(status_code=404, detail="IoT device not found")
        return iot_devices(device)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid device ID format")

@router.patch("/{device_id}", response_model=IoTDevicePublic)
async def update_iot_device(device_id: str, payload: dict = Body(...), current_user: Dict = Depends(user_or_admin_required)):
    """
    Update fields of an IoT device and broadcast updated list.
    """
    try:
        collection = get_iot_devices_collection
        
        #NEWLY ADDED
        # Get current device to check company assignment
        current_device = collection.find_one({"_id": ObjectId(device_id)})
        if not current_device:
            raise HTTPException(status_code=404, detail="IoT device not found")

        update_fields = {}
        allowed_fields = ["is_active", "last_update", "vehicle_id", "device_name", "device_model", "company_name", "notes"]
        for field in allowed_fields:
            if field in payload:
                update_fields[field] = payload[field]

        if not update_fields:
            raise HTTPException(status_code=400, detail="No valid fields to update")

        update_fields["last_update"] = datetime.utcnow()

        if "vehicle_id" in update_fields and update_fields["vehicle_id"]:
            vehicle = vehicle_collection.find_one({"_id": ObjectId(update_fields["vehicle_id"])})
            if not vehicle:
                raise HTTPException(status_code=404, detail="Vehicle not found")

        result = collection.update_one(
            {"_id": ObjectId(device_id)},
            {"$set": update_fields}
        )

        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="IoT device not found")

        updated = collection.find_one({"_id": ObjectId(device_id)})

        # Broadcast updated IoT device list
        await broadcast_iot_device_list()
        
        #NEWLY ADDED
        # Broadcast to fleet if company assignment changed or exists
        old_company = current_device.get("company_name")
        new_company = updated.get("company_name")
        
        fleets_collection = get_fleets_collection
        
        if old_company and old_company != new_company:
            # Broadcast to old fleet
            old_fleet_doc = fleets_collection.find_one({"company_name": old_company})
            if old_fleet_doc:
                await broadcast_fleet_iot_devices(str(old_fleet_doc["_id"]))
        
        if new_company:
            # Broadcast to new fleet
            new_fleet_doc = fleets_collection.find_one({"company_name": new_company})
            if new_fleet_doc:
                await broadcast_fleet_iot_devices(str(new_fleet_doc["_id"]))

        return iot_devices(updated)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid device ID format")
    
@router.delete("/{device_id}")
async def delete_iot_device(device_id: str, current_user: Dict = Depends(super_admin_required)):
    """
    Delete an IoT device and broadcast updated list.
    """
    try:
        collection = get_iot_devices_collection
        
        #NEWLY ADDED
        # Get device before deletion to know which fleet to update
        device = collection.find_one({"_id": ObjectId(device_id)})
        if not device:
            raise HTTPException(status_code=404, detail="IoT device not found")
        
        company_name = device.get("company_name")
        
        result = collection.delete_one({"_id": ObjectId(device_id)})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="IoT device not found")

        # Broadcast updated IoT device list
        await broadcast_iot_device_list()
        
        #NEWLY ADDED
        # Broadcast to fleet if it was assigned to a company
        if company_name:
            fleets_collection = get_fleets_collection
            fleet_doc = fleets_collection.find_one({"company_name": company_name})
            if fleet_doc:
                await broadcast_fleet_iot_devices(str(fleet_doc["_id"]))

        return {"message": "IoT device deleted"}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid device ID format")
    

#NEWLY ADDED    
# Add this new endpoint to your iot-device-router.js
@router.get("/fleet/{fleet_id}", response_model=List[IoTDevicePublic])
async def get_fleet_iot_devices(fleet_id: str, current_user: Dict = Depends(admin_required)):
    """
    Get IoT devices assigned to a specific fleet/company.
    """
    try:
        collection = get_iot_devices_collection
        # Get the fleet's company name first
        fleet_collection = get_fleets_collection()
        fleet = fleet_collection.find_one({"_id": ObjectId(fleet_id)})
        if not fleet:
            raise HTTPException(status_code=404, detail="Fleet not found")
        
        company_name = fleet.get("company_name")
        devices = collection.find({"company_name": company_name})
        
        device_list = [iot_devices(device) for device in devices]
        return device_list
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid fleet ID format")

@router.websocket("/fleet/{fleet_id}/ws")
async def websocket_fleet_iot_devices(websocket: WebSocket, fleet_id: str):
    """
    WebSocket endpoint to stream IoT devices for a specific fleet in real-time.
    """
    await websocket.accept()
    try:
        # Get the fleet's company name
        fleet_collection = get_fleets_collection()
        fleet = fleet_collection.find_one({"_id": ObjectId(fleet_id)})
        if not fleet:
            await websocket.send_json({"error": "Fleet not found"})
            await websocket.close()
            return
            
        company_name = fleet.get("company_name")
        
        # Send initial IoT device list for this fleet
        collection = get_iot_devices_collection
        devices = collection.find({"company_name": company_name})
        device_list = [
            {
                key: serialize_datetime(value) if isinstance(value, (datetime, ObjectId)) else value
                for key, value in iot_devices(device).items()
            } for device in devices
        ]
        await websocket.send_json({"devices": device_list})

        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        print(f"Client disconnected from /iot_devices/fleet/{fleet_id}/ws")
    except Exception as e:
        print(f"Error in fleet IoT devices WebSocket: {e}")
        await websocket.send_json({"error": str(e)})
        await websocket.close()