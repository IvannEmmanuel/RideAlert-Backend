from pydantic import BaseModel, Field, validator
from datetime import datetime
from typing import Optional, List
from enum import Enum

class PDFFile(BaseModel):
    filename: str
    content: Optional[str] = None

class FleetRole(str, Enum):
    unverified = "unverified"
    admin = "admin"
    superadmin = "superadmin"

class ContactInfo(BaseModel):
    email: str
    phone: str
    address: str

class FleetBase(BaseModel):
    company_name: str
    company_code: str
    contact_info: List[ContactInfo]
    subscription_plan: str  # Changed to string to accept plan_code
    is_active: Optional[bool] = None
    role: FleetRole = FleetRole.unverified
    last_updated: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    max_vehicles: Optional[int] = None  # Will be set from subscription plan
    plan_price: Optional[float] = None  # Will be set from subscription plan
    pdf_files: Optional[List[PDFFile]] = None

    @validator('subscription_plan')
    def validate_subscription_plan(cls, v):
        """Validate that subscription_plan is a valid plan code"""
        if v:
            return v.upper()  # Normalize to uppercase
        return v

class FleetCreate(FleetBase):
    password: str  # Accept plain password for creation

class FleetPublic(FleetBase):
    id: str

    class Config:
        exclude = {"password"}