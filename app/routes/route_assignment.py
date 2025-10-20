from fastapi import APIRouter, HTTPException, Depends
from app.dependencies.roles import super_and_admin_required, admin_required
from app.database import vehicle_collection, get_declared_routes_collection
from bson import ObjectId
from pydantic import BaseModel
from typing import List
from datetime import datetime

router = APIRouter()

class AssignRouteRequest(BaseModel):
    vehicle_id: str
    route_ids: List[str]

@router.post("/assign-route/{vehicle_id}")
async def assign_route_to_vehicle(
    vehicle_id: str,
    request: AssignRouteRequest,
    current_user: dict = Depends(admin_required)
):
    try:
        vehicles_collection = vehicle_collection
        routes_collection = get_declared_routes_collection
        
        print(f"DEBUG: Processing assignment for vehicle {vehicle_id}")
        print(f"DEBUG: Route IDs to assign: {request.route_ids}")
        
        # ✅ 1. Validate vehicle exists
        vehicle = vehicles_collection.find_one({"_id": ObjectId(vehicle_id)})
        if not vehicle:
            raise HTTPException(status_code=404, detail="Vehicle not found")
        
        valid_routes = []
        invalid_routes = []
        missing_geojson_routes = []

        # ✅ 2. Validate each route & check if geojson exists
        for route_id in request.route_ids:
            route = routes_collection.find_one({"_id": ObjectId(route_id)})
            if route:
                if not route.get("route_geojson"):
                    missing_geojson_routes.append(str(route_id))
                else:
                    valid_routes.append({
                        "route_id": route_id,
                        "start_location": route.get("start_location", ""),
                        "end_location": route.get("end_location", ""),
                        "route_name": f"{route.get('start_location', '')} → {route.get('end_location', '')}"
                    })
            else:
                invalid_routes.append(route_id)

        # ✅ Block invalid routes
        if invalid_routes:
            raise HTTPException(status_code=404, detail=f"Routes not found: {invalid_routes}")

        # ✅ Block routes without GeoJSON file
        if missing_geojson_routes:
            raise HTTPException(
                status_code=400,
                detail=f"These routes cannot be assigned because they have no route_geojson uploaded: {missing_geojson_routes}"
            )

        # ✅ 3. Proceed to update vehicle only if all good
        update_data = {
            "current_route": valid_routes[0] if valid_routes else None,
            "last_updated": datetime.utcnow()
        }

        result = vehicles_collection.update_one(
            {"_id": ObjectId(vehicle_id)},
            {"$set": update_data}
        )

        if result.modified_count == 0:
            raise HTTPException(status_code=500, detail="Failed to update vehicle")

        return {
            "success": True,
            "message": f"Successfully assigned {len(valid_routes)} route(s) to vehicle",
            "assigned_routes": valid_routes,
            "vehicle_id": vehicle_id
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/vehicle/{vehicle_id}/routes")
async def get_vehicle_routes(
    vehicle_id: str,
    current_user: dict = Depends(admin_required)
):
    """
    Get all routes assigned to a specific vehicle
    """
    try:
        vehicles_collection = vehicle_collection
        
        vehicle = vehicles_collection.find_one({"_id": ObjectId(vehicle_id)})
        if not vehicle:
            raise HTTPException(status_code=404, detail="Vehicle not found")
        
        assigned_routes = vehicle.get("assigned_routes", [])
        current_route = vehicle.get("current_route")
        
        return {
            "vehicle_id": vehicle_id,
            "assigned_routes": assigned_routes,
            "current_route": current_route,
            "total_routes": len(assigned_routes)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/vehicle/{vehicle_id}/routes/{route_id}")
async def remove_route_from_vehicle(
    vehicle_id: str,
    route_id: str,
    current_user: dict = Depends(admin_required)
):
    """
    Remove a specific route from a vehicle
    """
    try:
        vehicles_collection = vehicle_collection
        
        vehicle = vehicles_collection.find_one({"_id": ObjectId(vehicle_id)})
        if not vehicle:
            raise HTTPException(status_code=404, detail="Vehicle not found")
        
        assigned_routes = vehicle.get("assigned_routes", [])
        
        # Find the route to remove
        route_to_remove = None
        updated_routes = []
        
        for route in assigned_routes:
            if route["route_id"] == route_id:
                route_to_remove = route
            else:
                updated_routes.append(route)
        
        if not route_to_remove:
            raise HTTPException(status_code=404, detail="Route not assigned to this vehicle")
        
        # Update vehicle
        update_data = {
            "assigned_routes": updated_routes,
            "last_updated": datetime.utcnow()
        }
        
        # If we're removing the current route, update that too
        current_route = vehicle.get("current_route")
        if current_route and current_route.get("route_id") == route_id:
            update_data["current_route"] = updated_routes[0] if updated_routes else None
        
        result = vehicles_collection.update_one(
            {"_id": ObjectId(vehicle_id)},
            {"$set": update_data}
        )
        
        if result.modified_count == 0:
            raise HTTPException(status_code=500, detail="Failed to update vehicle")
        
        return {
            "success": True,
            "message": "Route removed from vehicle",
            "removed_route": route_to_remove
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/vehicle/{vehicle_id}/current-route/{route_id}")
async def set_current_route(
    vehicle_id: str,
    route_id: str,
    current_user: dict = Depends(admin_required)
):
    """
    Set a specific route as the current active route for a vehicle
    """
    try:
        vehicles_collection = vehicle_collection
        
        vehicle = vehicles_collection.find_one({"_id": ObjectId(vehicle_id)})
        if not vehicle:
            raise HTTPException(status_code=404, detail="Vehicle not found")
        
        assigned_routes = vehicle.get("assigned_routes", [])
        
        # Find the route to set as current
        target_route = None
        for route in assigned_routes:
            if route["route_id"] == route_id:
                target_route = route
                break
        
        if not target_route:
            raise HTTPException(status_code=404, detail="Route not assigned to this vehicle")
        
        # Update current route
        result = vehicles_collection.update_one(
            {"_id": ObjectId(vehicle_id)},
            {
                "$set": {
                    "current_route": target_route,
                    "last_updated": datetime.utcnow()
                }
            }
        )
        
        if result.modified_count == 0:
            raise HTTPException(status_code=500, detail="Failed to update vehicle")
        
        return {
            "success": True,
            "message": "Current route updated",
            "current_route": target_route
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))