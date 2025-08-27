from pydantic import BaseModel
from typing import List
from datetime import datetime

class GPSData(BaseModel):
    latitude: float
    longitude: float
    altitude: float
    timestamp: datetime

class SatelliteData(BaseModel):
    Cn0DbHz: float
    SvElevationDegrees: float
    Svid: int

class MpuData(BaseModel):
    MeasurementX: float
    MeasurementY: float
    MeasurementZ: float
class TrackingLogPublic(BaseModel):
    id: str
    vehicle_id: str
    gps_data: List[GPSData]