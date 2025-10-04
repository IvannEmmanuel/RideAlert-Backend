#fleet_id ang kulang wala nako na set

from fastapi import APIRouter, HTTPException, Depends, Body
from app.utils.notifications import send_proximity_notification, send_fcm_notification
from app.dependencies.roles import user_required
from pydantic import BaseModel
import logging
from fastapi import APIRouter, HTTPException
from bson import ObjectId
from datetime import datetime
from app.database import notification_logs_collection, user_collection
from app.models.notification_logs import notification_log_class
from app.schemas.notification_logs import NotificationLogCreate, NotificationLogPublic
from typing import List
from pytz import timezone
from fastapi import WebSocket, WebSocketDisconnect, APIRouter
from typing import Dict
import json
import asyncio

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notifications", tags=["Notifications"])

user_notification_subscribers: Dict[str, List[WebSocket]] = {}
user_fleet_notification_subscribers: Dict[str, List[WebSocket]] = {}

class ProximityNotificationRequest(BaseModel):
    user_id: str
    vehicle_id: str
    distance: int

@router.post("/send-proximity")
async def send_proximity_alert(
    request: ProximityNotificationRequest,
    current_user: dict = Depends(user_required)
):
    """
    Send proximity notification to user
    """
    try:
        success = await send_proximity_notification(
            request.user_id,
            request.vehicle_id,
            request.distance
        )
        
        if success:
            return {"message": "Proximity notification has sent successfully"}
        else:
            return {"message": "Notification has sent (recent notification exists or error occurred)"}
            
    except Exception as e:
        logger.error(f"Error in sending_proximity_alert: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to send the notification")

#para ma sendan og notification ang specific user both background and foreground
@router.post("/test-fcm")
async def test_fcm_notification(
    user_id: str = Body(...),
    title: str = Body(...),
    body: str = Body(...),
    current_user: dict = Depends(user_required)
):
    """
    Test FCM notification
    """
    try:
        from app.utils.notifications import send_fcm_notification
        from app.database import user_collection
        from bson import ObjectId
        
        user_data = user_collection.find_one({"_id": ObjectId(user_id)})
        if not user_data:
            raise HTTPException(status_code=404, detail="User is not found")
            
        fcm_token = user_data.get("fcm_token")
        if not fcm_token:
            raise HTTPException(status_code=400, detail="No FCM token found")
        
        success = await send_fcm_notification(fcm_token, title, body)
        
        if success:
            return {"message": "Test notification sent successfully"}
        else:
            raise HTTPException(status_code=500, detail="Failed to send the test notification on the specific user")
            
    except Exception as e:
        logger.error(f"Error in test_fcm_notification: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

#para mag create og notification then matik na dayon siya mo send og notification didto sa specific user (test-fcm combination)
@router.post("/", response_model=NotificationLogPublic)
async def create_notification_log(log: NotificationLogCreate):
    ph_tz = timezone("Asia/Manila")
    doc = {
        "user_id": ObjectId(log.user_id),
        "fleet_id": ObjectId(log.fleet_id),  # add fleet_id here
        "message": log.message,
        "createdAt": datetime.now(ph_tz).isoformat()
    }

    # Save to DB
    result = notification_logs_collection.insert_one(doc)
    new_log = notification_logs_collection.find_one({"_id": result.inserted_id})
    public_log = notification_log_class(new_log)

    user_fleet_key = f"{str(log.user_id)}:{str(log.fleet_id)}"  # user+fleet key

    # 🔔 Broadcast via WebSocket
    if user_fleet_key in user_fleet_notification_subscribers:
        for ws in user_fleet_notification_subscribers[user_fleet_key]:
            try:
                await ws.send_text(json.dumps(public_log))
            except Exception as e:
                print(f"Error sending WebSocket notification to {user_fleet_key}: {e}")

    # 📱 Send FCM push notification asynchronously
    async def send_fcm_async():
        try:
            user_data = user_collection.find_one({"_id": ObjectId(log.user_id)})
            if user_data:
                fcm_token = user_data.get("fcm_token")
                if fcm_token:
                    await send_fcm_notification(
                        fcm_token,
                        title="New Notification",
                        body=log.message
                    )
        except Exception as e:
            print(f"Error sending FCM notification to {user_fleet_key}: {e}")

    asyncio.create_task(send_fcm_async())

    return public_log


#para makita ang tanan nga notification sa specific na user.
@router.get("/user/{user_id}/{fleet_id}", response_model=List[NotificationLogPublic])
def get_user_notifications(user_id: str, fleet_id: str):
    try:
        user_obj_id = ObjectId(user_id)
        fleet_obj_id = ObjectId(fleet_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid user_id or fleet_id format")

    logs = notification_logs_collection.find({
        "user_id": user_obj_id,
        "fleet_id": fleet_obj_id
    })

    return [notification_log_class(log) for log in logs]

#to provide real-time updates from the /user/{user_id}
@router.websocket("/user/{user_id}/{fleet_id}/ws")
async def websocket_user_notifications(websocket: WebSocket, user_id: str, fleet_id: str):
    await websocket.accept()
    user_fleet_key = f"{user_id}:{fleet_id}"

    if user_fleet_key not in user_fleet_notification_subscribers:
        user_fleet_notification_subscribers[user_fleet_key] = []

    user_fleet_notification_subscribers[user_fleet_key].append(websocket)
    print(f"WebSocket connected for user+fleet {user_fleet_key}")

    try:
        while True:
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        print(f"WebSocket disconnected for {user_fleet_key}")
        user_fleet_notification_subscribers[user_fleet_key].remove(websocket)
        if not user_fleet_notification_subscribers[user_fleet_key]:
            del user_fleet_notification_subscribers[user_fleet_key]