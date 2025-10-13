# In app/models/declared_routes.py
from pydantic import BaseModel, Field
from typing import Optional

class DeclaredRouteModel(BaseModel):
    id: str = Field(..., alias="_id")  # Map MongoDB _id to id
    company_id: str
    company_name: str
    start_location: str
    end_location: str
    landmark_details_start: Optional[str] = ""
    landmark_details_end: Optional[str] = ""
    route_geojson: Optional[dict] = None
    
    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True