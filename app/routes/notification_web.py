# app/routes/notifications.py
from fastapi import APIRouter, HTTPException, Depends
from app.database import notifications_collection
from app.models.notification_web_logs import NotificationCreate, NotificationResponse
from app.dependencies.roles import super_and_admin_required
from bson import ObjectId
from datetime import datetime

router = APIRouter(prefix="/notifications", tags=["Notifications"])

@router.post("/", response_model=dict)
async def create_notification(
    notification: NotificationCreate,
    current_user: dict = Depends(super_and_admin_required)
):
    """Create a new notification and store it in database"""
    try:
        notification_data = {
            "title": notification.title,
            "description": notification.description,
            "type": notification.type,
            "recipient_roles": notification.recipient_roles,
            "recipient_ids": notification.recipient_ids or [],
            "data": notification.data,
            "is_read": False,
            "created_at": datetime.utcnow(),
            "created_by": current_user.get("id") if current_user else "system"
        }
        
        result = notifications_collection.insert_one(notification_data)
        
        return {
            "success": True, 
            "notification_id": str(result.inserted_id),
            "message": "Notification created successfully"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/", response_model=dict)
async def get_user_notifications(
    current_user: dict = Depends(super_and_admin_required),
    skip: int = 0,
    limit: int = 50
):
    """Get notifications for current user based on their role and ID"""
    try:
        user_id = current_user.get("id")
        user_role = current_user.get("role", "")
        
        # Build query: user should see notifications for their role OR specific to their user ID
        query = {
            "$or": [
                {"recipient_roles": "all"},
                {"recipient_roles": user_role},
                {"recipient_roles": {"$in": [user_role]}},
                {"recipient_ids": user_id},
                {"recipient_ids": {"$in": [user_id]}}
            ]
        }
        
        # Get total count for unread
        total_count = notifications_collection.count_documents(query)
        unread_count = notifications_collection.count_documents({**query, "is_read": False})
        
        # Get notifications
        notifications = list(notifications_collection.find(query)
            .sort("created_at", -1)
            .skip(skip)
            .limit(limit))
        
        # Convert to response format
        response_notifications = []
        for notif in notifications:
            response_notifications.append({
                "id": str(notif["_id"]),
                "title": notif["title"],
                "description": notif["description"],
                "type": notif["type"],
                "is_read": notif.get("is_read", False),
                "created_at": notif["created_at"],
                "data": notif.get("data")
            })
        
        return {
            "success": True,
            "notifications": response_notifications,
            "total_count": total_count,
            "unread_count": unread_count,
            "has_more": len(notifications) == limit
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{notification_id}/read", response_model=dict)
async def mark_notification_read(
    notification_id: str,
    current_user: dict = Depends(super_and_admin_required)
):
    """Mark a specific notification as read"""
    try:
        result = notifications_collection.update_one(
            {"_id": ObjectId(notification_id)},
            {"$set": {"is_read": True}}
        )
        
        if result.modified_count == 0:
            raise HTTPException(status_code=404, detail="Notification not found")
        
        return {
            "success": True, 
            "message": "Notification marked as read"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/read-all", response_model=dict)
async def mark_all_notifications_read(
    current_user: dict = Depends(super_and_admin_required)
):
    """Mark all notifications as read for current user"""
    try:
        user_id = current_user.get("id")
        user_role = current_user.get("role", "")
        
        query = {
            "$or": [
                {"recipient_roles": "all"},
                {"recipient_roles": user_role},
                {"recipient_roles": {"$in": [user_role]}},
                {"recipient_ids": user_id},
                {"recipient_ids": {"$in": [user_id]}}
            ],
            "is_read": False
        }
        
        result = notifications_collection.update_many(
            query,
            {"$set": {"is_read": True}}
        )
        
        return {
            "success": True,
            "message": f"Marked {result.modified_count} notifications as read"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{notification_id}", response_model=dict)
async def delete_notification(
    notification_id: str,
    current_user: dict = Depends(super_and_admin_required)
):
    """Delete a specific notification"""
    try:
        result = notifications_collection.delete_one({"_id": ObjectId(notification_id)})
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Notification not found")
        
        return {
            "success": True,
            "message": "Notification deleted successfully"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))