from fastapi import APIRouter, HTTPException, Depends, Body, WebSocket, WebSocketDisconnect
from app.schemas.user import UserCreate, UserInDB, UserLogin, Location
from app.database import user_collection, vehicle_collection
from app.models.user import user_helper
from app.schemas.user import Location as UserLocation
from bson import ObjectId
from pydantic import BaseModel, ValidationError
from app.utils.pasword_hashing import hash_password, verify_password
from app.utils.auth_token import create_access_token
from fastapi.responses import JSONResponse
from app.dependencies.roles import admin_required, user_required, user_or_admin_required, super_admin_required
from app.utils.ws_manager import user_count_manager
import logging

class LocationUpdate(BaseModel):
    latitude: float
    longitude: float

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["Users"])

@router.post("/register", response_model=UserInDB)
async def create_user(user: UserCreate):
    if user_collection.find_one({"email": user.email}):
        raise HTTPException(status_code=400, detail="Email already registered")

    user_dict = user.dict()
    user_dict["password"] = hash_password(user.password)
    user_dict["role"] = user.role or "user"

    result = user_collection.insert_one(user_dict)
    created_user = user_collection.find_one({"_id": result.inserted_id})

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
            "fleet_id": user.get("fleet_id"),
            "notify": user.get("notify", False),  # ✅ Include notify status
            "selected_vehicle_id": user.get("selected_vehicle_id")  # ✅ Include selected vehicle
        }
    })

@router.post("/location")
async def update_user_location_http(
    location_update: LocationUpdate,
    current_user: dict = Depends(user_required)
):
    """
    OPTIONAL ENDPOINT: Update user location manually.
    Background worker will handle notifications automatically based on stored locations.
    This endpoint is kept for frontend convenience but is NOT required for notifications.
    """
    logger.info(f"📍 Manual location update received: {location_update.dict()}")
    
    # Extract user_id
    user_id = (
        current_user.get('user_id') or
        current_user.get('id') or
        current_user.get('sub') or
        current_user.get('_id')
    )
    if not user_id:
        logger.error(f"❌ No user ID in current_user: {current_user}")
        raise HTTPException(status_code=401, detail="Invalid token: Missing user ID")
    
    user_id = str(user_id)
    oid = ObjectId(user_id)
    logger.info(f"👤 Extracted user_id: {user_id}")
    
    # Create Location object
    try:
        location = UserLocation(
            latitude=location_update.latitude,
            longitude=location_update.longitude
        )
    except (ImportError, ValidationError):
        location = {
            "latitude": location_update.latitude,
            "longitude": location_update.longitude
        }
        logger.warning("⚠️ Using dict fallback for location")
    
    # Fetch user from DB
    user = user_collection.find_one({"_id": oid})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if not user.get("fleet_id"):
        raise HTTPException(status_code=400, detail="User missing fleet_id")
    
    # Update DB location
    result = user_collection.update_one(
        {"_id": oid},
        {"$set": {"location": location if isinstance(location, dict) else location.dict()}}
    )
    
    if result.modified_count == 0:
        logger.info(f"📍 No change in location for {user_id} (same as before)")
    else:
        logger.info(f"💾 Location updated in DB for {user_id}")
    
    return {
        "message": "Location updated successfully. Background worker will handle notifications automatically."
    }
    
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

@router.post("/toggle-notify")
async def toggle_notify(
    notify: bool = Body(...),
    vehicle_id: str = Body(None),
    current_user: dict = Depends(user_required)
):
    """
    Toggle notification status for user.
    When notify=True, user will receive proximity notifications.
    When notify=False, user will not receive notifications.
    Optionally track which vehicle the user selected.
    """
    user_id = (
        current_user.get('user_id') or
        current_user.get('id') or
        current_user.get('sub') or
        current_user.get('_id')
    )
    
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token: Missing user ID")
    
    user_id = str(user_id)
    
    update_data = {"notify": notify}
    
    # Optionally store which vehicle user wants notifications for
    if vehicle_id:
        update_data["selected_vehicle_id"] = vehicle_id
    elif not notify:
        # Clear selected vehicle when turning off notifications
        update_data["selected_vehicle_id"] = None
    
    result = user_collection.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": update_data}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    
    status = "enabled" if notify else "disabled"
    logger.info(f"🔔 Notifications {status} for user {user_id}")
    
    return {
        "message": f"Notifications {status}",
        "notify": notify,
        "vehicle_id": vehicle_id
    }

@router.delete("/{user_id}")
async def delete_user(user_id: str, current_user: dict = Depends(super_admin_required)):
    """
    Delete a user and broadcast user count.
    """
    result = user_collection.delete_one({"_id": ObjectId(user_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="User not found")

    total_users = user_collection.count_documents({})
    await user_count_manager.broadcast({"total_users": total_users})

    return {"message": "User deleted"}

@router.websocket("/ws/count-users")
async def websocket_count_users(websocket: WebSocket):
    await user_count_manager.connect(websocket)
    collection = user_collection

    total_users = collection.count_documents({})
    await websocket.send_json({"total_users": total_users})

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        user_count_manager.disconnect(websocket)
        print("Client disconnected from /ws/count-users")