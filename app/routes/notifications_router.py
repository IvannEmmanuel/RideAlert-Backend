from fastapi import APIRouter, HTTPException, Depends, Body
from app.utils.notifications import send_proximity_notification
from app.dependencies.roles import user_required
from pydantic import BaseModel
import logging
from fastapi import APIRouter, HTTPException
from bson import ObjectId
from datetime import datetime
from app.database import notification_logs_collection
from app.models.notification_logs import notification_log_class
from app.schemas.notification_logs import NotificationLogCreate, NotificationLogPublic
from typing import List
from pytz import timezone

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notifications", tags=["Notifications"])

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


@router.post("/", response_model=NotificationLogPublic)
def create_notification_log(log: NotificationLogCreate):
    ph_tz = timezone("Asia/Manila")
    doc = {
        "user_id": ObjectId(log.user_id),
        "message": log.message,
        "createdAt": datetime.now(ph_tz).isoformat()
    }
    result = notification_logs_collection.insert_one(doc)
    new_log = notification_logs_collection.find_one({"_id": result.inserted_id})
    return notification_log_class(new_log)

@router.get("/user/{user_id}", response_model=List[NotificationLogPublic])
def get_user_notifications(user_id: str):
    logs = notification_logs_collection.find({"user_id": ObjectId(user_id)})
    return [notification_log_class(log) for log in logs]