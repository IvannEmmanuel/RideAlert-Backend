import json
from app.database import get_declared_routes_collection
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends
from fastapi import Path
from app.dependencies.roles import super_and_admin_required


router = APIRouter(prefix="/declared_routes", tags=["Declared Routes"])


@router.patch("/{route_id}/route-geojson", response_model=dict)
async def update_route_geojson(
    route_id: str = Path(..., description="Declared route ID"),
    route_geojson: UploadFile = File(...),
    current_user: dict = Depends(super_and_admin_required)
):
    try:
        geojson_content = await route_geojson.read()
        route_geojson_dict = json.loads(geojson_content)
        result = get_declared_routes_collection.update_one(
            {"_id": route_id},
            {"$set": {"route_geojson": route_geojson_dict}}
        )
        if result.matched_count == 0:
            raise HTTPException(
                status_code=404, detail="Declared route not found")
        return {"updated": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload", response_model=dict)
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
