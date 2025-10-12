from typing import Optional, Union
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi import Body
from pydantic import BaseModel
from app.database import vehicle_collection, tracking_logs_collection, user_collection, notification_logs_collection
from bson import ObjectId
from app.dependencies.roles import user_required, admin_required, user_or_admin_required, super_and_admin_required
from app.schemas.vehicle import VehicleTrackResponse, Location, VehicleStatus, VehicleBase, VehicleInDB
from typing import List
from datetime import datetime, timedelta
import asyncio
from app.utils.geo import haversine
from app.utils.ws_manager import vehicle_count_manager, vehicle_all_manager
from app.utils.notifications import send_fcm_notification

router = APIRouter(prefix="/vehicles", tags=["Vehicles"])


@router.get("/{vehicle_id}")
async def get_vehicle(vehicle_id: str):
    """Return vehicle document by id or device_id (string or ObjectId)."""
    try:
        # Try treating as ObjectId first
        query = None
        if ObjectId.is_valid(vehicle_id):
            query = {"$or": [{"_id": ObjectId(vehicle_id)}, {"device_id": vehicle_id}]}
        else:
            query = {"$or": [{"device_id": vehicle_id}, {"_id": vehicle_id}]}

        print(f"GET /vehicles/{vehicle_id} query: {query}")

        vehicle = vehicle_collection.find_one(query)
        if not vehicle:
            print(f"Vehicle {vehicle_id} not found")
            raise HTTPException(status_code=404, detail="Vehicle not found")

        # Build sanitized response to avoid nested ObjectId serialization issues
        resp = {
            "_id": str(vehicle.get("_id")),
            "location": vehicle.get("location"),
            "device_id": vehicle.get("device_id"),
            "plate": vehicle.get("plate"),
            "driverName": vehicle.get("driverName"),
            "fleet_id": str(vehicle.get("fleet_id")) if vehicle.get("fleet_id") else None
        }
        print(f"GET /vehicles/{vehicle_id} response: {resp}")
        return resp
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in get_vehicle: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class ETARequest(BaseModel):
    vehicle_id: str
    user_location: Location

class ETAResponse(BaseModel):
    vehicle_id: str
    vehicle_plate: str
    vehicle_route: str
    distance_meters: float
    distance_km: float
    current_speed_mps: float
    current_speed_kmh: float
    average_speed_kmh: float
    eta_minutes: Optional[float]
    eta_formatted: str
    vehicle_location: dict
    user_location: dict
    status: str
    message: str
    is_stopped: bool
    confidence: str  # "high", "medium", "low"

def get_speed_history(device_id: str, minutes: int = 5) -> list:
    """
    Get speed history for the last N minutes to calculate average speed.
    This helps smooth out temporary stops (traffic lights, stops, etc.)
    """
    time_threshold = datetime.utcnow() - timedelta(minutes=minutes)
    timestamp_ms = int(time_threshold.timestamp() * 1000)
    
    tracking_logs = list(tracking_logs_collection.find(
        {
            "device_id": device_id,
            "timestamp": {"$gte": timestamp_ms}
        },
        sort=[("timestamp", -1)],
        limit=30  # Last 30 readings (should cover 5 minutes)
    ))
    
    speeds = []
    for log in tracking_logs:
        speed = log.get("SpeedMps", 0.0)
        speeds.append(speed)
    
    return speeds

def calculate_average_speed(speeds: list, percentile: float = 0.7) -> float:
    """
    Calculate average speed using 70th percentile to ignore outliers.
    This filters out very low speeds (stopped) and very high speeds (anomalies).
    """
    if not speeds:
        return 0.0
    
    # Remove zeros and negative values
    valid_speeds = [s for s in speeds if s > 0]
    
    if not valid_speeds:
        return 0.0
    
    # Sort speeds
    valid_speeds.sort()
    
    # Get 70th percentile (ignore bottom 30% which might be stops)
    index = int(len(valid_speeds) * percentile)
    if index >= len(valid_speeds):
        index = len(valid_speeds) - 1
    
    # Average of speeds above percentile threshold
    percentile_speed = valid_speeds[index]
    
    # Calculate average of speeds that are >= percentile_speed / 2
    # This includes moving speeds but excludes complete stops
    threshold = percentile_speed / 2
    moving_speeds = [s for s in valid_speeds if s >= threshold]
    
    if not moving_speeds:
        return percentile_speed
    
    return sum(moving_speeds) / len(moving_speeds)

