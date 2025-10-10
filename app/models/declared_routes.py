from pydantic import BaseModel
from typing import Optional


from typing import Optional


class DeclaredRouteModel(BaseModel):
    company_id: str
    start_location: str
    end_location: str
    landmark_details_start: str
    landmark_details_end: str
    route_geojson: Optional[dict] = None
