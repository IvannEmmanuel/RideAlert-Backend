from app.models.declared_routes import DeclaredRouteModel
from typing import List
import json
from app.database import get_declared_routes_collection, get_fleets_collection
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends, WebSocket
from fastapi import Path
from app.dependencies.roles import super_and_admin_required, admin_required
from bson import ObjectId
from app.utils.ws_manager import routes_all_manager  # Adjust path if needed


router = APIRouter(prefix="/declared_routes", tags=["Declared Routes"])

@router.websocket("/ws/routes")
async def websocket_endpoint(websocket: WebSocket):
    await routes_all_manager.connect(websocket)
    try:
        while True:
            # Keep connection alive; can receive messages if needed
            data = await websocket.receive_text()
    except Exception:
        routes_all_manager.disconnect(websocket)

@router.delete("/{route_id}")
async def delete_declared_route(
    route_id: str,
    current_user: dict = Depends(admin_required)
):
    try:
        # Get the collection
        routes_collection = get_declared_routes_collection
        
        # Fetch the route before deletion to get details for broadcast
        route_to_delete = routes_collection.find_one({"_id": ObjectId(route_id)})
        if not route_to_delete:
            raise HTTPException(status_code=404, detail="Route not found")
        
        # Delete the route
        result = routes_collection.delete_one({"_id": ObjectId(route_id)})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Route not found")
        
        # Broadcast deletion to all connected superadmin clients
        await routes_all_manager.broadcast({
            "type": "deleted_route",
            "route_id": str(route_to_delete["_id"]),
            "company_id": str(route_to_delete["company_id"])
        })
        
        return {"deleted": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/{route_id}")
async def update_declared_route(
    route_id: str,
    start_location: str = Form(None),
    end_location: str = Form(None),
    landmark_details_start: str = Form(None),
    landmark_details_end: str = Form(None),
    current_user: dict = Depends(super_and_admin_required)
):
    try:
        update_data = {}
        if start_location is not None:
            update_data["start_location"] = start_location
        if end_location is not None:
            update_data["end_location"] = end_location
        if landmark_details_start is not None:
            update_data["landmark_details_start"] = landmark_details_start
        if landmark_details_end is not None:
            update_data["landmark_details_end"] = landmark_details_end

        if not update_data:
            raise HTTPException(status_code=400, detail="No data provided for update")

        # Update and get the full updated document
        result = get_declared_routes_collection.find_one_and_update(
            {"_id": ObjectId(route_id)},
            {"$set": update_data},
            return_document=True  # Returns the updated document
        )
        
        if not result:
            raise HTTPException(status_code=404, detail="Route not found")
        
        # Get company name for broadcast
        fleet = get_fleets_collection.find_one({"_id": ObjectId(str(result["company_id"]))})
        company_name = fleet.get("company_name", "Unknown Company") if fleet else "Unknown Company"
        
        # Prepare updated route data for broadcast
        broadcast_route = {
            "_id": str(result["_id"]),
            "company_name": company_name,
            "start_location": result.get("start_location", ""),
            "end_location": result.get("end_location", ""),
            "landmark_details_start": result.get("landmark_details_start", ""),
            "landmark_details_end": result.get("landmark_details_end", ""),
        }
        
        # Broadcast update to all connected superadmin clients
        await routes_all_manager.broadcast({
            "type": "updated_route",
            "route": broadcast_route
        })
            
        return {"updated": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{company_id}")
async def get_declared_routes_by_company(company_id: str, current_user: dict = Depends(admin_required)):
    try:
        routes = list(get_declared_routes_collection.find({"company_id": company_id}))
        
        # Fetch company name once
        fleet = get_fleets_collection.find_one({"_id": ObjectId(company_id)})
        company_name = fleet.get("company_name", "Unknown Company") if fleet else "Unknown Company"
        
        result = []
        for route in routes:
            route["_id"] = str(route["_id"])  # Convert ObjectId to string
            route["company_name"] = company_name
            result.append(route)
        
        return result  # Return raw dict without Pydantic validation
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
        inserted_id = str(result.inserted_id)
        
        # Get company name for the broadcast
        fleet = get_fleets_collection.find_one({"_id": ObjectId(company_id)})
        company_name = fleet.get("company_name", "Unknown Company") if fleet else "Unknown Company"
        
        # Prepare route data for broadcast
        broadcast_route = {
            "_id": inserted_id,
            "company_name": company_name,
            "start_location": start_location,
            "end_location": end_location,
            "landmark_details_start": landmark_details_start,
            "landmark_details_end": landmark_details_end,
        }
        
        # Broadcast to all connected superadmin clients
        await routes_all_manager.broadcast({
            "type": "new_route",
            "route": broadcast_route
        })
        
        return {"inserted_id": inserted_id}
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
    
@router.get("/routes/{fleet_id}", response_model=List[dict])
async def get_routes_by_fleet_id(fleet_id: str, current_user: dict = Depends(admin_required)):
    """
    Get all start and end locations for a specific fleet/company (fleet_id).
    """
    try:
        routes_collection = get_declared_routes_collection
        fleets_collection = get_fleets_collection

        # Check if company exists
        company = fleets_collection.find_one({"_id": ObjectId(fleet_id)})
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        # Get all routes belonging to this company
        routes = list(routes_collection.find({"company_id": fleet_id}, {
            "start_location": 1,
            "end_location": 1,
            "_id": 0
        }))

        if not routes:
            raise HTTPException(status_code=404, detail="No routes found for this company")

        return routes

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))