def is_vehicle_stopped(current_speed: float, speed_history: list) -> bool:
    """
    Determine if vehicle is genuinely stopped or just temporarily halted.
    Returns True only if stopped for extended period.
    """
    # If current speed is very low
    if current_speed < 0.5:  # Less than 1.8 km/h
        # Check if it's been stopped for a while
        recent_speeds = speed_history[:5]  # Last 5 readings
        if len(recent_speeds) >= 3:
            stopped_count = sum(1 for s in recent_speeds if s < 0.5)
            # If more than 60% of recent readings show stopped
            if stopped_count / len(recent_speeds) > 0.6:
                return True
    return False

def calculate_smart_eta(
    distance_meters: float,
    current_speed_mps: float,
    average_speed_mps: float,
    is_stopped: bool,
    vehicle_status: str
) -> tuple[Optional[float], str, str]:
    """
    Calculate ETA with intelligent handling of stops and traffic.
    
    Returns:
        (eta_minutes, eta_formatted, confidence_level)
    """
    # Default speeds for different scenarios (in m/s)
    URBAN_SPEED_MPS = 8.33  # 30 km/h - typical urban speed
    SLOW_TRAFFIC_MPS = 5.56  # 20 km/h - slow traffic
    MIN_SPEED_MPS = 2.78     # 10 km/h - very slow/congested
    
    # Scenario 1: Vehicle is stopped (traffic light, picking passengers, etc.)
    if is_stopped:
        # Use average speed from history, or default urban speed
        effective_speed = average_speed_mps if average_speed_mps > 1.0 else URBAN_SPEED_MPS
        confidence = "medium"
        message = "Vehicle temporarily stopped. ETA based on average speed."
    
    # Scenario 2: Vehicle status is "standing" (parked/not moving)
    elif vehicle_status == "standing":
        # Vehicle is not in service yet
        if average_speed_mps > 1.0:
            # Has recent movement history
            effective_speed = average_speed_mps
            confidence = "low"
            message = "Vehicle standing. ETA based on historical speed."
        else:
            # No recent movement
            effective_speed = URBAN_SPEED_MPS
            confidence = "low"
            message = "Vehicle standing. ETA is estimated."
    
    # Scenario 3: Vehicle is moving slowly (traffic/congestion)
    elif 0.5 <= current_speed_mps < 3.0:  # Between 1.8 km/h and 10.8 km/h
        # Probably in traffic, use weighted average of current and historical
        if average_speed_mps > current_speed_mps:
            # Traffic is clearing up, weight more toward average
            effective_speed = (current_speed_mps * 0.3) + (average_speed_mps * 0.7)
        else:
            # Traffic is getting worse, weight more toward current
            effective_speed = (current_speed_mps * 0.7) + (average_speed_mps * 0.3)
        
        # Ensure minimum speed
        effective_speed = max(effective_speed, MIN_SPEED_MPS)
        confidence = "medium"
        message = "Vehicle in traffic. ETA adjusted for congestion."
    
    # Scenario 4: Vehicle is moving normally
    elif current_speed_mps >= 3.0:
        # Use blend of current and average for stability
        if average_speed_mps > 1.0:
            # Weight 60% current, 40% average for stability
            effective_speed = (current_speed_mps * 0.6) + (average_speed_mps * 0.4)
            confidence = "high"
            message = "Vehicle moving normally. Real-time ETA."
        else:
            # No good average, use current
            effective_speed = current_speed_mps
            confidence = "medium"
            message = "Vehicle moving. ETA based on current speed."
    
    # Scenario 5: Very low/zero speed with no history
    else:
        effective_speed = URBAN_SPEED_MPS
        confidence = "low"
        message = "Limited data. ETA is estimated."
    
    # Calculate ETA
    eta_seconds = distance_meters / effective_speed
    eta_minutes = eta_seconds / 60
    
    # Add buffer for stops (traffic lights, passenger pickup, etc.)
    # Add 15% buffer for urban travel, capped at 5 minutes
    buffer_minutes = min(eta_minutes * 0.15, 5.0)
    eta_minutes_with_buffer = eta_minutes + buffer_minutes
    
    # Format ETA
    if eta_minutes_with_buffer < 1:
        eta_formatted = "Less than 1 minute"
    elif eta_minutes_with_buffer < 60:
        eta_formatted = f"{int(eta_minutes_with_buffer)} minutes"
    else:
        hours = int(eta_minutes_with_buffer // 60)
        mins = int(eta_minutes_with_buffer % 60)
        eta_formatted = f"{hours} hour{'s' if hours > 1 else ''} {mins} minutes"
    
    return eta_minutes_with_buffer, eta_formatted, confidence, message

@router.post("/calculate-eta", response_model=ETAResponse)
async def calculate_vehicle_eta(
    request: ETARequest,
    current_user: dict = Depends(user_or_admin_required)
):
    """
    Calculate SMART distance and ETA with traffic-aware logic.
    
    This endpoint:
    1. Fetches vehicle and latest tracking data
    2. Analyzes speed history (last 5 minutes)
    3. Detects if vehicle is stopped, in traffic, or moving normally
    4. Calculates realistic ETA with buffer for stops
    5. Provides confidence level for the estimate
    """
    
    # Validate vehicle_id
    if not ObjectId.is_valid(request.vehicle_id):
        raise HTTPException(status_code=400, detail="Invalid vehicle ID format")
    
    # Fetch vehicle
    vehicle = vehicle_collection.find_one({"_id": ObjectId(request.vehicle_id)})
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    
    # Get vehicle location
    vehicle_location = vehicle.get("location")
    if not vehicle_location or not vehicle_location.get("latitude") or not vehicle_location.get("longitude"):
        raise HTTPException(status_code=400, detail="Vehicle location not available")
    
    vehicle_lat = vehicle_location["latitude"]
    vehicle_lon = vehicle_location["longitude"]
    user_lat = request.user_location.latitude
    user_lon = request.user_location.longitude
    
    # Calculate distance
    distance_meters = haversine(user_lat, user_lon, vehicle_lat, vehicle_lon)
    distance_km = distance_meters / 1000
    
    # Get device_id and fetch speed data
    device_id = vehicle.get("device_id")
    current_speed_mps = 0.0
    average_speed_mps = 0.0
    status_message = "ETA calculated using default speed"
    confidence = "low"
    is_stopped_flag = False
    
    if device_id:
        # Get latest tracking log
        latest_tracking = tracking_logs_collection.find_one(
            {"device_id": device_id},
            sort=[("timestamp", -1)]
        )
        
        if latest_tracking:
            current_speed_mps = latest_tracking.get("SpeedMps", 0.0)
            
            # Check if tracking data is recent (within last 2 minutes)
            tracking_timestamp = latest_tracking.get("timestamp")
            if tracking_timestamp:
                tracking_time = datetime.fromtimestamp(tracking_timestamp / 1000)
                time_diff = datetime.utcnow() - tracking_time
                
                if time_diff <= timedelta(minutes=2):
                    # Get speed history for smart calculation
                    speed_history = get_speed_history(device_id, minutes=5)
                    
                    if speed_history:
                        average_speed_mps = calculate_average_speed(speed_history)
                        is_stopped_flag = is_vehicle_stopped(current_speed_mps, speed_history)
    
    # Get vehicle status details
    vehicle_status_detail = vehicle.get("status_detail", "").lower()
    
    # Calculate smart ETA
    eta_minutes, eta_formatted, confidence, status_message = calculate_smart_eta(
        distance_meters,
        current_speed_mps,
        average_speed_mps,
        is_stopped_flag,
        vehicle_status_detail
    )
    
    # Convert speeds to km/h for response
    current_speed_kmh = current_speed_mps * 3.6
    average_speed_kmh = average_speed_mps * 3.6
    
    return ETAResponse(
        vehicle_id=str(vehicle["_id"]),
        vehicle_plate=vehicle.get("plate", "Unknown"),
        vehicle_route=vehicle.get("route", "Unknown"),
        distance_meters=round(distance_meters, 2),
        distance_km=round(distance_km, 2),
        current_speed_mps=round(current_speed_mps, 2),
        current_speed_kmh=round(current_speed_kmh, 2),
        average_speed_kmh=round(average_speed_kmh, 2),
        eta_minutes=round(eta_minutes, 2) if eta_minutes else None,
        eta_formatted=eta_formatted,
        vehicle_location={
            "latitude": vehicle_lat,
            "longitude": vehicle_lon
        },
        user_location={
            "latitude": user_lat,
            "longitude": user_lon
        },
        status=vehicle.get("status", "unknown"),
        message=status_message,
        is_stopped=is_stopped_flag,
        confidence=confidence
    )

def serialize_vehicle(vehicle):
    """Serialize a vehicle document, converting ObjectId to string."""
    return {
        "id": str(vehicle["_id"]),
        "fleet_id": str(vehicle.get("fleet_id", "")),
        "location": vehicle.get("location"),
        "vehicle_type": vehicle.get("vehicle_type", ""),
        "capacity": vehicle.get("capacity", 0),
        "available_seats": vehicle.get("available_seats", 0),
        "status": vehicle.get("status", "unavailable"),
        "route": vehicle.get("route", ""),
        "driverName": vehicle.get("driverName", ""),
        "plate": vehicle.get("plate", ""),
        "device_id": vehicle.get("device_id"),
        "bound_for": vehicle.get("bound_for")
    }


async def broadcast_vehicle_list(fleet_id: str):
    """Broadcast the list of vehicles for a specific fleet_id."""
    vehicles = [
        serialize_vehicle(vehicle)
        for vehicle in vehicle_collection.find({"fleet_id": fleet_id})
    ]
    await vehicle_all_manager.broadcast({"vehicles": vehicles}, fleet_id)


async def broadcast_available_vehicle_list(fleet_id: str):
    """Broadcast the list of available vehicles with valid locations for a specific fleet_id."""
    query = {
        "fleet_id": fleet_id,
         "status": {"$in": ["available", "full"]},
        "location.latitude": {"$ne": None},
        "location.longitude": {"$ne": None}
    }
    vehicles = [
        {
            "id": str(vehicle["_id"]),
            "location": vehicle.get("location"),
            "available_seats": vehicle.get("available_seats", 0),
            "route": vehicle.get("route", ""),
            "driverName": vehicle.get("driverName", ""),
            "plate": vehicle.get("plate", ""),
            "status": vehicle.get("status", "unavailable"),
            "bound_for": vehicle.get("bound_for"),
            "status_details": vehicle.get("status_details")
        }
        for vehicle in vehicle_collection.find(query)
    ]
    await vehicle_all_manager.broadcast({"vehicles": vehicles}, fleet_id)


@router.post("/create/{fleet_id}", response_model=VehicleInDB)
async def create_vehicle_for_fleet(
    fleet_id: str,
    vehicle: VehicleBase,
    current_user: dict = Depends(super_and_admin_required)
):
    # Ensure plate is unique
    if vehicle_collection.find_one({"plate": vehicle.plate}):
        raise HTTPException(
            status_code=400,
            detail="This vehicle license plate already exists"
        )

    # Convert to dict and enforce fleet_id
    vehicle_dict = vehicle.dict()
    vehicle_dict["fleet_id"] = fleet_id

    # Insert into DB
    result = vehicle_collection.insert_one(vehicle_dict)
    created_vehicle = vehicle_collection.find_one({"_id": result.inserted_id})
    if not created_vehicle:
        raise HTTPException(status_code=500, detail="Failed to create vehicle")

    # Broadcast updated vehicle count and list
    total_vehicles = vehicle_collection.count_documents({})
    await vehicle_count_manager.broadcast({"total_vehicles": total_vehicles})
    await broadcast_vehicle_list(fleet_id)

    # Safe location check before broadcasting available list
    location = created_vehicle.get("location")
    if (
        created_vehicle.get("status") == "available"
        and isinstance(location, dict)
        and location.get("latitude") is not None
        and location.get("longitude") is not None
    ):
        await broadcast_available_vehicle_list(fleet_id)

    # Return serialized vehicle
    created_vehicle_dict = serialize_vehicle(created_vehicle)
    return VehicleInDB(**created_vehicle_dict)

# @router.post("/create", response_model=VehicleInDB)
# def create_vehicle(vehicle: VehicleBase, current_user: dict = Depends(admin_required)):

#     if vehicle_collection.find_one({"plate": vehicle.plate}):
#         raise HTTPException(status_code=400, detail="This vehicle license plate is existed already")

#     vehicle_dict = vehicle.dict()
#     result = vehicle_collection.insert_one(vehicle_dict)

#     created_vehicle = vehicle_collection.find_one({"_id": result.inserted_id})
#     if not created_vehicle:
#         raise HTTPException(status_code=500, detail="Failed to create that vehicle")

#     created_vehicle_dict = {
#         "id": str(created_vehicle["_id"]),
#         "fleet_id": str(create_vehicle["fleet_id"]),
#         "location": created_vehicle["location"],
#         "vehicle_type": created_vehicle["vehicle_type"],
#         "capacity": created_vehicle["capacity"],
#         "available_seats": created_vehicle["available_seats"],
#         "status": created_vehicle["status"],
#         "route": created_vehicle["route"],
#         "driverName": created_vehicle["driverName"],
#         "plate": created_vehicle["plate"],
#         "device_id": created_vehicle.get("device_id")
#     }

#     return VehicleInDB(**created_vehicle_dict)

# @router.get("/all", response_model=List[VehicleInDB])
# def get_all_vehicles(current_user: dict = Depends(user_or_admin_required)):
#     try:
#         vehicles_cursor = vehicle_collection.find({})
#         vehicles = []
#         for vehicle in vehicles_cursor:
#             vehicle_data = {
#                 "id": str(vehicle["_id"]),
#                 "location": vehicle.get("location"),
#                 "vehicle_type": vehicle.get("vehicle_type", ""),
#                 "capacity": vehicle.get("capacity", 0),
#                 "available_seats": vehicle.get("available_seats", 0),
#                 "status": vehicle.get("status", "unavailable"),
#                 "route": vehicle.get("route", ""),
#                 "driverName": vehicle.get("driverName", ""),
#                 "plate": vehicle.get("plate", ""),
#                 "device_id": vehicle.get("device_id")
#             }
#             vehicles.append(VehicleInDB(**vehicle_data))
#         return vehicles
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Error retrieving vehicles: {str(e)}")


@router.get("/all/{fleet_id}", response_model=List[VehicleInDB])
def get_all_vehicles(fleet_id: str, current_user: dict = Depends(user_or_admin_required)):
    try:
        vehicles_cursor = vehicle_collection.find({
            "$or": [
                {"fleet_id": fleet_id},
                {"fleet_id": ObjectId(fleet_id)} if ObjectId.is_valid(
                    fleet_id) else {}
            ]
        })

        vehicles = []
        for vehicle in vehicles_cursor:
            vehicle_data = serialize_vehicle(vehicle)
            vehicles.append(VehicleInDB(**vehicle_data))

        return vehicles

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error retrieving vehicles: {str(e)}")


@router.get("/track/{id}", response_model=VehicleTrackResponse)
def track_vehicle(id: str, current_user: dict = Depends(user_or_admin_required)):
    try:
        vehicle = vehicle_collection.find_one({"_id": ObjectId(id)})
    except:
        raise HTTPException(
            status_code=400, detail="Invalid vehicle ID format")

    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")

    vehicle_location = vehicle.get("location", {})
    if not vehicle_location.get("latitude") or not vehicle_location.get("longitude"):
        raise HTTPException(
            status_code=400, detail="Vehicle location unavailable")

    return VehicleTrackResponse(
        id=str(vehicle["_id"]),
        location=Location(
            latitude=vehicle_location["latitude"],
            longitude=vehicle_location["longitude"]
        ),
        available_seats=vehicle.get("available_seats", 0),
        status=VehicleStatus(vehicle["status"]),
        route=vehicle.get("route", ""),
        driverName=vehicle.get("driverName", ""),
        plate=vehicle.get("plate", "")
    )

# ADDED TO WEBSOCKET

# You can create a separate endpoint to update device_id when the IoT device is registered


@router.put("/assign-device/{vehicle_id}")
async def assign_device_id(vehicle_id: str, device_id: str, current_user: dict = Depends(super_and_admin_required)):
    try:
        result = vehicle_collection.update_one(
            {"_id": ObjectId(vehicle_id)},
            {"$set": {"device_id": device_id}}
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Vehicle not found")

        # Broadcast vehicle lists if the vehicle is available and has a valid location
        vehicle = vehicle_collection.find_one({"_id": ObjectId(vehicle_id)})
        fleet_id = str(vehicle.get("fleet_id", ""))
        await broadcast_vehicle_list(fleet_id)
        if vehicle.get("status") == "available" and vehicle.get("location", {}).get("latitude") and vehicle.get("location", {}).get("longitude"):
            await broadcast_available_vehicle_list(fleet_id)

        return {"message": "Device ID assigned successfully"}
    except ValueError:
        raise HTTPException(
            status_code=400, detail="Invalid vehicle ID format")


@router.delete("/{vehicle_id}")
async def delete_vehicle(vehicle_id: str, current_user: dict = Depends(super_and_admin_required)):
    try:
        vehicle = vehicle_collection.find_one({"_id": ObjectId(vehicle_id)})
        if not vehicle:
            raise HTTPException(status_code=404, detail="Vehicle not found")

        fleet_id = str(vehicle.get("fleet_id", ""))
        result = vehicle_collection.delete_one({"_id": ObjectId(vehicle_id)})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Vehicle not found")

        # Broadcast vehicle count and vehicle lists
        total_vehicles = vehicle_collection.count_documents({})
        await vehicle_count_manager.broadcast({"total_vehicles": total_vehicles})
        await broadcast_vehicle_list(fleet_id)
        if vehicle.get("status") == "available" and vehicle.get("location", {}).get("latitude") and vehicle.get("location", {}).get("longitude"):
            await broadcast_available_vehicle_list(fleet_id)

        return {"message": "Vehicle deleted"}
    except ValueError:
        raise HTTPException(
            status_code=400, detail="Invalid vehicle ID format")


@router.websocket("/ws/count-vehicles")
async def websocket_count_vehicles(websocket: WebSocket):
    await vehicle_count_manager.connect(websocket)
    collection = vehicle_collection

    try:
        # Try sending initial count
        total_vehicles = collection.count_documents({})
        await websocket.send_json({"total_vehicles": total_vehicles})

        # Keep connection alive (listen for pings/messages)
        while True:
            await websocket.receive_text()

    except WebSocketDisconnect:
        vehicle_count_manager.disconnect(websocket)
        print("Client disconnected from /ws/count-vehicles")

    except Exception as e:
        # Log other errors, but don’t try to send_json here
        print(f"Unexpected error in /ws/count-vehicles: {e}")
        vehicle_count_manager.disconnect(websocket)


# @router.websocket("/ws/vehicles/available/{fleet_id}")
# async def available_vehicles_ws(websocket: WebSocket, fleet_id: str):
#     """Stream only available vehicles that have a location"""
#     await vehicle_all_manager.connect(websocket, fleet_id)
#     try:
#         # Send initial list of available vehicles
#         query = {
#             "fleet_id": fleet_id,
#             "status": {"$in": ["available", "full"]},
#             "location.latitude": {"$ne": None},
#             "location.longitude": {"$ne": None}
#         }
#         vehicles = [
#             {
#                 "id": str(vehicle["_id"]),
#                 "location": vehicle.get("location"),
#                 "available_seats": vehicle.get("available_seats", 0),
#                 "route": vehicle.get("route", ""),
#                 "driverName": vehicle.get("driverName", ""),
#                 "plate": vehicle.get("plate", ""),
#                 "status": vehicle.get("status", "unavailable"),
#                 "bound_for": vehicle.get("bound_for")
#             }
#             for vehicle in vehicle_collection.find(query)
#         ]
#         await websocket.send_json({"vehicles": vehicles})

#         while True:
#             # Keep connection alive
#             await websocket.receive_text()

#     except WebSocketDisconnect:
#         vehicle_all_manager.disconnect(websocket, fleet_id)
#         print(f"Available vehicle stream for fleet {fleet_id} disconnected")
#     except Exception as e:
#         vehicle_all_manager.disconnect(websocket, fleet_id)
#         print(
#             f"Error in available vehicles WebSocket for fleet {fleet_id}: {e}")

# NEWLY ADDED


@router.websocket("/ws/vehicles/all/{fleet_id}")
async def websocket_all_vehicles(websocket: WebSocket, fleet_id: str):
    """
    WebSocket endpoint to stream all vehicles for a specific fleet in real-time.
    """
    await vehicle_all_manager.connect(websocket, fleet_id)
    try:
        # Send initial vehicle list
        vehicles = [
            serialize_vehicle(vehicle)
            for vehicle in vehicle_collection.find({"fleet_id": fleet_id})
        ]
        await websocket.send_json({"vehicles": vehicles})

        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        vehicle_all_manager.disconnect(websocket, fleet_id)
        print(f"Client disconnected from vehicles/all/{fleet_id}")
    except Exception as e:
        vehicle_all_manager.disconnect(websocket, fleet_id)
        print(f"Error in vehicles WebSocket for fleet {fleet_id}: {e}")

# ========================
# IoT status update endpoints
# ========================


class IoTStatusUpdate(BaseModel):
    key: str


def _map_key_to_status_and_detail(key: str):
    """Map IoT keypad key to canonical status and optional detail string.

    We preserve only the enum-friendly statuses in `status` to avoid breaking
    existing filters and counts, and put nuance in `status_detail`.
    """
    k = (key or "").strip().upper()
    if k == '1':
        return (VehicleStatus.full.value, "full")
    if k == '2':
        return (VehicleStatus.available.value, "available")
    if k == 'A':  # STANDING -> treat as available, keep detail
        return (VehicleStatus.available.value, "standing")
    if k == '4':  # INACTIVE -> treat as unavailable, keep detail
        return (VehicleStatus.unavailable.value, "inactive")
    return (None, None)


@router.post("/status/device/{device_id}")
async def update_status_by_device(device_id: str, payload: IoTStatusUpdate):
    """Update a vehicle's status using an IoT keypad key, addressing by device_id.

    Mappings:
    - '1' -> FULL
    - '2' -> AVAILABLE
    - 'A' -> STANDING (treated as AVAILABLE in `status`, stored in `status_detail`)
    - '4' -> INACTIVE (treated as UNAVAILABLE in `status`, stored in `status_detail`)

    Note: '5' (HELP REQUESTED) is handled via a separate endpoint.
    """
    vehicle = vehicle_collection.find_one({"device_id": device_id})
    if not vehicle:
        raise HTTPException(
            status_code=404, detail="Vehicle with that device_id not found")

    status_value, detail = _map_key_to_status_and_detail(payload.key)
    if not status_value:
        raise HTTPException(
            status_code=400, detail="Unsupported key. Use '1','2','A','4' or call help endpoint for '5'.")

    update_doc = {"status": status_value}
    if detail:
        update_doc["status_detail"] = detail

    result = vehicle_collection.update_one(
        {"_id": vehicle["_id"]},
        {"$set": update_doc}
    )

    # Broadcast updated lists for the fleet
    fleet_id = str(vehicle.get("fleet_id", ""))
    await broadcast_vehicle_list(fleet_id)

    # If newly available and has a valid location, broadcast available list
    v_after = vehicle_collection.find_one({"_id": vehicle["_id"]})
    loc = v_after.get("location") if v_after else None
    if (
        v_after
        and v_after.get("status") == VehicleStatus.available.value
        and isinstance(loc, dict)
        and loc.get("latitude") is not None
        and loc.get("longitude") is not None
    ):
        await broadcast_available_vehicle_list(fleet_id)

    return {"message": "Vehicle status updated", "status": status_value, "status_detail": detail}


class HelpRequest(BaseModel):
    message: Optional[str] = None
    key: Optional[Union[str, int]] = None


@router.post("/help-request/device/{device_id}")
async def help_request_by_device(device_id: str, payload: HelpRequest | None = None):
    """Handle HELP REQUESTED from IoT (key '5') by notifying fleet admins."""
    vehicle = vehicle_collection.find_one({"device_id": device_id})
    if not vehicle:
        raise HTTPException(
            status_code=404, detail="Vehicle with that device_id not found")

    # If a key is passed here and it's not '5', reject to avoid misrouting
    if payload and payload.key is not None:
        k = str(payload.key).strip().upper()
        if k != '5':
            raise HTTPException(
                status_code=400, detail="Wrong endpoint for this key. Use /vehicles/status/device for '1','2','A','4', /vehicles/bound-for/device for '6','7', or /vehicles/iot/device for unified handling.")

    fleet_id = str(vehicle.get("fleet_id", ""))
    plate = vehicle.get("plate") or str(vehicle.get("_id"))

    # Find admins for this fleet
    admins_cursor = user_collection.find({
        "role": {"$in": ["admin", "superadmin"]},
        "$or": [
            {"fleet_id": fleet_id},
            {"fleet_id": ObjectId(fleet_id)} if ObjectId.is_valid(
                fleet_id) else {}
        ]
    })

    notified = 0
    details = payload.message if payload and payload.message else ""
    title = "Help requested"
    body = f"Vehicle {plate} has requested help." + \
        (f" Details: {details}" if details else "")

    async def _notify_user(user):
        token = user.get("fcm_token")
        if not token:
            return False
        ok = await send_fcm_notification(token, title, body)
        return ok

    # Notify each admin asynchronously (sequential await to avoid overwhelming FCM)
    for admin in admins_cursor:
        try:
            if await _notify_user(admin):
                notified += 1
        except Exception:
            pass

    # Log the help request
    notification_logs_collection.insert_one({
        "vehicle_id": str(vehicle["_id"]),
        "fleet_id": fleet_id,
        "timestamp": datetime.utcnow(),
        "notification_type": "help_request",
        "message": details
    })

    return {"message": "Help request processed", "admins_notified": notified}


# ========================
# IoT bound_for update endpoint (keys '6' and '7')
# ========================

class IoTBoundForUpdate(BaseModel):
    key: str


def _map_key_to_bound_for(key: str):
    k = (key or "").strip().upper()
    if k == 'B':
        return "IGPIT"
    if k == 'C':
        return "BUGO"
    return None


@router.post("/bound-for/device/{device_id}")
async def update_bound_for_by_device(device_id: str, payload: IoTBoundForUpdate):
    """Update a vehicle's bound_for using IoT keypad key ('B' or 'C')."""
    vehicle = vehicle_collection.find_one({"device_id": device_id})
    if not vehicle:
        raise HTTPException(
            status_code=404, detail="Vehicle with that device_id not found")

    bound_for = _map_key_to_bound_for(payload.key)
    if not bound_for:
        raise HTTPException(
            status_code=400, detail="Unsupported key. Use 'B' for IGPIT or 'C' for BUGO.")

    vehicle_collection.update_one(
        {"_id": vehicle["_id"]},
        {"$set": {"bound_for": bound_for}}
    )

    # Broadcast updated vehicles for the fleet
    fleet_id = str(vehicle.get("fleet_id", ""))
    await broadcast_vehicle_list(fleet_id)

    return {"message": "Vehicle bound_for updated", "bound_for": bound_for}


# ========================
# Unified IoT keypad endpoint
# ========================

class IoTUnifiedUpdate(BaseModel):
    key: str | int
    message: str | None = None


@router.post("/iot/device/{device_id}")
async def iot_keypad_update(device_id: str, payload: IoTUnifiedUpdate):
    """Unified endpoint for IoT keypad events.

    Keys mapping:
    - '1' -> FULL (status)
    - '2' -> AVAILABLE (status)
    - 'A' -> STANDING (treated as AVAILABLE with status_detail)
    - '4' -> INACTIVE (treated as UNAVAILABLE with status_detail)
    - '5' -> HELP REQUESTED (notify admins)
    - 'B' -> BOUND FOR IGPIT
    - 'C' -> BOUND FOR BUGO
    """
    vehicle = vehicle_collection.find_one({"device_id": device_id})
    if not vehicle:
        raise HTTPException(
            status_code=404, detail="Vehicle with that device_id not found")

    k = str(payload.key).strip().upper()

    # Help request (5)
    if k == '5':
        fleet_id = str(vehicle.get("fleet_id", ""))
        plate = vehicle.get("plate") or str(vehicle.get("_id"))
        admins_cursor = user_collection.find({
            "role": {"$in": ["admin", "superadmin"]},
            "$or": [
                {"fleet_id": fleet_id},
                {"fleet_id": ObjectId(fleet_id)} if ObjectId.is_valid(
                    fleet_id) else {}
            ]
        })
        title = "Help requested"
        details = payload.message or ""
        body = f"Vehicle {plate} has requested help." + \
            (f" Details: {details}" if details else "")
        notified = 0
        for admin in admins_cursor:
            token = admin.get("fcm_token")
            if not token:
                continue
            try:
                if await send_fcm_notification(token, title, body):
                    notified += 1
            except Exception:
                pass

        notification_logs_collection.insert_one({
            "vehicle_id": str(vehicle["_id"]),
            "fleet_id": fleet_id,
            "timestamp": datetime.utcnow(),
            "notification_type": "help_request",
            "message": details
        })
        return {"message": "Help request processed", "admins_notified": notified}

    # Status updates (1,2,A,4)
    status_value, detail = _map_key_to_status_and_detail(k)
    if status_value:
        update_doc = {"status": status_value}
        if detail:
            update_doc["status_detail"] = detail
        vehicle_collection.update_one(
            {"_id": vehicle["_id"]}, {"$set": update_doc})

        fleet_id = str(vehicle.get("fleet_id", ""))
        await broadcast_vehicle_list(fleet_id)
        v_after = vehicle_collection.find_one({"_id": vehicle["_id"]})
        loc = v_after.get("location") if v_after else None
        if (
            v_after
            and v_after.get("status") == VehicleStatus.available.value
            and isinstance(loc, dict)
            and loc.get("latitude") is not None
            and loc.get("longitude") is not None
        ):
            await broadcast_available_vehicle_list(fleet_id)
        return {"message": "Vehicle status updated", "status": status_value, "status_detail": detail}

    # Bound for (B,C)
    bound_for = _map_key_to_bound_for(k)
    if bound_for:
        vehicle_collection.update_one({"_id": vehicle["_id"]}, {
                                      "$set": {"bound_for": bound_for}})
        fleet_id = str(vehicle.get("fleet_id", ""))
        await broadcast_vehicle_list(fleet_id)
        return {"message": "Vehicle bound_for updated", "bound_for": bound_for}

    # Unsupported
    raise HTTPException(
        status_code=400, detail="Unsupported key. Use '1','2','A','4','5','B','C'.")
