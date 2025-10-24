from fastapi import APIRouter, HTTPException, Body, Depends, WebSocket, WebSocketDisconnect, Form, File, UploadFile #Form file uploadfile added
from app.models.fleets import fleets
from app.schemas.fleets import FleetCreate, FleetPublic
from app.database import get_fleets_collection, vehicle_collection
from bson import ObjectId, Binary #binary added
from datetime import datetime
from typing import List, Dict, Optional
from app.dependencies.roles import super_admin_required
from app.utils.pasword_hashing import hash_password, verify_password
from app.utils.auth_token import create_access_token, create_refresh_token, verify_refresh_token
from fastapi.encoders import jsonable_encoder
# from app.schemas.fleets import SubscriptionPlan
from app.utils.ws_manager import fleet_all_manager, fleet_count_manager, fleet_details_manager
import json #added
from pydantic import ValidationError, BaseModel #added
import base64 #added
from fastapi.responses import StreamingResponse  #added
import io #added
from app.utils.email_sender import approval_email_sender, rejection_email_sender  # Add this import
from app.database import get_subscription_plans_collection
from app.models.subscription_plans import subscription_plan_entity

router = APIRouter(prefix="/fleets", tags=["Fleets"])

class RefreshTokenRequest(BaseModel):
    refresh_token: str

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
    fleet_docs = list(collection.find({"role": {"$ne": "superadmin"}}))

    # Build a map of vehicle counts per fleet_id (stringified) using aggregation for performance
    try:
        counts_cursor = vehicle_collection.aggregate([
            {"$group": {"_id": {"$toString": "$fleet_id"}, "count": {"$sum": 1}}}
        ])
        counts_map = {doc["_id"]: doc["count"] for doc in counts_cursor}
    except Exception:
        # Fallback: empty map on any aggregation error
        counts_map = {}

    fleets_list = [
        {
            **{
                key: serialize_datetime(value) if isinstance(value, (datetime, ObjectId)) else value
                for key, value in fleets(f).items()
            },
            "vehicle_count": counts_map.get(str(f.get("_id")), 0)
        } for f in fleet_docs
    ]

    await fleet_all_manager.broadcast({"fleets": fleets_list})

async def broadcast_fleet_details(fleet_id: str):
    """Broadcast the details of a specific fleet to connected /fleet_id/ws clients."""
    collection = get_fleets_collection
    fleet_doc = collection.find_one({"_id": ObjectId(fleet_id)})
    if fleet_doc:
        fleet_data = fleets(fleet_doc)
        serialized_data = {
            key: serialize_datetime(value) if isinstance(value, (datetime, ObjectId)) else value
            for key, value in fleet_data.items()
        }
        # Attach total vehicles for this fleet (handle string/ObjectId stored fleet_id)
        try:
            try:
                oid = ObjectId(fleet_id)
                total = vehicle_collection.count_documents({"$or": [{"fleet_id": oid}, {"fleet_id": fleet_id}]})
            except Exception:
                total = vehicle_collection.count_documents({"fleet_id": fleet_id})
        except Exception:
            total = 0

        serialized_data["vehicle_count"] = total
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

@router.websocket("/ws/all")
async def websocket_all_fleets(websocket: WebSocket):
    """
    WebSocket endpoint to stream all fleets in real-time.
    """
    await fleet_all_manager.connect(websocket)
    
    try:
        # Send initial fleet list right after connect
        collection = get_fleets_collection
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
        print("Client disconnected from all fleets WebSocket")
    except Exception as e:
        fleet_all_manager.disconnect(websocket)
        print(f"Error in all fleets WebSocket: {e}")
        await websocket.close()

