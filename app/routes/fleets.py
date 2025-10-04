from fastapi import APIRouter, HTTPException, Body, Depends, WebSocket, WebSocketDisconnect, Form, File, UploadFile #Form file uploadfile added
from app.models.fleets import fleets
from app.schemas.fleets import FleetCreate, FleetPublic
from app.database import get_fleets_collection
from bson import ObjectId, Binary #binary added
from datetime import datetime
from typing import List, Dict, Optional
from app.dependencies.roles import super_admin_required
from app.utils.pasword_hashing import hash_password, verify_password
from app.utils.auth_token import create_access_token
from fastapi.encoders import jsonable_encoder
from app.schemas.fleets import SubscriptionPlan
from app.utils.ws_manager import fleet_all_manager, fleet_count_manager, fleet_details_manager
import json #added
from pydantic import ValidationError #added
import base64 #added
from fastapi.responses import StreamingResponse  #added
import io #added

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
    collection = get_fleets_collection()
    fleet_docs = collection.find({"role": {"$ne": "superadmin"}})
    fleets_list = [
        {
            key: serialize_datetime(value) if isinstance(value, (datetime, ObjectId)) else value
            for key, value in fleets(f).items()
        } for f in fleet_docs
    ]
    await fleet_all_manager.broadcast({"fleets": fleets_list})

async def broadcast_fleet_details(fleet_id: str):
    """Broadcast the details of a specific fleet to connected /fleet_id/ws clients."""
    collection = get_fleets_collection()
    fleet_doc = collection.find_one({"_id": ObjectId(fleet_id)})
    if fleet_doc:
        fleet_data = fleets(fleet_doc)
        serialized_data = {
            key: serialize_datetime(value) if isinstance(value, (datetime, ObjectId)) else value
            for key, value in fleet_data.items()
        }
        await fleet_details_manager.broadcast(serialized_data, fleet_id)

# @router.post("/", response_model=FleetPublic)
# async def create_fleet(payload: Optional[FleetCreate] = Body(None)):
#     """
#     Create a new fleet and broadcast fleet count and updated fleet list.
#     """
#     collection = get_fleets_collection

#     if not payload:
#         raise HTTPException(status_code=400, detail="Fleet data is required")

#     # company_code must be unique
#     if collection.find_one({"company_code": payload.company_code}):
#         raise HTTPException(status_code=400, detail="company_code already exists")

#     # at least one contact_info required
#     if not payload.contact_info or len(payload.contact_info) == 0:
#         raise HTTPException(status_code=400, detail="At least one contact_info entry is required")

#     email = payload.contact_info[0].email
#     if collection.find_one({"contact_info.email": email}):
#         raise HTTPException(status_code=400, detail="email already exists")

#     # convert payload → dict
#     doc = payload.dict()

#     # hash password
#     if "password" in doc and doc["password"]:
#         doc["password"] = hash_password(doc["password"])

#     now = datetime.utcnow()
#     doc.update({
#         "created_at": now,
#         "last_updated": now,
#         "role": "unverified",
#         "is_active": True,
#         "plan_price": plan_prices[doc["subscription_plan"]],
#         "max_vehicles": max_vehicles_limits[doc["subscription_plan"]]
#     })

#     result = collection.insert_one(doc)
#     created = collection.find_one({"_id": result.inserted_id})

#     # 🚀 Broadcast fleet count and fleet list after create
#     total_fleets = collection.count_documents({"role": {"$ne": "superadmin"}})
#     await fleet_count_manager.broadcast({"total_fleets": total_fleets})
#     await broadcast_fleet_list()

#     return fleets(created)

#newly added create
@router.post("/", response_model=FleetPublic)
async def create_fleet(
    data: str = Form(...),  # JSON string from frontend
    business_documents: Optional[List[UploadFile]] = File(None)  # now optional
):
    collection = get_fleets_collection

    # Parse and validate JSON against FleetCreate
    try:
        payload_obj = FleetCreate(**json.loads(data))
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors())

    # Uniqueness checks
    if collection.find_one({"company_code": payload_obj.company_code}):
        raise HTTPException(status_code=400, detail="company_code already exists")
    if collection.find_one({"contact_info.email": payload_obj.contact_info[0].email}):
        raise HTTPException(status_code=400, detail="email already exists")

    # Read uploaded PDFs into base64 strings
    pdf_files = []
    if business_documents:
        for file in business_documents:
            file_bytes = await file.read()
            pdf_files.append({
                "filename": file.filename,
                "content": base64.b64encode(file_bytes).decode("utf-8")
            })

    # Prepare document for MongoDB
    now = datetime.utcnow()
    doc = payload_obj.dict()
    doc.update({
        "created_at": now,
        "last_updated": now,
        "role": "unverified",
        "is_active": True,
        "plan_price": payload_obj.plan_price,
        "max_vehicles": payload_obj.max_vehicles,
        "password": hash_password(payload_obj.password),
        "pdf_files": pdf_files
    })

    # Insert into DB
    result = collection.insert_one(doc)
    created = collection.find_one({"_id": result.inserted_id})

    # Broadcast updates
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

