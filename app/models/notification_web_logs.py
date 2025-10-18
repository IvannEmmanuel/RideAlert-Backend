# app/models/notification.py
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from bson import ObjectId

class NotificationCreate(BaseModel):
    title: str
    description: str
    type: str  # 'route_added', 'vehicle_alert', etc.
    recipient_roles: List[str]  # ['superadmin', 'admin'] or ['all']
    recipient_ids: Optional[List[str]] = None  # Specific user IDs
    data: Optional[dict] = None

class NotificationResponse(BaseModel):
    id: str
    title: str
    description: str
    type: str
    recipient_roles: List[str]
    recipient_ids: Optional[List[str]]
    is_read: bool
    created_at: datetime
    data: Optional[dict]