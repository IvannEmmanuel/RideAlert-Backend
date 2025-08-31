from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List
from enum import Enum

class FleetRole(str, Enum):
    unverified = "unverified"
    admin = "admin"

class SubscriptionPlan(str, Enum):
    basic = "Basic"
    premium = "Premium"

class ContactInfo(BaseModel):
    email: str
    phone: str
    address: str

class FleetBase(BaseModel):
    company_name: str
    company_code: str
    contact_info: List[ContactInfo]
    subscription_plan: SubscriptionPlan
    is_active: Optional[bool] = None
    max_vehicles: int
    role: FleetRole = FleetRole.unverified
    last_updated: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

class FleetCreate(FleetBase):
    password: str  # Accept plain password for creation

class FleetPublic(FleetBase):
    id: str

    class Config:
        exclude = {"password"}