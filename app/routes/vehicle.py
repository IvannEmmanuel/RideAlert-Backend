# Endpoint for fleet admin to assign route_id to a vehicle
from app.utils.notifications import send_fcm_notification
from app.utils.ws_manager import vehicle_count_manager, vehicle_all_manager, stats_count_manager, stats_verified_manager, eta_manager
from app.utils.geo import haversine
import asyncio
from datetime import datetime, timedelta
from typing import List
from app.schemas.vehicle import VehicleTrackResponse, Location, VehicleStatus, VehicleBase, VehicleInDB
from app.dependencies.roles import user_required, admin_required, user_or_admin_required, super_and_admin_required
from bson import ObjectId
from app.database import vehicle_collection, tracking_logs_collection, user_collection, notification_logs_collection
from app.database import get_fleets_collection
from pydantic import BaseModel
from fastapi import Body
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from typing import Optional, Union, Dict

router = APIRouter(prefix="/vehicles", tags=["Vehicles"])

active_eta_subscriptions: Dict[str, Dict] = {}

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
    confidence: str


async def broadcast_stats_update():
    """Broadcast updated stats to all connected stats WebSocket clients"""
    try:
        # Update for /stats/count
        total_vehicles = vehicle_collection.count_documents({})
        total_users = user_collection.count_documents({})
        total_fleets = get_fleets_collection.count_documents({})

        count_data = {
            "type": "stats_count",
            "data": {
                "total_vehicles": total_vehicles,
                "total_users": total_users,
                "total_fleets": total_fleets
            }
        }
        await stats_count_manager.broadcast(count_data)

        # Update for /stats/verified
        fleets_col = get_fleets_collection
        verified_cursor = fleets_col.find(
            {"role": "admin", "is_active": True}, {"_id": 1})
        verified_ids = [str(f.get("_id")) for f in verified_cursor]

        if verified_ids:
            from bson import ObjectId as _ObjectId
            id_filters = []
            for fid in verified_ids:
                if _ObjectId.is_valid(fid):
                    id_filters.append({"fleet_id": _ObjectId(fid)})
                id_filters.append({"fleet_id": fid})

            query = {"$or": id_filters}
            verified_vehicles = vehicle_collection.count_documents(query)
        else:
            verified_vehicles = 0

        total_vehicles = vehicle_collection.count_documents({})
        unverified_vehicles = total_vehicles - verified_vehicles

        verified_data = {
            "type": "stats_verified",
            "data": {
                "verified_vehicles": verified_vehicles,
                "unverified_vehicles": unverified_vehicles,
                "total_vehicles": total_vehicles,
                "verified_percentage": (verified_vehicles / total_vehicles * 100) if total_vehicles > 0 else 0
            }
        }
        await stats_verified_manager.broadcast(verified_data)

    except Exception as e:
        print(f"Error broadcasting stats update: {e}")


# @router.put("/assign-route/{vehicle_id}")
# async def assign_route_id(vehicle_id: str, route_id: str, current_user: dict = Depends(super_and_admin_required)):
#     try:
#         result = vehicle_collection.update_one(
#             {"_id": ObjectId(vehicle_id)},
#             {"$set": {"route_id": route_id}}
#         )
#         if result.matched_count == 0:
#             raise HTTPException(status_code=404, detail="Vehicle not found")

#         # Broadcast vehicle lists if the vehicle is available and has a valid location
#         vehicle = vehicle_collection.find_one({"_id": ObjectId(vehicle_id)})
#         fleet_id = str(vehicle.get("fleet_id", ""))
#         await broadcast_vehicle_list(fleet_id)
#         if vehicle.get("status") == "available" and vehicle.get("location", {}).get("latitude") and vehicle.get("location", {}).get("longitude"):
#             await broadcast_available_vehicle_list(fleet_id)

#         return {"message": "Route ID assigned successfully"}
#     except ValueError:
#         raise HTTPException(
#             status_code=400, detail="Invalid vehicle ID format")

