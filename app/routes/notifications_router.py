from fastapi import APIRouter, HTTPException, Depends, Body
from app.utils.notifications import send_proximity_notification
from app.dependencies.roles import user_required
from pydantic import BaseModel
import logging

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
    Send proximity notification to user when vehicle is nearby
    """
    try:
        success = await send_proximity_notification(
            request.user_id,
            request.vehicle_id,
            request.distance
        )
        
        if success:
            return {"message": "Proximity notification sent successfully"}
        else:
            return {"message": "Notification not sent (recent notification exists or error occurred)"}
            
    except Exception as e:
        logger.error(f"Error in send_proximity_alert: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to send notification")

@router.post("/test-fcm")
async def test_fcm_notification(
    user_id: str = Body(...),
    title: str = Body(...),
    body: str = Body(...),
    current_user: dict = Depends(user_required)
):
    """
    Test FCM notification for debugging purposes
    """
    try:
        from app.utils.notifications import send_fcm_notification
        from app.database import user_collection
        from bson import ObjectId
        
        user_data = user_collection.find_one({"_id": ObjectId(user_id)})
        if not user_data:
            raise HTTPException(status_code=404, detail="User not found")
            
        fcm_token = user_data.get("fcm_token")
        if not fcm_token:
            raise HTTPException(status_code=400, detail="No FCM token found for that user")
        
        success = await send_fcm_notification(fcm_token, title, body)
        
        if success:
            return {"message": "Test notification has been sent successfully"}
        else:
            raise HTTPException(status_code=500, detail="Failed to send the test notification")
            
    except Exception as e:
        logger.error(f"Error in test_fcm_notification: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))