

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends
from app.database import get_declared_routes_collection
from app.dependencies.roles import super_and_admin_required
import json

router = APIRouter(prefix="/declared_routes", tags=["Declared Routes"])


@router.post("/upload", response_model=dict)
async def upload_declared_route(
    company_name: str = Form(...),
    company_code: str = Form(...),
    company_id: str = Form(None),
    start_location: str = Form(...),
    end_location: str = Form(...),
    landmark_details_start: str = Form(...),
    landmark_details_end: str = Form(...),
    route_geojson: UploadFile = File(...),
    current_user: dict = Depends(super_and_admin_required)
):
    try:
        geojson_content = await route_geojson.read()
        route_geojson_dict = json.loads(geojson_content)
        data = {
            "company_name": company_name,
            "company_code": company_code,
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
