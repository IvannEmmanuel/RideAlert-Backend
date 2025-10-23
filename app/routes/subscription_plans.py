from fastapi import APIRouter, HTTPException, Body, Depends
from app.models.subscription_plans import subscription_plan_entity
from app.schemas.subscription_plans import (
    SubscriptionPlanCreate, 
    SubscriptionPlanUpdate, 
    SubscriptionPlanPublic
)
from app.database import get_subscription_plans_collection
from bson import ObjectId
from datetime import datetime
from typing import List
from app.dependencies.roles import super_admin_required

router = APIRouter(prefix="/subscription-plans", tags=["Subscription Plans"])

def serialize_datetime(obj):
    """Convert datetime and ObjectId objects to strings."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, ObjectId):
        return str(obj)
    return obj

@router.post("/", response_model=SubscriptionPlanPublic)
async def create_subscription_plan(
    payload: SubscriptionPlanCreate,
    current_user: dict = Depends(super_admin_required)
):
    """
    Create a new subscription plan. Only accessible by superadmin.
    """
    collection = get_subscription_plans_collection

    # Check if plan_code already exists
    if collection.find_one({"plan_code": payload.plan_code.upper()}):
        raise HTTPException(status_code=400, detail="Plan code already exists")

    now = datetime.utcnow()
    doc = payload.dict()
    doc.update({
        "plan_code": payload.plan_code.upper(),  # Normalize to uppercase
        "created_at": now,
        "last_updated": now
    })

    result = collection.insert_one(doc)
    created = collection.find_one({"_id": result.inserted_id})

    return subscription_plan_entity(created)

@router.get("/", response_model=List[SubscriptionPlanPublic])
async def get_all_subscription_plans(active_only: bool = False):
    """
    Get all subscription plans. 
    Query param 'active_only=true' to get only active plans.
    """
    collection = get_subscription_plans_collection
    
    query = {"is_active": True} if active_only else {}
    plans = list(collection.find(query).sort("price", 1))  # Sort by price ascending
    
    return [subscription_plan_entity(plan) for plan in plans]

@router.get("/{plan_id}", response_model=SubscriptionPlanPublic)
async def get_subscription_plan(plan_id: str):
    """
    Get a specific subscription plan by ID.
    """
    collection = get_subscription_plans_collection
    
    if not ObjectId.is_valid(plan_id):
        raise HTTPException(status_code=400, detail="Invalid plan ID format")
    
    plan = collection.find_one({"_id": ObjectId(plan_id)})
    if not plan:
        raise HTTPException(status_code=404, detail="Subscription plan not found")
    
    return subscription_plan_entity(plan)

@router.get("/code/{plan_code}", response_model=SubscriptionPlanPublic)
async def get_subscription_plan_by_code(plan_code: str):
    """
    Get a subscription plan by its code (e.g., BASIC, PREMIUM).
    """
    collection = get_subscription_plans_collection
    
    plan = collection.find_one({"plan_code": plan_code.upper()})
    if not plan:
        raise HTTPException(status_code=404, detail="Subscription plan not found")
    
    return subscription_plan_entity(plan)

@router.patch("/{plan_id}", response_model=SubscriptionPlanPublic)
async def update_subscription_plan(
    plan_id: str,
    payload: SubscriptionPlanUpdate,
    current_user: dict = Depends(super_admin_required)
):
    """
    Update a subscription plan. Only accessible by superadmin.
    """
    collection = get_subscription_plans_collection
    
    if not ObjectId.is_valid(plan_id):
        raise HTTPException(status_code=400, detail="Invalid plan ID format")

    # Build update fields from non-None values
    update_fields = {k: v for k, v in payload.dict(exclude_unset=True).items() if v is not None}
    
    if not update_fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    update_fields["last_updated"] = datetime.utcnow()

    result = collection.update_one(
        {"_id": ObjectId(plan_id)},
        {"$set": update_fields}
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Subscription plan not found")

    updated = collection.find_one({"_id": ObjectId(plan_id)})
    return subscription_plan_entity(updated)

@router.delete("/{plan_id}")
async def delete_subscription_plan(
    plan_id: str,
    current_user: dict = Depends(super_admin_required)
):
    """
    Delete a subscription plan. Only accessible by superadmin.
    WARNING: This will cause issues if fleets are using this plan.
    Consider deactivating instead.
    """
    collection = get_subscription_plans_collection
    
    if not ObjectId.is_valid(plan_id):
        raise HTTPException(status_code=400, detail="Invalid plan ID format")

    # Check if any fleets are using this plan
    from app.database import get_fleets_collection
    plan = collection.find_one({"_id": ObjectId(plan_id)})
    if not plan:
        raise HTTPException(status_code=404, detail="Subscription plan not found")

    fleets_using_plan = get_fleets_collection.count_documents({
        "subscription_plan": plan["plan_code"]
    })

    if fleets_using_plan > 0:
        raise HTTPException(
            status_code=400, 
            detail=f"Cannot delete plan. {fleets_using_plan} fleet(s) are using this plan. Deactivate it instead."
        )

    result = collection.delete_one({"_id": ObjectId(plan_id)})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Subscription plan not found")

    return {"message": "Subscription plan deleted successfully"}

@router.patch("/{plan_id}/toggle-active")
async def toggle_plan_active_status(
    plan_id: str,
    current_user: dict = Depends(super_admin_required)
):
    """
    Toggle the active status of a subscription plan.
    Safer alternative to deletion.
    """
    collection = get_subscription_plans_collection
    
    if not ObjectId.is_valid(plan_id):
        raise HTTPException(status_code=400, detail="Invalid plan ID format")

    plan = collection.find_one({"_id": ObjectId(plan_id)})
    if not plan:
        raise HTTPException(status_code=404, detail="Subscription plan not found")

    new_status = not plan.get("is_active", True)
    
    collection.update_one(
        {"_id": ObjectId(plan_id)},
        {"$set": {"is_active": new_status, "last_updated": datetime.utcnow()}}
    )

    updated = collection.find_one({"_id": ObjectId(plan_id)})
    
    return {
        "message": f"Plan {'activated' if new_status else 'deactivated'} successfully",
        "plan": subscription_plan_entity(updated)
    }