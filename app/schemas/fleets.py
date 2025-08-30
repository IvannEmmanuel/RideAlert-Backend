from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List
from enum import Enum

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
    is_active: bool
    max_vehicles: int
    last_updated: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

class FleetCreate(FleetBase):
    pass

class FleetPublic(FleetBase):
    id: str