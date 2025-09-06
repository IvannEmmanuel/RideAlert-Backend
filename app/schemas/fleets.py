from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List
from enum import Enum

class FleetRole(str, Enum):
    unverified = "unverified"
    admin = "admin"
    superadmin = "superadmin"

class SubscriptionPlan(str, Enum):
    basic = "Basic"
    premium = "Premium"
    enterprise = "Enterprise"

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
    role: FleetRole = FleetRole.unverified
    last_updated: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @property
    def plan_price(self) -> int:
        """Returns the price for the subscription plan in PHP."""
        prices = {
            SubscriptionPlan.basic: 250,
            SubscriptionPlan.premium: 1000,
            SubscriptionPlan.enterprise: 2500
        }
        return prices[self.subscription_plan]

    @property
    def max_vehicles(self) -> int:
        """Returns the max vehicles allowed for the subscription plan."""
        limits = {
            SubscriptionPlan.basic: 5,
            SubscriptionPlan.premium: 25,
            SubscriptionPlan.enterprise: 100
        }
        return limits[self.subscription_plan]

class FleetCreate(FleetBase):
    password: str  # Accept plain password for creation

class FleetPublic(FleetBase):
    id: str

    class Config:
        exclude = {"password"}