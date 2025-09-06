from fastapi import APIRouter, HTTPException, Body, Depends, WebSocket, WebSocketDisconnect
from app.models.fleets import fleets
from app.schemas.fleets import FleetCreate, FleetPublic
from app.database import get_fleets_collection
from bson import ObjectId
from datetime import datetime
from typing import List, Dict, Optional
from app.dependencies.roles import super_admin_required
from app.utils.pasword_hashing import hash_password, verify_password
from app.utils.auth_token import create_access_token
import asyncio
from fastapi.encoders import jsonable_encoder
from app.schemas.fleets import SubscriptionPlan
from app.utils.ws_manager import fleet_all_manager, fleet_count_manager

router = APIRouter(prefix="/fleets", tags=["Fleets"])

plan_prices = {
    SubscriptionPlan.basic: 250,
    SubscriptionPlan.premium: 1000,
    SubscriptionPlan.enterprise: 2500
}

max_vehicles_limits = {
    SubscriptionPlan.basic: 5,
    SubscriptionPlan.premium: 25,
    SubscriptionPlan.enterprise: 100
}

def serialize_datetime(obj):
    """Convert datetime and ObjectId objects to strings."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, ObjectId):
        return str(obj)
    return obj

async def broadcast_fleet_list():
    """Helper function to broadcast the full fleet list to all connected /ws/all clients."""
    collection = get_fleets_collection
    fleet_docs = collection.find({"role": {"$ne": "superadmin"}})
    fleets_list = [
        {
            key: serialize_datetime(value) if isinstance(value, (datetime, ObjectId)) else value
            for key, value in fleets(f).items()
        } for f in fleet_docs
    ]
    await fleet_all_manager.broadcast({"fleets": fleets_list})

@router.post("/", response_model=FleetPublic)
async def create_fleet(payload: Optional[FleetCreate] = Body(None)):
    """
    Create a new fleet and broadcast fleet count and updated fleet list.
    """
    collection = get_fleets_collection

    if not payload:
        raise HTTPException(status_code=400, detail="Fleet data is required")

    # company_code must be unique
    if collection.find_one({"company_code": payload.company_code}):
        raise HTTPException(status_code=400, detail="company_code already exists")

    # at least one contact_info required
    if not payload.contact_info or len(payload.contact_info) == 0:
        raise HTTPException(status_code=400, detail="At least one contact_info entry is required")

    email = payload.contact_info[0].email
    if collection.find_one({"contact_info.email": email}):
        raise HTTPException(status_code=400, detail="email already exists")

    # convert payload → dict
    doc = payload.dict()

    # hash password
    if "password" in doc and doc["password"]:
        doc["password"] = hash_password(doc["password"])

    now = datetime.utcnow()
    doc.update({
        "created_at": now,
        "last_updated": now,
        "role": "unverified",
        "is_active": True,
        "plan_price": plan_prices[doc["subscription_plan"]],
        "max_vehicles": max_vehicles_limits[doc["subscription_plan"]]
    })

    result = collection.insert_one(doc)
    created = collection.find_one({"_id": result.inserted_id})

    # 🚀 Broadcast fleet count and fleet list after create
    total_fleets = collection.count_documents({"role": {"$ne": "superadmin"}})
    await fleet_count_manager.broadcast({"total_fleets": total_fleets})
    await broadcast_fleet_list()

    return fleets(created)

@router.post("/login")
async def login_fleet(email: str = Body(...), password: str = Body(...)):
    """
    Login a fleet account using email and password.
    Only fleets with role=admin are allowed.
    """
    collection = get_fleets_collection

    # Look for email inside contact_info
    fleet = collection.find_one({"contact_info.email": email})
    if not fleet:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # Verify hashed password
    if not verify_password(password, fleet["password"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # Role check: only allow admin
    if fleet["role"] not in ["admin", "superadmin"]:
        raise HTTPException(status_code=403, detail="Fleet is not verified/approved")

    # Extract primary email from contact_info
    primary_email = None
    if "contact_info" in fleet and len(fleet["contact_info"]) > 0:
        primary_email = fleet["contact_info"][0]["email"]

    # Prepare token payload
    token_data = {
        "fleet_id": str(fleet["_id"]),
        "email": primary_email,
        "role": fleet["role"]
    }

    access_token = create_access_token(token_data)

    fleet_data = fleets(fleet)
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "message": "Login successful",
        "fleet": fleet_data
    }

@router.websocket("/ws/all")
async def websocket_all_fleets(websocket: WebSocket):
    """
    WebSocket endpoint to stream all fleets in real-time.
    Excludes fleets with role 'superadmin'.
    """
    await fleet_all_manager.connect(websocket)
    collection = get_fleets_collection

    try:
        # Send initial fleet list
        fleet_docs = collection.find({"role": {"$ne": "superadmin"}})
        fleets_list = [
            {
                key: serialize_datetime(value) if isinstance(value, (datetime, ObjectId)) else value
                for key, value in fleets(f).items()
            } for f in fleet_docs
        ]
        await websocket.send_json({"fleets": fleets_list})

        # Keep connection alive
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        fleet_all_manager.disconnect(websocket)
        print("Client disconnected from /ws/all")

@router.websocket("/{fleet_id}/ws")
async def websocket_fleet_details(websocket: WebSocket, fleet_id: str):
    """
    WebSocket endpoint to stream specific fleet details in real-time.
    """
    await websocket.accept()
    collection = get_fleets_collection

    try:
        # Validate ObjectId format
        if not ObjectId.is_valid(fleet_id):
            await websocket.send_json({"error": "Invalid fleet ID format"})
            await websocket.close()
            return

        while True:
            fleet_doc = collection.find_one({"_id": ObjectId(fleet_id)})
            
            if not fleet_doc:
                await websocket.send_json({"error": "Fleet not found"})
                await websocket.close()
                break
            
            # Convert the fleet document using your existing fleets function
            fleet_data = fleets(fleet_doc)
            
            # Serialize datetime and ObjectId fields
            serialized_data = {
                key: serialize_datetime(value) if isinstance(value, (datetime, ObjectId)) else value
                for key, value in fleet_data.items()
            }
            
            await websocket.send_json(serialized_data)
            await asyncio.sleep(5)  # Send updates every 5 seconds
            
    except WebSocketDisconnect:
        print(f"Client disconnected from fleet {fleet_id} details")
    except Exception as e:
        print(f"Error in fleet details WebSocket: {e}")
        await websocket.send_json({"error": str(e)})
        await websocket.close()

@router.websocket("/ws/count-fleets")
async def websocket_count_fleets(websocket: WebSocket):
    await fleet_count_manager.connect(websocket)
    collection = get_fleets_collection

    # Send initial count right after connect
    total_fleets = collection.count_documents({"role": {"$ne": "superadmin"}})
    await websocket.send_json({"total_fleets": total_fleets})

    try:
        while True:
            # keep connection alive
            await websocket.receive_text()
    except Exception:
        fleet_count_manager.disconnect(websocket)

@router.get("/{fleet_id}", response_model=FleetPublic)
def get_fleet(fleet_id: str):
    """
    Get a specific fleet by ID.
    """
    collection = get_fleets_collection
    fleet_doc = collection.find_one({"_id": ObjectId(fleet_id)})
    if not fleet_doc:
        raise HTTPException(status_code=404, detail="Fleet not found")
    return fleets(fleet_doc)

@router.patch("/{fleet_id}", response_model=FleetPublic)
async def update_fleet(fleet_id: str, payload: dict = Body(...)):
    """
    Update a fleet and broadcast fleet count and updated fleet list.
    """
    collection = get_fleets_collection

    update_fields = {}
    allowed_fields = [
        "company_name", "contact_info", "subscription_plan",
        "is_active", "max_vehicles", "last_updated"
    ]

    for field in allowed_fields:
        if field in payload:
            update_fields[field] = payload[field]

    if not update_fields:
        raise HTTPException(status_code=400, detail="No valid fields to update")

    update_fields["last_updated"] = datetime.utcnow()

    result = collection.update_one({"_id": ObjectId(fleet_id)}, {"$set": update_fields})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Fleet not found")

    updated = collection.find_one({"_id": ObjectId(fleet_id)})

    # 🚀 Broadcast fleet count and fleet list
    total_fleets = collection.count_documents({"role": {"$ne": "superadmin"}})
    await fleet_count_manager.broadcast({"total_fleets": total_fleets})
    await broadcast_fleet_list()

    return fleets(updated)

@router.delete("/{fleet_id}")
async def delete_fleet(fleet_id: str):
    """
    Delete a fleet and broadcast fleet count and updated fleet list.
    """
    collection = get_fleets_collection
    result = collection.delete_one({"_id": ObjectId(fleet_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Fleet not found")

    # 🚀 Broadcast fleet count and fleet list
    total_fleets = collection.count_documents({"role": {"$ne": "superadmin"}})
    await fleet_count_manager.broadcast({"total_fleets": total_fleets})
    await broadcast_fleet_list()

    return {"message": "Fleet deleted"}