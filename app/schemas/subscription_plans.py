from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List

class SubscriptionPlanBase(BaseModel):
    plan_name: str = Field(..., description="Name of the subscription plan (e.g., Basic, Premium)")
    plan_code: str = Field(..., description="Unique code for the plan (e.g., BASIC, PREMIUM)")
    description: Optional[str] = Field(None, description="Description of the plan")
    price: float = Field(..., gt=0, description="Price in PHP")
    max_vehicles: int = Field(..., gt=0, description="Maximum vehicles allowed")
    features: Optional[List[str]] = Field(default=[], description="List of features included")
    is_active: bool = Field(default=True, description="Whether the plan is available for selection")

class SubscriptionPlanCreate(SubscriptionPlanBase):
    """Schema for creating a new subscription plan"""
    pass

class SubscriptionPlanUpdate(BaseModel):
    """Schema for updating an existing subscription plan"""
    plan_name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = Field(None, gt=0)
    max_vehicles: Optional[int] = Field(None, gt=0)
    features: Optional[List[str]] = None
    is_active: Optional[bool] = None

class SubscriptionPlanPublic(SubscriptionPlanBase):
    """Schema for public subscription plan data"""
    id: str
    created_at: datetime
    last_updated: datetime

    class Config:
        from_attributes = True