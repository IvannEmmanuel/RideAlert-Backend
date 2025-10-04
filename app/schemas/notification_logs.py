from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class NotificationLogBase(BaseModel):
    message: str

class NotificationLogCreate(NotificationLogBase):
    user_id: str
    fleet_id: str

class NotificationLogPublic(NotificationLogBase):
    id: str
    user_id: str
    createdAt: datetime
    fleet_id: str
    vehicle_id: Optional[str] = None  # <-- make it optional