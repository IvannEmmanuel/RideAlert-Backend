from pydantic import BaseModel
from typing import List
from datetime import datetime


class GPSData(BaseModel):
    latitude: float
    longitude: float
    altitude: float
    timestamp: datetime
    fleet_id: str


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
    fleet_id: str
    device_id: str
    gps_data: List[GPSData]
