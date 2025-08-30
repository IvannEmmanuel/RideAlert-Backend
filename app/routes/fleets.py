from fastapi import APIRouter, HTTPException, Body, Depends
from app.models.fleets import fleets
from app.schemas.fleets import FleetCreate, FleetPublic
from app.database import get_fleets_collection
from bson import ObjectId
from datetime import datetime
from typing import List, Dict, Optional
from app.dependencies.roles import super_admin_required

router = APIRouter(prefix="/fleets", tags=["Fleets"])

@router.post("/", response_model=FleetPublic)
async def create_fleet(
    payload: Optional[FleetCreate] = Body(None),
    current_user: Dict = Depends(super_admin_required)
):
    """
    Create a new fleet. Requires admin role.
    """

    collection = get_fleets_collection

    # Defensive: Ensure payload is provided
    if not payload:
        raise HTTPException(status_code=400, detail="Fleet data is required")

    # Check for duplicate company_code
    if collection.find_one({"company_code": payload.company_code}):
        raise HTTPException(status_code=400, detail="company_code already exists")

    doc = payload.dict()
    now = datetime.utcnow()
    doc.setdefault("created_at", now)
    doc.setdefault("last_updated", now)

    result = collection.insert_one(doc)
    created = collection.find_one({"_id": result.inserted_id})

    return fleets(created)  # ✅ matches FleetPublic


@router.get("/all", response_model=List[FleetPublic])
def list_fleets():
    """
    Get all fleets.
    """
    collection = get_fleets_collection
    fleet_docs = collection.find()
    return [fleets(f) for f in fleet_docs]


@router.get("/{fleet_id}", response_model=FleetPublic)
def get_fleet(fleet_id: str):
    """
    Get a specific fleet by ID.
    """
    collection = get_fleets_collection
    fleet_doc = collection.find_one({"_id": ObjectId(fleet_id)})
    if not fleet_doc:
        raise HTTPException(status_code=404, detail="Fleet not found")
    return fleets(fleet_doc)


@router.patch("/{fleet_id}", response_model=FleetPublic)
def update_fleet(fleet_id: str, payload: dict = Body(...)):
    """
    Update fields of a fleet (e.g., subscription_plan, is_active).
    """
    collection = get_fleets_collection

    update_fields = {}
    allowed_fields = [
        "company_name", "contact_info", "subscription_plan",
        "is_active", "max_vehicles", "last_updated"
    ]

    for field in allowed_fields:
        if field in payload:
            update_fields[field] = payload[field]

    if not update_fields:
        raise HTTPException(status_code=400, detail="No valid fields to update")

    update_fields["last_updated"] = datetime.utcnow()

    result = collection.update_one(
        {"_id": ObjectId(fleet_id)},
        {"$set": update_fields}
    )

    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Fleet not found or not updated")

    updated = collection.find_one({"_id": ObjectId(fleet_id)})
    return fleets(updated)
