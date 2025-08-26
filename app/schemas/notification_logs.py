from pydantic import BaseModel
from datetime import datetime

class NotificationLogBase(BaseModel):
    message: str

class NotificationLogCreate(NotificationLogBase):
    user_id: str

class NotificationLogPublic(NotificationLogBase):
    id: str
    user_id: str
    createdAt: datetime
