from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

class NotificationLogBase(BaseModel):
    message: Optional[str] = Field(default=None, description="Notification message")

class NotificationLogCreate(NotificationLogBase):
    user_id: str
    fleet_id: str
    message: str  # Keep required for creates

class NotificationLogPublic(NotificationLogBase):
    id: str
    user_id: str
    createdAt: datetime
    fleet_id: str
    vehicle_id: Optional[str] = None  # <-- make it optional