@router.put("/assign-route/{vehicle_id}")
async def assign_route_id(vehicle_id: str, route_id: str, current_user: dict = Depends(super_and_admin_required)):
    try:
        result = vehicle_collection.update_one(
            {"_id": ObjectId(vehicle_id)},
            {"$set": {"route_id": route_id}}
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Vehicle not found")

        # Broadcast vehicle lists if the vehicle is available and has a valid location
        vehicle = vehicle_collection.find_one({"_id": ObjectId(vehicle_id)})
        fleet_id = str(vehicle.get("fleet_id", ""))
        await broadcast_vehicle_list(fleet_id)

        # NEW: Broadcast stats updates
        await broadcast_stats_update()

        if vehicle.get("status") == "available" and vehicle.get("location", {}).get("latitude") and vehicle.get("location", {}).get("longitude"):
            await broadcast_available_vehicle_list(fleet_id)

        return {"message": "Route ID assigned successfully"}
    except ValueError:
        raise HTTPException(
            status_code=400, detail="Invalid vehicle ID format")


def get_speed_history(device_id: str, minutes: int = 5) -> list:
    """Get speed history for the last N minutes"""
    time_threshold = datetime.utcnow() - timedelta(minutes=minutes)
    timestamp_ms = int(time_threshold.timestamp() * 1000)

    tracking_logs = list(tracking_logs_collection.find(
        {
            "device_id": device_id,
            "timestamp": {"$gte": timestamp_ms}
        },
        sort=[("timestamp", -1)],
        limit=30
    ))

    speeds = []
    for log in tracking_logs:
        speed = log.get("SpeedMps", 0.0)
        speeds.append(speed)

    return speeds


def calculate_average_speed(speeds: list, percentile: float = 0.7) -> float:
    """Calculate average speed using percentile to ignore outliers"""
    if not speeds:
        return 0.0

    valid_speeds = [s for s in speeds if s > 0]
    if not valid_speeds:
        return 0.0

    valid_speeds.sort()
    index = int(len(valid_speeds) * percentile)
    if index >= len(valid_speeds):
        index = len(valid_speeds) - 1

    percentile_speed = valid_speeds[index]
    threshold = percentile_speed / 2
    moving_speeds = [s for s in valid_speeds if s >= threshold]

    if not moving_speeds:
        return percentile_speed

    return sum(moving_speeds) / len(moving_speeds)

def is_vehicle_stopped(current_speed: float, speed_history: list) -> bool:
    """Determine if vehicle is genuinely stopped"""
    if current_speed < 0.5:
        recent_speeds = speed_history[:5]
        if len(recent_speeds) >= 3:
            stopped_count = sum(1 for s in recent_speeds if s < 0.5)
            if stopped_count / len(recent_speeds) > 0.6:
                return True
    return False


def calculate_smart_eta(
    distance_meters: float,
    current_speed_mps: float,
    average_speed_mps: float,
    is_stopped: bool,
    vehicle_status: str
) -> tuple[Optional[float], str, str, str]:
    """Calculate ETA with intelligent handling of stops and traffic"""
    URBAN_SPEED_MPS = 8.33
    SLOW_TRAFFIC_MPS = 5.56
    MIN_SPEED_MPS = 2.78

    if is_stopped:
        effective_speed = average_speed_mps if average_speed_mps > 1.0 else URBAN_SPEED_MPS
        confidence = "medium"
        message = "Vehicle temporarily stopped. ETA based on average speed."

    elif vehicle_status == "standing":
        if average_speed_mps > 1.0:
            effective_speed = average_speed_mps
            confidence = "low"
            message = "Vehicle standing. ETA based on historical speed."
        else:
            effective_speed = URBAN_SPEED_MPS
            confidence = "low"
            message = "Vehicle standing. ETA is estimated."

    elif 0.5 <= current_speed_mps < 3.0:
        if average_speed_mps > current_speed_mps:
            effective_speed = (current_speed_mps * 0.3) + (average_speed_mps * 0.7)
        else:
            effective_speed = (current_speed_mps * 0.7) + (average_speed_mps * 0.3)

        effective_speed = max(effective_speed, MIN_SPEED_MPS)
        confidence = "medium"
        message = "Vehicle in traffic. ETA adjusted for congestion."

    elif current_speed_mps >= 3.0:
        if average_speed_mps > 1.0:
            effective_speed = (current_speed_mps * 0.6) + (average_speed_mps * 0.4)
            confidence = "high"
            message = "Vehicle moving normally. Real-time ETA."
        else:
            effective_speed = current_speed_mps
            confidence = "medium"
            message = "Vehicle moving. ETA based on current speed."

    else:
        effective_speed = URBAN_SPEED_MPS
        confidence = "low"
        message = "Limited data. ETA is estimated."

    # Calculate ETA
    eta_seconds = distance_meters / effective_speed
    eta_minutes = eta_seconds / 60

    # Add buffer for stops
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

@router.websocket("/ws/eta/{vehicle_id}")
async def eta_websocket(websocket: WebSocket, vehicle_id: str):
    """Real-time ETA updates for specific vehicle"""
    await eta_manager.connect(websocket, vehicle_id)
    
    try:
        # Send initial connection confirmation
        await websocket.send_json({
            "type": "eta_connection_established",
            "vehicle_id": vehicle_id,
            "message": "Connected to real-time ETA updates"
        })
        
        # Keep connection alive and listen for messages
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
                
    except WebSocketDisconnect:
        eta_manager.disconnect(websocket, vehicle_id)
        print(f"ETA WebSocket client disconnected for vehicle {vehicle_id}")
    except Exception as e:
        eta_manager.disconnect(websocket, vehicle_id)
        print(f"Error in ETA WebSocket for vehicle {vehicle_id}: {e}")


@router.post("/calculate-eta", response_model=ETAResponse)
async def calculate_vehicle_eta(
    request: ETARequest,
    current_user: dict = Depends(user_or_admin_required)
):
    """
    Calculate SMART distance and ETA with traffic-aware logic.
    Also broadcasts real-time updates via WebSocket.
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

    # Prepare ETA response data
    eta_response = ETAResponse(
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

    # BROADCAST VIA WEBSOCKET TO ALL LISTENERS
    try:
        eta_data_for_ws = {
            "eta_seconds": eta_minutes * 60 if eta_minutes else None,
            "eta_formatted": eta_formatted,
            "distance_km": round(distance_km, 2),
            "current_speed_kmh": round(current_speed_kmh, 2),
            "average_speed_kmh": round(average_speed_kmh, 2),
            "vehicle_route": vehicle.get("route", "Unknown"),
            "is_stopped": is_stopped_flag,
            "confidence": confidence,
            "message": status_message,
            "vehicle_location": {
                "latitude": vehicle_lat,
                "longitude": vehicle_lon
            },
            "user_location": {
                "latitude": user_lat,
                "longitude": user_lon
            }
        }
        
        await eta_manager.broadcast_eta(request.vehicle_id, eta_data_for_ws)
        print(f"📡 ETA broadcast for vehicle {request.vehicle_id}: {eta_formatted}")
        
    except Exception as e:
        print(f"⚠️ Failed to broadcast ETA via WebSocket: {e}")
        # Don't fail the HTTP response if WebSocket broadcast fails

    return eta_response

@router.post("/eta/subscribe")
async def subscribe_to_eta_updates(
    request: ETARequest,
    current_user: dict = Depends(user_or_admin_required)
):
    """Subscribe to real-time ETA updates for a vehicle"""
    if not ObjectId.is_valid(request.vehicle_id):
        raise HTTPException(status_code=400, detail="Invalid vehicle ID format")

    # Store the subscription
    active_eta_subscriptions[request.vehicle_id] = {
        "user_location": request.user_location.dict(),
        "last_updated": datetime.utcnow(),
        "user_id": current_user.get("id")
    }

    # Calculate and return initial ETA
    return await calculate_vehicle_eta(request, current_user)

@router.post("/eta/unsubscribe/{vehicle_id}")
async def unsubscribe_from_eta_updates(
    vehicle_id: str,
    current_user: dict = Depends(user_or_admin_required)
):
    """Unsubscribe from ETA updates"""
    if vehicle_id in active_eta_subscriptions:
        subscription = active_eta_subscriptions[vehicle_id]
        if subscription.get("user_id") == current_user.get("id"):
            del active_eta_subscriptions[vehicle_id]
    
    return {"message": "Unsubscribed from ETA updates"}

# Background task to periodically update ETA for active subscriptions
async def background_eta_updater():
    """Periodically calculate and broadcast ETA for active subscriptions"""
    while True:
        try:
            current_time = datetime.utcnow()
            stale_subscriptions = []
            
            for vehicle_id, subscription in active_eta_subscriptions.items():
                # Remove stale subscriptions (older than 5 minutes)
                if (current_time - subscription["last_updated"]).total_seconds() > 300:
                    stale_subscriptions.append(vehicle_id)
                    continue
                
                try:
                    # Create ETA request for background update
                    eta_request = ETARequest(
                        vehicle_id=vehicle_id,
                        user_location=Location(**subscription["user_location"])
                    )
                    
                    # Trigger ETA calculation (this will automatically broadcast via WebSocket)
                    # We need to create a minimal user context for the dependency
                    user_context = {"id": subscription["user_id"]}
                    
                    # Since we can't directly call calculate_vehicle_eta with dependencies,
                    # we'll extract the core logic into a helper function
                    await calculate_and_broadcast_eta(eta_request, user_context)
                    
                except Exception as e:
                    print(f"Error updating ETA for vehicle {vehicle_id}: {e}")
            
            # Remove stale subscriptions
            for vehicle_id in stale_subscriptions:
                del active_eta_subscriptions[vehicle_id]
                print(f"Removed stale ETA subscription for vehicle {vehicle_id}")
            
            await asyncio.sleep(10)  # Update every 10 seconds
            
        except Exception as e:
            print(f"Error in background ETA updater: {e}")
            await asyncio.sleep(30)

async def calculate_and_broadcast_eta(request: ETARequest, user_context: dict):
    """Helper function to calculate ETA without HTTP dependencies"""
    try:
        # Validate vehicle_id
        if not ObjectId.is_valid(request.vehicle_id):
            return

        # Fetch vehicle
        vehicle = vehicle_collection.find_one({"_id": ObjectId(request.vehicle_id)})
        if not vehicle:
            return

        # Get vehicle location
        vehicle_location = vehicle.get("location")
        if not vehicle_location or not vehicle_location.get("latitude") or not vehicle_location.get("longitude"):
            return

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
        is_stopped_flag = False

        if device_id:
            latest_tracking = tracking_logs_collection.find_one(
                {"device_id": device_id},
                sort=[("timestamp", -1)]
            )

            if latest_tracking:
                current_speed_mps = latest_tracking.get("SpeedMps", 0.0)
                tracking_timestamp = latest_tracking.get("timestamp")
                if tracking_timestamp:
                    tracking_time = datetime.fromtimestamp(tracking_timestamp / 1000)
                    time_diff = datetime.utcnow() - tracking_time

                    if time_diff <= timedelta(minutes=2):
                        speed_history = get_speed_history(device_id, minutes=5)
                        if speed_history:
                            average_speed_mps = calculate_average_speed(speed_history)
                            is_stopped_flag = is_vehicle_stopped(current_speed_mps, speed_history)

        # Get vehicle status and calculate ETA
        vehicle_status_detail = vehicle.get("status_detail", "").lower()
        eta_minutes, eta_formatted, confidence, status_message = calculate_smart_eta(
            distance_meters,
            current_speed_mps,
            average_speed_mps,
            is_stopped_flag,
            vehicle_status_detail
        )

        # Convert speeds to km/h
        current_speed_kmh = current_speed_mps * 3.6
        average_speed_kmh = average_speed_mps * 3.6

        # Prepare and broadcast ETA data
        eta_data_for_ws = {
            "eta_seconds": eta_minutes * 60 if eta_minutes else None,
            "eta_formatted": eta_formatted,
            "distance_km": round(distance_km, 2),
            "current_speed_kmh": round(current_speed_kmh, 2),
            "average_speed_kmh": round(average_speed_kmh, 2),
            "vehicle_route": vehicle.get("route", "Unknown"),
            "is_stopped": is_stopped_flag,
            "confidence": confidence,
            "message": status_message,
            "vehicle_location": {
                "latitude": vehicle_lat,
                "longitude": vehicle_lon
            },
            "user_location": {
                "latitude": user_lat,
                "longitude": user_lon
            }
        }
        
        await eta_manager.broadcast_eta(request.vehicle_id, eta_data_for_ws)
        print(f"🔄 Background ETA update for vehicle {request.vehicle_id}: {eta_formatted}")
        
    except Exception as e:
        print(f"Error in calculate_and_broadcast_eta: {e}")


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


@router.get("/{vehicle_id}")
async def get_vehicle(vehicle_id: str):
    """Return vehicle document by id or device_id (string or ObjectId)."""
    try:
        # Try treating as ObjectId first
        query = None
        if ObjectId.is_valid(vehicle_id):
            query = {"$or": [{"_id": ObjectId(vehicle_id)}, {
                "device_id": vehicle_id}]}
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
            "fleet_id": str(vehicle.get("fleet_id")) if vehicle.get("fleet_id") else None,
            "status": vehicle.get("status"),
        }
        print(f"GET /vehicles/{vehicle_id} response: {resp}")
        return resp
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in get_vehicle: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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

    # NEW: Broadcast stats updates
    await broadcast_stats_update()

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


@router.get("/count/verified")
def count_verified_fleet_vehicles(current_user: dict = Depends(super_and_admin_required)):
    """
    Return the total count of vehicle documents that belong to verified fleets.

    Verified fleets are considered those with `role` == 'admin' and `is_active` == True.
    """
    try:
        fleets_col = get_fleets_collection

        # Find all verified fleets and grab their _id values
        verified_cursor = fleets_col.find(
            {"role": "admin", "is_active": True}, {"_id": 1})
        verified_ids = [str(f.get("_id")) for f in verified_cursor]

        if not verified_ids:
            return {"verified_vehicle_count": 0}

        # Vehicles may store fleet_id as ObjectId or string; build an $or query
        from bson import ObjectId as _ObjectId
        id_filters = []
        for fid in verified_ids:
            if _ObjectId.is_valid(fid):
                id_filters.append({"fleet_id": _ObjectId(fid)})
            id_filters.append({"fleet_id": fid})

        query = {"$or": id_filters}
        count = vehicle_collection.count_documents(query)
        return {"verified_vehicle_count": count}

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error counting verified vehicles: {str(e)}")


@router.get("/counts")
def get_vehicle_counts_by_fleet(current_user: dict = Depends(super_and_admin_required)):
    """
    Return vehicle counts grouped by fleet_id.

    Response format:
      { "counts": [ { "fleet_id": "<id>", "count": 12 }, ... ] }

    This handles fleet_id stored as ObjectId or string by converting to string in aggregation.
    """
    try:
        # Use aggregation to group vehicles by fleet_id (string)
        pipeline = [
            {"$group": {"_id": {"$toString": "$fleet_id"}, "count": {"$sum": 1}}},
        ]
        agg = list(vehicle_collection.aggregate(pipeline))
        counts = [{"fleet_id": item["_id"], "count": item["count"]}
                  for item in agg]
        return {"counts": counts}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error aggregating vehicle counts: {str(e)}")


@router.get("/stats/counts-http")
def get_vehicle_counts_by_fleet_stats(current_user: dict = Depends(super_and_admin_required)):
    """
    HTTP endpoint for vehicle counts grouped by fleet_id.
    """
    try:
        pipeline = [
            {"$group": {"_id": {"$toString": "$fleet_id"}, "count": {"$sum": 1}}},
        ]
        agg = list(vehicle_collection.aggregate(pipeline))
        counts = [{"fleet_id": item["_id"], "count": item["count"]}
                  for item in agg]
        return {"counts": counts}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error aggregating vehicle counts: {str(e)}")


@router.websocket("/stats/count")
async def stats_count_websocket(websocket: WebSocket):
    """
    WebSocket endpoint for real-time stats count updates.
    Sends total vehicles, users, and fleets count.
    """
    await stats_count_manager.connect(websocket)
    try:
        # Send initial data when client connects
        total_vehicles = vehicle_collection.count_documents({})
        total_users = user_collection.count_documents({})
        total_fleets = get_fleets_collection.count_documents({})

        initial_data = {
            "type": "stats_count",
            "data": {
                "total_vehicles": total_vehicles,
                "total_users": total_users,
                "total_fleets": total_fleets
            }
        }
        await websocket.send_json(initial_data)

        # Keep connection alive and wait for updates
        while True:
            # Client can send ping or just wait for updates
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")

    except WebSocketDisconnect:
        stats_count_manager.disconnect(websocket)
        print("Client disconnected from /stats/count")
    except Exception as e:
        stats_count_manager.disconnect(websocket)
        print(f"Error in /stats/count WebSocket: {e}")


@router.get("/stats/verified-http")
def count_verified_fleet_vehicles_stats(current_user: dict = Depends(super_and_admin_required)):
    """
    HTTP endpoint for total count of vehicles for verified fleets.
    """
    try:
        fleets_col = get_fleets_collection
        verified_cursor = fleets_col.find(
            {"role": "admin", "is_active": True}, {"_id": 1})
        verified_ids = [str(f.get("_id")) for f in verified_cursor]
        if not verified_ids:
            return {"verified_vehicle_count": 0}
        from bson import ObjectId as _ObjectId
        id_filters = []
        for fid in verified_ids:
            if _ObjectId.is_valid(fid):
                id_filters.append({"fleet_id": _ObjectId(fid)})
            id_filters.append({"fleet_id": fid})
        query = {"$or": id_filters}
        count = vehicle_collection.count_documents(query)
        return {"verified_vehicle_count": count}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error counting verified vehicles: {str(e)}")


@router.websocket("/stats/verified")
async def stats_verified_websocket(websocket: WebSocket):
    """
    WebSocket endpoint for real-time verified vehicles stats.
    Sends verified vehicles count and percentage.
    """
    await stats_verified_manager.connect(websocket)
    try:
        # Send initial data when client connects
        fleets_col = get_fleets_collection
        verified_cursor = fleets_col.find(
            {"role": "admin", "is_active": True}, {"_id": 1})
        verified_ids = [str(f.get("_id")) for f in verified_cursor]

        if verified_ids:
            from bson import ObjectId as _ObjectId
            id_filters = []
            for fid in verified_ids:
                if _ObjectId.is_valid(fid):
                    id_filters.append({"fleet_id": _ObjectId(fid)})
                id_filters.append({"fleet_id": fid})

            query = {"$or": id_filters}
            verified_vehicles = vehicle_collection.count_documents(query)
        else:
            verified_vehicles = 0

        total_vehicles = vehicle_collection.count_documents({})
        unverified_vehicles = total_vehicles - verified_vehicles

        initial_data = {
            "type": "stats_verified",
            "data": {
                "verified_vehicles": verified_vehicles,
                "unverified_vehicles": unverified_vehicles,
                "total_vehicles": total_vehicles,
                "verified_percentage": (verified_vehicles / total_vehicles * 100) if total_vehicles > 0 else 0
            }
        }
        await websocket.send_json(initial_data)

        # Keep connection alive and wait for updates
        while True:
            # Client can send ping or just wait for updates
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")

    except WebSocketDisconnect:
        stats_verified_manager.disconnect(websocket)
        print("Client disconnected from /stats/verified")
    except Exception as e:
        stats_verified_manager.disconnect(websocket)
        print(f"Error in /stats/verified WebSocket: {e}")


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


# @router.put("/assign-device/{vehicle_id}")
# async def assign_device_id(vehicle_id: str, device_id: str, current_user: dict = Depends(super_and_admin_required)):
#     try:
#         result = vehicle_collection.update_one(
#             {"_id": ObjectId(vehicle_id)},
#             {"$set": {"device_id": device_id}}
#         )
#         if result.matched_count == 0:
#             raise HTTPException(status_code=404, detail="Vehicle not found")

#         # Broadcast vehicle lists if the vehicle is available and has a valid location
#         vehicle = vehicle_collection.find_one({"_id": ObjectId(vehicle_id)})
#         fleet_id = str(vehicle.get("fleet_id", ""))
#         await broadcast_vehicle_list(fleet_id)
#         if vehicle.get("status") == "available" and vehicle.get("location", {}).get("latitude") and vehicle.get("location", {}).get("longitude"):
#             await broadcast_available_vehicle_list(fleet_id)

#         return {"message": "Device ID assigned successfully"}
#     except ValueError:
#         raise HTTPException(
#             status_code=400, detail="Invalid vehicle ID format")

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

        # NEW: Broadcast stats updates
        await broadcast_stats_update()

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

        # NEW: Broadcast stats updates
        await broadcast_stats_update()

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


# @router.post("/status/device/{device_id}")
# async def update_status_by_device(device_id: str, payload: IoTStatusUpdate):
#     """Update a vehicle's status using an IoT keypad key, addressing by device_id.

#     Mappings:
#     - '1' -> FULL
#     - '2' -> AVAILABLE
#     - 'A' -> STANDING (treated as AVAILABLE in `status`, stored in `status_detail`)
#     - '4' -> INACTIVE (treated as UNAVAILABLE in `status`, stored in `status_detail`)

#     Note: '5' (HELP REQUESTED) is handled via a separate endpoint.
#     """
#     vehicle = vehicle_collection.find_one({"device_id": device_id})
#     if not vehicle:
#         raise HTTPException(
#             status_code=404, detail="Vehicle with that device_id not found")

#     status_value, detail = _map_key_to_status_and_detail(payload.key)
#     if not status_value:
#         raise HTTPException(
#             status_code=400, detail="Unsupported key. Use '1','2','A','4' or call help endpoint for '5'.")

#     update_doc = {"status": status_value}
#     if detail:
#         update_doc["status_detail"] = detail

#     result = vehicle_collection.update_one(
#         {"_id": vehicle["_id"]},
#         {"$set": update_doc}
#     )

#     # Broadcast updated lists for the fleet
#     fleet_id = str(vehicle.get("fleet_id", ""))
#     await broadcast_vehicle_list(fleet_id)

#     # If newly available and has a valid location, broadcast available list
#     v_after = vehicle_collection.find_one({"_id": vehicle["_id"]})
#     loc = v_after.get("location") if v_after else None
#     if (
#         v_after
#         and v_after.get("status") == VehicleStatus.available.value
#         and isinstance(loc, dict)
#         and loc.get("latitude") is not None
#         and loc.get("longitude") is not None
#     ):
#         await broadcast_available_vehicle_list(fleet_id)

#     return {"message": "Vehicle status updated", "status": status_value, "status_detail": detail}

@router.post("/status/device/{device_id}")
async def update_status_by_device(device_id: str, payload: IoTStatusUpdate):
    """Update a vehicle's status using an IoT keypad key, addressing by device_id."""
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

    # NEW: Broadcast stats updates (in case status affects verified counts)
    await broadcast_stats_update()

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


@router.post("/bound-for/device/{device_id}")
async def update_bound_for_by_device(device_id: str, payload: IoTBoundForUpdate):
    """Update a vehicle's bound_for using IoT keypad key ('B' or 'C')."""
    vehicle = vehicle_collection.find_one({"device_id": device_id})
    if not vehicle:
        raise HTTPException(
            status_code=404, detail="Vehicle with that device_id not found")

    k = (payload.key or "").strip().upper()
    current_route = vehicle.get("current_route", {})
    start_location = current_route.get("start_location")
    end_location = current_route.get("end_location")
    if k == 'B':
        if not start_location:
            raise HTTPException(
                status_code=400, detail="No start_location set for this vehicle.")
        bound_for = start_location
    elif k == 'C':
        if not end_location:
            raise HTTPException(
                status_code=400, detail="No end_location set for this vehicle.")
        bound_for = end_location
    else:
        raise HTTPException(
            status_code=400, detail="Unsupported key. Use 'B' for start_location or 'C' for end_location.")

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


# @router.post("/iot/device/{device_id}")
# async def iot_keypad_update(device_id: str, payload: IoTUnifiedUpdate):
#     """Unified endpoint for IoT keypad events.

#     Keys mapping:
#     - '1' -> FULL (status)
#     - '2' -> AVAILABLE (status)
#     - 'A' -> STANDING (treated as AVAILABLE with status_detail)
#     - '4' -> INACTIVE (treated as UNAVAILABLE with status_detail)
#     - '5' -> HELP REQUESTED (notify admins)
#     - 'B' -> BOUND FOR IGPIT
#     - 'C' -> BOUND FOR BUGO
#     """
#     vehicle = vehicle_collection.find_one({"device_id": device_id})
#     if not vehicle:
#         raise HTTPException(
#             status_code=404, detail="Vehicle with that device_id not found")

#     k = str(payload.key).strip().upper()

#     # Help request (5)
#     if k == '5':
#         fleet_id = str(vehicle.get("fleet_id", ""))
#         plate = vehicle.get("plate") or str(vehicle.get("_id"))
#         admins_cursor = user_collection.find({
#             "role": {"$in": ["admin", "superadmin"]},
#             "$or": [
#                 {"fleet_id": fleet_id},
#                 {"fleet_id": ObjectId(fleet_id)} if ObjectId.is_valid(
#                     fleet_id) else {}
#             ]
#         })
#         title = "Help requested"
#         details = payload.message or ""
#         body = f"Vehicle {plate} has requested help." + \
#             (f" Details: {details}" if details else "")
#         notified = 0
#         for admin in admins_cursor:
#             token = admin.get("fcm_token")
#             if not token:
#                 continue
#             try:
#                 if await send_fcm_notification(token, title, body):
#                     notified += 1
#             except Exception:
#                 pass

#         notification_logs_collection.insert_one({
#             "vehicle_id": str(vehicle["_id"]),
#             "fleet_id": fleet_id,
#             "timestamp": datetime.utcnow(),
#             "notification_type": "help_request",
#             "message": details
#         })
#         return {"message": "Help request processed", "admins_notified": notified}

#     # Status updates (1,2,A,4)
#     status_value, detail = _map_key_to_status_and_detail(k)
#     if status_value:
#         update_doc = {"status": status_value}
#         if detail:
#             update_doc["status_detail"] = detail
#         vehicle_collection.update_one(
#             {"_id": vehicle["_id"]}, {"$set": update_doc})

#         fleet_id = str(vehicle.get("fleet_id", ""))
#         await broadcast_vehicle_list(fleet_id)
#         v_after = vehicle_collection.find_one({"_id": vehicle["_id"]})
#         loc = v_after.get("location") if v_after else None
#         if (
#             v_after
#             and v_after.get("status") == VehicleStatus.available.value
#             and isinstance(loc, dict)
#             and loc.get("latitude") is not None
#             and loc.get("longitude") is not None
#         ):
#             await broadcast_available_vehicle_list(fleet_id)
#         return {"message": "Vehicle status updated", "status": status_value, "status_detail": detail}

#     # Bound for (B,C)
#     bound_for = _map_key_to_bound_for(k)
#     if bound_for:
#         vehicle_collection.update_one({"_id": vehicle["_id"]}, {
#                                       "$set": {"bound_for": bound_for}})
#         fleet_id = str(vehicle.get("fleet_id", ""))
#         await broadcast_vehicle_list(fleet_id)
#         return {"message": "Vehicle bound_for updated", "bound_for": bound_for}

#     # Unsupported
#     raise HTTPException(
#         status_code=400, detail="Unsupported key. Use '1','2','A','4','5','B','C'.")

@router.post("/iot/device/{device_id}")
async def iot_keypad_update(device_id: str, payload: IoTUnifiedUpdate):
    """Unified endpoint for IoT keypad events."""
    vehicle = vehicle_collection.find_one({"device_id": device_id})
    if not vehicle:
        raise HTTPException(
            status_code=404, detail="Vehicle with that device_id not found")

    k = str(payload.key).strip().upper()

    # Help request (5)
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

        # NEW: Broadcast stats updates
        await broadcast_stats_update()

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

    # Bound for (B,C) using current_route
    current_route = vehicle.get("current_route", {})
    start_location = current_route.get("start_location")
    end_location = current_route.get("end_location")
    if k == 'B':
        if not start_location:
            raise HTTPException(
                status_code=400, detail="No start_location set for this vehicle.")
        bound_for = start_location
    elif k == 'C':
        if not end_location:
            raise HTTPException(
                status_code=400, detail="No end_location set for this vehicle.")
        bound_for = end_location
    else:
        raise HTTPException(
            status_code=400, detail="Unsupported key. Use '1','2','A','4','5','B','C'.")

    vehicle_collection.update_one({"_id": vehicle["_id"]}, {
        "$set": {"bound_for": bound_for}})
    fleet_id = str(vehicle.get("fleet_id", ""))
    await broadcast_vehicle_list(fleet_id)
    return {"message": "Vehicle bound_for updated", "bound_for": bound_for}