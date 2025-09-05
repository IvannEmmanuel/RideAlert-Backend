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

router = APIRouter(prefix="/fleets", tags=["Fleets"])

@router.post("/", response_model=FleetPublic)
async def create_fleet(
    payload: Optional[FleetCreate] = Body(None)
):
    """
    Create a new fleet.
    """
    collection = get_fleets_collection

    if not payload:
        raise HTTPException(status_code=400, detail="Fleet data is required")

    # Check if company_code already exists
    if collection.find_one({"company_code": payload.company_code}):
        raise HTTPException(status_code=400, detail="company_code already exists")

    # Extract email from first contact_info entry
    if payload.contact_info and len(payload.contact_info) > 0:
        email = payload.contact_info[0].email
        if collection.find_one({"contact_info.email": email}):
            raise HTTPException(status_code=400, detail="email already exists")
    else:
        raise HTTPException(status_code=400, detail="At least one contact_info entry is required")

    # Convert payload to dict
    doc = payload.dict()

    # Hash password
    if "password" in doc and doc["password"]:
        doc["password"] = hash_password(doc["password"])

    # Add metadata
    now = datetime.utcnow()
    doc.update({
        "created_at": now,
        "last_updated": now,
        "role": "unverified",
        "is_active": False
    })

    result = collection.insert_one(doc)
    created = collection.find_one({"_id": result.inserted_id})

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

#get all the companies
@router.websocket("/ws/all")
async def websocket_all_fleets(websocket: WebSocket):
    """
    WebSocket endpoint to stream all fleets in real-time.
    """
    await websocket.accept()
    collection = get_fleets_collection

    def serialize_datetime(obj):
        """Convert datetime and ObjectId objects to strings."""
        if isinstance(obj, datetime):
            return obj.isoformat()
        elif isinstance(obj, ObjectId):
            return str(obj)
        return obj

    try:
        while True:
            fleet_docs = collection.find()
            fleets_list = [
                {
                    key: serialize_datetime(value) if isinstance(value, (datetime, ObjectId)) else value
                    for key, value in fleets(f).items()
                } for f in fleet_docs
            ]  # Convert datetime and ObjectId fields to strings
            await websocket.send_json({"fleets": fleets_list})  # Ensure {fleets: [...]} format
            await asyncio.sleep(5)  # Send updates every 5 seconds
    except WebSocketDisconnect:
        print("Client disconnected")

#get total number of companies
@router.websocket("/ws/count-fleets")
async def websocket_count_fleets(websocket: WebSocket):
    await websocket.accept()
    collection = get_fleets_collection

    try:
        while True:
            await websocket.send_json({"total_fleets": collection.count_documents({})})
            await asyncio.sleep(5)  # Adjust interval as needed; sends update every 5s
    except WebSocketDisconnect:
        print("Client disconnected")

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
def update_fleet(fleet_id: str, payload: dict = Body(...)):
    """
    Update fields of a fleet (e.g., subscription_plan, is_active).
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

    result = collection.update_one(
        {"_id": ObjectId(fleet_id)},
        {"$set": update_fields}
    )

    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Fleet not found or not updated")

    updated = collection.find_one({"_id": ObjectId(fleet_id)})
    return fleets(updated)