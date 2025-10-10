from pydantic import BaseModel
from typing import Optional

class DeclaredRouteModel(BaseModel):
    company_name: str
    company_code: str
    company_id: Optional[str] = None
    start_location: str
    end_location: str
    landmark_details_start: str
    landmark_details_end: str
    route_geojson: dict