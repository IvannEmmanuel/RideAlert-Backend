from fastapi import APIRouter, HTTPException, Depends, Body, WebSocket, WebSocketDisconnect
from app.schemas.user import UserCreate, UserInDB, UserLogin, Location
from app.database import user_collection, vehicle_collection
from app.models.user import user_helper
from app.schemas.user import Location as UserLocation  # Adjust import if needed
from bson import ObjectId
from pydantic import BaseModel, ValidationError
from app.utils.pasword_hashing import hash_password
from app.utils.pasword_hashing import verify_password
from app.utils.haversine import haversine_code
from app.utils.notifications import check_and_notify
from app.utils.auth_token import create_access_token
from fastapi.responses import JSONResponse
from app.dependencies.roles import admin_required, user_required, user_or_admin_required, super_admin_required
from app.utils.ws_manager import user_count_manager
import asyncio
import logging

class LocationUpdate(BaseModel):
    latitude: float
    longitude: float
    # Add accuracy, timestamp if needed

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["Users"])

@router.post("/register", response_model=UserInDB)
async def create_user(user: UserCreate):
    if user_collection.find_one({"email": user.email}):
        raise HTTPException(status_code=400, detail="Email already registered")

    user_dict = user.dict()
    user_dict["password"] = hash_password(user.password)  # hash here
    user_dict["role"] = user.role or "user"

    result = user_collection.insert_one(user_dict)
    created_user = user_collection.find_one({"_id": result.inserted_id})

    # 🚀 Broadcast user count after create
    total_users = user_collection.count_documents({})
    await user_count_manager.broadcast({"total_users": total_users})

    return user_helper(created_user)

@router.get("/{user_id}", response_model=UserInDB)
def get_user(user_id: str, current_user: dict = Depends(user_or_admin_required)):
    user = user_collection.find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user_helper(user)

@router.post("/login")
def login_user(login_data: UserLogin):
    user = user_collection.find_one({"email": login_data.email})

    if not user or not verify_password(login_data.password, user["password"]):
        raise HTTPException(status_code=401, detail="email or password is invalid")

    token_data = {
        "user_id": str(user["_id"]),
        "email": user["email"],
        "role": user["role"]
    }

    access_token = create_access_token(token_data)

    return JSONResponse(content={
        "access_token": access_token,
        "user": {
            "id": str(user["_id"]),
            "first_name": user.get("first_name"),
            "last_name": user.get("last_name"),
            "email": user.get("email"),
            "gender": user.get("gender"),
            "address": user.get("address"),
            "role": user.get("role"),
            "location": user.get("location", {}),
            "fleet_id": user.get("fleet_id")
        }
    })

