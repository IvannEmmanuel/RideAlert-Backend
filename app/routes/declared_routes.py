from app.models.declared_routes import DeclaredRouteModel
from typing import List
import json
from app.database import get_declared_routes_collection, get_fleets_collection
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends
from fastapi import Path
from app.dependencies.roles import super_and_admin_required
from bson import ObjectId


router = APIRouter(prefix="/declared_routes", tags=["Declared Routes"])


@router.get("/{company_id}", response_model=List[DeclaredRouteModel])
async def get_declared_routes_by_company(company_id: str, current_user: dict = Depends(super_and_admin_required)):
    try:
        routes = list(get_declared_routes_collection.find(
            {"company_id": company_id}))
        for route in routes:
            route["_id"] = str(route["_id"])
        return [DeclaredRouteModel(**route) for route in routes]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/", response_model=List[DeclaredRouteModel])
async def list_declared_routes(
    company_id: str,
    current_user: dict = Depends(super_and_admin_required)
):
    try:
        routes = list(get_declared_routes_collection.find(
            {"company_id": company_id}))
        for route in routes:
            route["_id"] = str(route["_id"])
        return [DeclaredRouteModel(**route) for route in routes]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{route_id}/route-geojson-upload", response_model=dict)
async def update_route_geojson(
    route_id: str = Path(..., description="Declared route ID"),
    route_geojson: UploadFile = File(...),
    current_user: dict = Depends(super_and_admin_required)
):
    try:
        geojson_content = await route_geojson.read()
        route_geojson_dict = json.loads(geojson_content)
        result = get_declared_routes_collection.update_one(
            {"_id": ObjectId(route_id)},
            {"$set": {"route_geojson": route_geojson_dict}}
        )
        if result.matched_count == 0:
            raise HTTPException(
                status_code=404, detail="Declared route not found")
        return {"updated": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/route-register", response_model=dict)
async def upload_declared_route(
    company_id: str = Form(...),
    start_location: str = Form(...),
    end_location: str = Form(...),
    landmark_details_start: str = Form(...),
    landmark_details_end: str = Form(...),
    route_geojson: UploadFile = File(None)
):
    try:
        route_geojson_dict = None
        if route_geojson:
            geojson_content = await route_geojson.read()
            route_geojson_dict = json.loads(geojson_content)
        data = {
            "company_id": company_id,
            "start_location": start_location,
            "end_location": end_location,
            "landmark_details_start": landmark_details_start,
            "landmark_details_end": landmark_details_end,
            "route_geojson": route_geojson_dict
        }
        result = get_declared_routes_collection.insert_one(data)
        return {"inserted_id": str(result.inserted_id)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/all/routes", response_model=List[DeclaredRouteModel])
async def get_all_declared_routes(current_user: dict = Depends(super_and_admin_required)):
    try:
        routes = list(get_declared_routes_collection.find())
        
        # Get all company names - convert both to string for matching
        fleets = list(get_fleets_collection.find({}, {"_id": 1, "company_name": 1}))
        company_map = {str(fleet["_id"]): fleet["company_name"] for fleet in fleets}
        
        # Add company names to routes
        for route in routes:
            route["_id"] = str(route["_id"])
            # Convert company_id to string for lookup
            company_id_str = str(route["company_id"])
            route["company_name"] = company_map.get(company_id_str, "Unknown Company")
            
        return [DeclaredRouteModel(**route) for route in routes]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))