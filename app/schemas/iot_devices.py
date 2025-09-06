from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from enum import Enum

class IoTDeviceStatus(str, Enum):
    active = "active"
    inactive = "inactive"

class IoTDeviceModel(str, Enum):
    test_prod = "Test For Production"

class IoTDeviceBase(BaseModel):
    vehicle_id: Optional[str] = None
    is_active: IoTDeviceStatus
    device_name: Optional[str] = None
    device_model: Optional[IoTDeviceModel] = None
    company_name: Optional[str] = None
    notes: Optional[str] = None

class IoTDeviceCreate(IoTDeviceBase):
    """Schema for creating a new IoT device entry."""
    pass

class IoTDevicePublic(IoTDeviceBase):
    id: str
    device_model: Optional[str] = None
    last_update: Optional[datetime] = None
    createdAt: Optional[datetime] = None
    company_name: Optional[str] = None
    notes: Optional[str] = None