@router.get("/all")
async def get_all_fleets():
    """
    Fetch all fleets once (excluding superadmin).
    """
    collection = get_fleets_collection
    fleet_docs = collection.find({"role": {"$ne": "superadmin"}})
    
    fleets_list = [
        {
            key: serialize_datetime(value) if isinstance(value, (datetime, ObjectId)) else value
            for key, value in fleets(f).items()
        }
        for f in fleet_docs
    ]
    return {"fleets": fleets_list}

@router.websocket("/{fleet_id}/ws")
async def websocket_fleet_details(websocket: WebSocket, fleet_id: str):
    """
    WebSocket endpoint to stream specific fleet details in real-time.
    """
    try:
        if not ObjectId.is_valid(fleet_id):
            await websocket.send_json({"error": "Invalid fleet ID format"})
            await websocket.close()
            return

        collection = get_fleets_collection
        fleet_doc = collection.find_one({"_id": ObjectId(fleet_id)})
        if not fleet_doc:
            await websocket.send_json({"error": "Fleet not found"})
            await websocket.close()
            return

        await fleet_details_manager.connect(websocket, fleet_id)

        # Send initial fleet details
        fleet_data = fleets(fleet_doc)
        serialized_data = {
            key: serialize_datetime(value) if isinstance(value, (datetime, ObjectId)) else value
            for key, value in fleet_data.items()
        }
        await websocket.send_json(serialized_data)

        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            fleet_details_manager.disconnect(websocket, fleet_id)
            print(f"Client disconnected from fleet {fleet_id} details")
        except Exception as e:
            fleet_details_manager.disconnect(websocket, fleet_id)
            print(f"Error in fleet details WebSocket for fleet {fleet_id}: {e}")
            await websocket.send_json({"error": str(e)})
            await websocket.close()

    except Exception as e:
        print(f"Unexpected error in fleet details WebSocket for fleet {fleet_id}: {e}")
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

@router.patch("/{fleet_id}/approve", dependencies=[Depends(super_admin_required)])
async def approve_fleet(fleet_id: str):
    """
    Approve a fleet registration by setting its role to 'admin' and updating timestamps.
    Only accessible by superadmin.
    """
    collection = get_fleets_collection

    if not ObjectId.is_valid(fleet_id):
        raise HTTPException(status_code=400, detail="Invalid fleet ID format")

    now = datetime.utcnow()
    result = collection.update_one(
        {"_id": ObjectId(fleet_id)},
        {"$set": {"role": "admin", "last_updated": now}}
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Fleet not found")

    updated_fleet = collection.find_one({"_id": ObjectId(fleet_id)})

    # Broadcast updated fleet list and count
    total_fleets = collection.count_documents({"role": {"$ne": "superadmin"}})
    await fleet_count_manager.broadcast({"total_fleets": total_fleets})
    await broadcast_fleet_list()
    await broadcast_fleet_details(fleet_id)

    return {
        "message": "Fleet approved successfully",
        "fleet": fleets(updated_fleet)
    }

@router.patch("/{fleet_id}/reject", dependencies=[Depends(super_admin_required)])
async def reject_fleet(fleet_id: str):
    """
    Reject a fleet registration by setting its role to 'rejected' and updating timestamps.
    Only accessible by superadmin.
    """
    collection = get_fleets_collection

    if not ObjectId.is_valid(fleet_id):
        raise HTTPException(status_code=400, detail="Invalid fleet ID format")

    now = datetime.utcnow()
    result = collection.update_one(
        {"_id": ObjectId(fleet_id)},
        {"$set": {"role": "rejected", "last_updated": now}}
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Fleet not found")

    updated_fleet = collection.find_one({"_id": ObjectId(fleet_id)})

    # Broadcast updated fleet list and count
    total_fleets = collection.count_documents({"role": {"$ne": "superadmin"}})
    await fleet_count_manager.broadcast({"total_fleets": total_fleets})
    await broadcast_fleet_list()
    await broadcast_fleet_details(fleet_id)

    return {
        "message": "Fleet rejected successfully",
        "fleet": fleets(updated_fleet)
    }

@router.get("/{fleet_id}/pdf/{filename}")
async def get_fleet_pdf(fleet_id: str, filename: str):
    collection = get_fleets_collection
    fleet = collection.find_one({"_id": ObjectId(fleet_id)})
    if not fleet:
        raise HTTPException(status_code=404, detail="Fleet not found")

    pdf_files = fleet.get("pdf_files", [])
    file_entry = next((f for f in pdf_files if f["filename"] == filename), None)
    if not file_entry:
        raise HTTPException(status_code=404, detail="PDF not found")

    # Decode base64 back to bytes
    pdf_bytes = base64.b64decode(file_entry["content"])

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )