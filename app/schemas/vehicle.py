from pydantic import BaseModel
from enum import Enum
from typing import Optional

# Enums for vehicle type and status
class VehicleType(str, Enum):
    newPUV = "newPUV"
    oldPUV = "oldPUV"

class VehicleStatus(str, Enum):
    available = "available"
    unavailable = "unavailable"
    full = "full"

# Pydantic model for vehicle location
class Location(BaseModel):
    latitude: float
    longitude: float

class VehicleBase(BaseModel):
    location: Optional[Location] = None
    vehicle_type: VehicleType
    capacity: int
    available_seats: int
    status: VehicleStatus
    route: str
    driverName: str
    plate: str
    device_id: Optional[str] = None
    bound_for: Optional[str] = None

class VehicleInDB(VehicleBase):
    id: str

class VehicleTrackResponse(BaseModel):
    id: str
    location: Location
    available_seats: int
    status: VehicleStatus
    route: str
    driverName: str
    plate: str
    device_id: str
    fleet_id: str
    bound_for: str