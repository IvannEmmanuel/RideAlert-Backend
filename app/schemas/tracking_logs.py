from pydantic import BaseModel
from typing import List
from datetime import datetime

class GPSData(BaseModel):
    latitude: float
    longitude: float
    timestamp: datetime

class TrackingLogPublic(BaseModel):
    id: str
    vehicle_id: str
    gps_data: List[GPSData]