#newly added create
@router.post("/", response_model=FleetPublic)
async def create_fleet(
    data: str = Form(...),
    business_documents: Optional[List[UploadFile]] = File(None)
):
    """
    Create a new fleet with subscription plan validation.
    The subscription_plan field should be the plan_code (e.g., "BASIC", "PREMIUM").
    """
    collection = get_fleets_collection
    plans_collection = get_subscription_plans_collection

    # Parse and validate JSON
    try:
        payload_obj = FleetCreate(**json.loads(data))
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors())

    # Validate subscription plan exists and is active
    plan = plans_collection.find_one({
        "plan_code": payload_obj.subscription_plan.upper(),
        "is_active": True
    })
    
    if not plan:
        raise HTTPException(
            status_code=400, 
            detail=f"Subscription plan '{payload_obj.subscription_plan}' not found or inactive"
        )

    # Uniqueness checks
    if collection.find_one({"company_code": payload_obj.company_code}):
        raise HTTPException(status_code=400, detail="company_code already exists")
    if collection.find_one({"contact_info.email": payload_obj.contact_info[0].email}):
        raise HTTPException(status_code=400, detail="email already exists")

    # Read uploaded PDFs
    pdf_files = []
    if business_documents:
        for file in business_documents:
            file_bytes = await file.read()
            pdf_files.append({
                "filename": file.filename,
                "content": base64.b64encode(file_bytes).decode("utf-8")
            })

    # Prepare document with subscription plan details
    now = datetime.utcnow()
    doc = payload_obj.dict()
    doc.update({
        "created_at": now,
        "last_updated": now,
        "role": "unverified",
        "is_active": True,
        "subscription_plan": plan["plan_code"],  # Store plan code
        "plan_price": plan["price"],  # Get from subscription plan
        "max_vehicles": plan["max_vehicles"],  # Get from subscription plan
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

# Also add this helper endpoint to get available plans for registration
@router.get("/available-plans")
async def get_available_subscription_plans():
    """
    Get all active subscription plans for fleet registration.
    Public endpoint - no authentication required.
    """
    
    plans_collection = get_subscription_plans_collection
    plans = list(plans_collection.find({"is_active": True}).sort("price", 1))
    
    return {
        "plans": [subscription_plan_entity(plan) for plan in plans]
    }

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
    refresh_token = create_refresh_token(token_data)

    fleet_data = fleets(fleet)
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "message": "Login successful",
        "fleet": fleet_data
    }

@router.post("/refresh")
async def refresh_access_token(request: RefreshTokenRequest):
    """
    Refresh an access token using a refresh token.
    
    Expected request body:
    {
        "refresh_token": "your_refresh_token_here"
    }
    """
    refresh_token = request.refresh_token
    
    if not refresh_token:
        raise HTTPException(status_code=400, detail="refresh_token is required")

    payload = verify_refresh_token(refresh_token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    new_access_token = create_access_token({
        "fleet_id": payload["fleet_id"],
        "email": payload["email"],
        "role": payload["role"],
    })

    return {
        "access_token": new_access_token,
        "token_type": "bearer"
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

@router.get("/admin")
async def get_admin_fleets():
    """
    Fetch only fleets with role = 'admin'.
    """
    collection = get_fleets_collection
    fleet_docs = collection.find({"role": "admin"})
    
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

@router.get("/code/{company_code}")
async def get_fleet_by_code(company_code: str):
    """
    Get a fleet by company code (used for route registration)
    """
    try:
        collection = get_fleets_collection
        fleet = collection.find_one({"company_code": company_code})
        
        if not fleet:
            raise HTTPException(status_code=404, detail="Fleet not found")
        
        # Convert ObjectId to string for JSON serialization
        fleet["_id"] = str(fleet["_id"])
        
        return fleet
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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

@router.patch("/{fleet_id}/approve")
async def approve_fleet(fleet_id: str, current_user: dict = Depends(super_admin_required)):
    """
    Approve a fleet registration by setting its role to 'admin' and updating timestamps.
    Only accessible by superadmin.
    """
    try:
        print(f"🔧 Starting fleet approval for: {fleet_id}")
        
        collection = get_fleets_collection

        if not ObjectId.is_valid(fleet_id):
            raise HTTPException(status_code=400, detail="Invalid fleet ID format")

        # Get the fleet data first to extract email
        fleet = collection.find_one({"_id": ObjectId(fleet_id)})
        if not fleet:
            raise HTTPException(status_code=404, detail="Fleet not found")

        print(f"📋 Found fleet: {fleet.get('company_name')}")
        
        now = datetime.utcnow()
        # Record approver information
        approver = current_user.get("email") or current_user.get("user_id") or current_user.get("id")
        update_payload = {
            "role": "admin", 
            "last_updated": now, 
            "approved_by": approver, 
            "approved_in": now,
            "is_active": True
        }
        
        print(f"🔄 Updating fleet with: {update_payload}")
        
        result = collection.update_one(
            {"_id": ObjectId(fleet_id)},
            {"$set": update_payload}
        )

        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Fleet not found")

        updated_fleet = collection.find_one({"_id": ObjectId(fleet_id)})
        print(f"✅ Fleet updated successfully")

        # Send approval email
        email_sent = False
        company_email = None
        
        try:
            # Extract company email from fleet data
            contact_info = fleet.get('contact_info', [{}])
            print(f"📧 Contact info: {contact_info}")
            
            if contact_info and isinstance(contact_info, list) and len(contact_info) > 0:
                company_email = contact_info[0].get('email')
            
            company_name = fleet.get('company_name', 'Valued Customer')
            print(f"📧 Company email: {company_email}, Name: {company_name}")
            
            if company_email and company_email != "N/A" and company_email != "N/A":
                print(f"📨 Attempting to send approval email to: {company_email}")
                # Send approval email
                email_sent = approval_email_sender.send_approval_email(
                    company_email=company_email,
                    company_name=company_name,
                    login_credentials={
                        'email': company_email,
                        'company_name': company_name,
                        'login_url': 'https://ridealertadminpanel.onrender.com'
                    }
                )
                
                if email_sent:
                    print(f"✅ Approval email sent to {company_email}")
                else:
                    print(f"⚠️ Fleet approved but failed to send email to {company_email}")
            else:
                print(f"⚠️ No valid email found for fleet {fleet_id}")
                
        except Exception as e:
            print(f"❌ Error in email sending: {str(e)}")
            import traceback
            traceback.print_exc()
            # Don't raise error - fleet is still approved even if email fails

        # Broadcast updated fleet list and count
        print("🔄 Broadcasting fleet updates...")
        total_fleets = collection.count_documents({"role": {"$ne": "superadmin"}})
        await fleet_count_manager.broadcast({"total_fleets": total_fleets})
        await broadcast_fleet_list()
        await broadcast_fleet_details(fleet_id)

        print(f"🎉 Fleet approval completed for {fleet_id}")
        
        return {
            "message": "Fleet approved successfully",
            "fleet": fleets(updated_fleet),
            "email_sent": email_sent,
            "company_email": company_email
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ CRITICAL ERROR in approve_fleet: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )

@router.patch("/{fleet_id}/reject")
async def reject_fleet(fleet_id: str, current_user: dict = Depends(super_admin_required)):
    """
    Reject a fleet registration - simple version without rejection reason
    """
    collection = get_fleets_collection

    if not ObjectId.is_valid(fleet_id):
        raise HTTPException(status_code=400, detail="Invalid fleet ID format")

    # Get the fleet data first to extract email
    fleet = collection.find_one({"_id": ObjectId(fleet_id)})
    if not fleet:
        raise HTTPException(status_code=404, detail="Fleet not found")

    now = datetime.utcnow()
    rejecter = current_user.get("email") or current_user.get("user_id") or current_user.get("id")
    update_payload = {
        "role": "rejected", 
        "last_updated": now, 
        "rejected_by": rejecter, 
        "rejected_in": now
    }
    
    result = collection.update_one(
        {"_id": ObjectId(fleet_id)},
        {"$set": update_payload}
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Fleet not found")

    updated_fleet = collection.find_one({"_id": ObjectId(fleet_id)})

    # Send rejection email
    email_sent = False
    company_email = None
    
    try:
        contact_info = fleet.get('contact_info', [{}])
        if contact_info and isinstance(contact_info, list) and len(contact_info) > 0:
            company_email = contact_info[0].get('email')
        company_name = fleet.get('company_name', 'Valued Customer')
        
        if company_email and company_email != "N/A":
            email_sent = rejection_email_sender.send_rejection_email(
                company_email=company_email,
                company_name=company_name
            )
            
    except Exception as e:
        print(f"Error sending rejection email: {e}")

    # Broadcast updates
    total_fleets = collection.count_documents({"role": {"$ne": "superadmin"}})
    await fleet_count_manager.broadcast({"total_fleets": total_fleets})
    await broadcast_fleet_list()
    await broadcast_fleet_details(fleet_id)

    return {
        "message": "Fleet rejected successfully",
        "fleet": fleets(updated_fleet),
        "email_sent": email_sent,
        "company_email": company_email
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