@router.post("/location")
async def update_user_location_http(
    location_update: LocationUpdate,
    current_user: dict = Depends(user_required)  # e.g., {"user_id": "user_id", "role": "user"}
):
    logger.info(f"📍 Location update received: {location_update.dict()}")
    logger.info(f"🔑 Current user from dep: {current_user}")  # Debug: See structure
    
    # 🛠️ Fix: Extract user_id safely (includes 'user_id' from your logs)
    user_id = (
        current_user.get('user_id') or  # Your actual key
        current_user.get('id') or 
        current_user.get('sub') or 
        current_user.get('_id')
    )
    if not user_id:
        logger.error(f"❌ No user ID in current_user: {current_user}")
        raise HTTPException(status_code=401, detail="Invalid token: Missing user ID")
    
    user_id = str(user_id)  # Ensure string
    oid = ObjectId(user_id)
    logger.info(f"👤 Extracted user_id: {user_id}")
    
    # Create Location object (assume UserLocation schema exists; fallback to dict)
    try:
        from app.schemas.user import Location as UserLocation  # Adjust if path differs
        location = UserLocation(latitude=location_update.latitude, longitude=location_update.longitude)
    except (ImportError, ValidationError):
        # Fallback: Simple dict if schema not available
        location = {"latitude": location_update.latitude, "longitude": location_update.longitude}
        logger.warning("⚠️ Using dict fallback for location")
    
    # Fetch user from DB (ensures fleet_id exists)
    user = user_collection.find_one({"_id": oid})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if not user.get("fleet_id"):
        raise HTTPException(status_code=400, detail="User missing fleet_id")
    
    fleet_id = user["fleet_id"]
    
    # Update DB location
    result = user_collection.update_one(
        {"_id": oid},
        {"$set": {"location": location if isinstance(location, dict) else location.dict()}}
    )
    
    if result.modified_count == 0:
        logger.info(f"📍 No change in location for {user_id} (same as before)")
    else:
        logger.info(f"💾 Location updated in DB for {user_id}")
    
    # Always run proximity checks, even if no DB change (user might have moved slightly)
    
    # Trigger proximity checks
    try:
        # Query available vehicles in fleet with valid locations
        fleet_query = {
            "fleet_id": fleet_id,
            "status": "available",
            "$or": [
                {"location.latitude": {"$exists": True, "$ne": None}},
                {"location.longitude": {"$exists": True, "$ne": None}}
            ]
        }
        vehicles = list(vehicle_collection.find(fleet_query).limit(50))  # Limit for perf
        
        logger.info(f"🔍 Found {len(vehicles)} available vehicles for fleet {fleet_id}")
        
        notified_count = 0
        for vehicle in vehicles:
            vehicle_id = str(vehicle["_id"])
            vehicle_loc = vehicle.get("location")
            if vehicle_loc and vehicle_loc.get("latitude") is not None and vehicle_loc.get("longitude") is not None:
                success = await check_and_notify(
                    user_id,
                    type("UserLoc", (), {"latitude": location_update.latitude, "longitude": location_update.longitude})(),
                    type("VehicleLoc", (), vehicle_loc)(),
                    vehicle_id
                )
                if success:
                    notified_count += 1
                    logger.info(f"🔔 Tiered notification triggered for vehicle {vehicle_id}")
        
        logger.info(f"✅ Proximity checks complete: {notified_count} tiered notifications sent")
        return {"message": f"Location processed. {notified_count} tiered notifications sent."}
        
    except Exception as e:
        logger.error(f"💥 Proximity check error for {user_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Proximity check failed: {str(e)}")
    
@router.post("/fcm-token")
async def save_fcm_token(
    user_id: str = Body(...),
    fcm_token: str = Body(...)
):
    result = user_collection.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"fcm_token": fcm_token}}
    )
    if result.matched_count == 1:
        if result.modified_count == 1:
            return {"message": "FCM token updated"}
        else:
            return {"message": "FCM token already up-to-date"}
    raise HTTPException(status_code=404, detail="User not found")

@router.delete("/fcm-token")
async def clear_fcm_token(user_id: str):
    result = user_collection.update_one(
        {"_id": ObjectId(user_id)},
        {"$unset": {"fcm_token": ""}}
    )
    if result.matched_count == 1:
        return {"message": "FCM token cleared"}
    raise HTTPException(status_code=404, detail="User not found")

@router.delete("/{user_id}")
async def delete_user(user_id: str, current_user: dict = Depends(super_admin_required)):
    """
    Delete a user and broadcast user count.
    """
    result = user_collection.delete_one({"_id": ObjectId(user_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="User not found")

    # 🚀 Broadcast user count after delete
    total_users = user_collection.count_documents({})
    await user_count_manager.broadcast({"total_users": total_users})

    return {"message": "User deleted"}

@router.websocket("/ws/count-users")
async def websocket_count_users(websocket: WebSocket):
    await user_count_manager.connect(websocket)
    collection = user_collection

    # Send initial count right after connect
    total_users = collection.count_documents({})
    await websocket.send_json({"total_users": total_users})

    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        user_count_manager.disconnect(websocket)
        print("Client disconnected from /ws/count-users")