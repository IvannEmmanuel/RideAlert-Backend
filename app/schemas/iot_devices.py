from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from enum import Enum

class IoTDeviceStatus(str, Enum):
    active = "active"
    inactive = "inactive"

class IoTDeviceBase(BaseModel):
    vehicle_id: Optional[str] = None
    is_active: IoTDeviceStatus
    device_name: Optional[str] = None

class IoTDeviceCreate(IoTDeviceBase):
    """Schema for creating a new IoT device entry."""
    pass

class IoTDevicePublic(IoTDeviceBase):
    id: str
    last_update: Optional[datetime] = None
    createdAt: Optional[datetime] = None
