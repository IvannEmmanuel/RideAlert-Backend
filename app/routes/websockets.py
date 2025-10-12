from fastapi import WebSocket, WebSocketDisconnect, APIRouter
from bson import ObjectId
from pydantic import ValidationError
from app.database import vehicle_collection, user_collection, db
from app.schemas.vehicle import Location as VehicleLocation
from app.schemas.user import Location as UserLocation
from app.utils.notifications import check_and_notify
from typing import Dict, List
import asyncio
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

ws_router = APIRouter(tags=["WebSocket"])


# device_id -> subscribers (for IoT device location updates)
device_subscribers: Dict[str, List[WebSocket]] = {}
# Global device location feed
all_device_updates_subscribers: List[WebSocket] = []


@ws_router.websocket("/ws/user-location")
async def update_user_location(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()

            user_id = data.get("user_id")
            location_data = data.get("location")

            # Validate ObjectId format
            try:
                oid = ObjectId(user_id)
            except Exception:
                await websocket.send_text("Invalid user-id format")
                continue

            # Validate location schema
            try:
                location = UserLocation(**location_data)
            except ValidationError:
                await websocket.send_text("The user location is invalid")
                continue

            # Check if user actually exists before updating
            user = user_collection.find_one({"_id": oid})
            if not user:
                await websocket.send_text(f"User {user_id} not found")
                continue

            # Ensure fleet_id exists
            if not user.get("fleet_id"):
                logger.error(f"No fleet_id for user {user_id}")
                await websocket.send_text("User missing fleet_id")
                continue

            fleet_id = user["fleet_id"]  # ObjectId or str

            # Update location
            result = user_collection.update_one(
                {"_id": oid},
                {"$set": {"location": location.dict()}}
            )

            if result.modified_count == 1:
                await websocket.send_text(f"Location updated for user {user_id}")

                # Trigger proximity checks against fleet vehicles
                try:
                    # Query available vehicles in user's fleet with valid locations
                    fleet_query = {
                        "fleet_id": fleet_id,
                        "status": "available",
                        "$or": [
                            {"location.latitude": {"$exists": True, "$ne": None}},
                            {"location.longitude": {"$exists": True, "$ne": None}}
                        ]
                    }
                    vehicles = list(vehicle_collection.find(fleet_query))

                    logger.info(
                        f"Checking proximity for user {user_id} against {len(vehicles)} vehicles in fleet {fleet_id}")

                    # For each vehicle, check distance and notify if close
                    notified_count = 0
                    for vehicle in vehicles:
                        vehicle_id = str(vehicle["_id"])
                        vehicle_loc = vehicle.get("location")
                        if vehicle_loc and vehicle_loc.get("latitude") and vehicle_loc.get("longitude"):
                            success = await check_and_notify(
                                str(oid),  # user_id
                                location,  # UserLocation object
                                # Mock for VehicleLocation
                                type("VehicleLoc", (), vehicle_loc)(),
                                vehicle_id  # For anti-spam
                            )
                            if success:
                                notified_count += 1

                    logger.info(
                        f"Proximity checks complete for user {user_id}: {notified_count} notifications sent")

                except Exception as check_err:
                    logger.error(
                        f"Error in proximity checks for user {user_id}: {check_err}")
                    await websocket.send_text(f"Proximity check failed: {check_err}")
            else:
                await websocket.send_text(f"No location change made for user {user_id}")

    except WebSocketDisconnect:
        print("User client is disconnected")


# para track ang devices continuously no need to reload

@ws_router.websocket("/ws/track-device")
async def track_device_ws(websocket: WebSocket):
    await websocket.accept()
    device_id = None
    try:
        data = await websocket.receive_json()
        device_id = data.get("device_id")
        if not device_id:
            await websocket.send_text("device_id required")
            await websocket.close()
            return

        if device_id not in device_subscribers:
            device_subscribers[device_id] = []
        device_subscribers[device_id].append(websocket)

        # Send initial connection confirmation describing channel purpose
        await websocket.send_json({
            "type": "connection_established",
            "device_id": device_id,
            "message": f"Continuous tracking channel: Only broadcasts location updates for device {device_id}.",
            "timestamp": datetime.utcnow().isoformat()
        })

        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if device_id and device_id in device_subscribers:
            subs = device_subscribers[device_id]
            if websocket in subs:
                subs.remove(websocket)
                if not subs:
                    device_subscribers.pop(device_id)
        print("Device tracking client disconnected from user")

# para count tanan vehicles continuously (bisan newly created) no need to reload


# @ws_router.websocket("/ws/vehicle-counts")
# async def vehicle_counts_ws(websocket: WebSocket):
#     await websocket.accept()
#     try:
#         while True:
#             # Query DB for counts
#             total = vehicle_collection.count_documents({})
#             available = vehicle_collection.count_documents(
#                 {"status": "available"})
#             full = vehicle_collection.count_documents({"status": "full"})
#             unavailable = vehicle_collection.count_documents(
#                 {"status": "unavailable"})

#             await websocket.send_json({
#                 "total": total,
#                 "available": available,
#                 "full": full,
#                 "unavailable": unavailable
#             })

#             # You can tune this interval or replace with a change-stream if Mongo supports it
#             await asyncio.sleep(5)
#     except WebSocketDisconnect:
#         print("Vehicle count client disconnected")

@ws_router.websocket("/ws/vehicle-counts/{fleet_id}")
async def vehicle_counts_ws(websocket: WebSocket, fleet_id: str):
    await websocket.accept()
    try:
        while True:
            try:
                # Try converting to ObjectId, fallback to string
                try:
                    fleet_obj_id = ObjectId(fleet_id)
                except:
                    fleet_obj_id = fleet_id

                # Query vehicles where fleet_id matches either string or ObjectId
                vehicles = list(vehicle_collection.find({
                    "$or": [
                        {"fleet_id": fleet_obj_id},
                        {"fleet_id": str(fleet_obj_id)}
                    ]
                }))

                total = len(vehicles)
                available = sum(1 for v in vehicles if v.get(
                    "status") == "available")
                full = sum(1 for v in vehicles if v.get("status") == "full")
                unavailable = sum(1 for v in vehicles if v.get(
                    "status") == "unavailable")

                await websocket.send_json({
                    "fleet_id": fleet_id,
                    "total": total,
                    "available": available,
                    "full": full,
                    "unavailable": unavailable
                })
            except Exception as e:
                await websocket.send_json({"error": str(e)})

            await asyncio.sleep(3)  # update every 3 seconds
    except WebSocketDisconnect:
        print(f"Client disconnected from {fleet_id} vehicle count stream")


# para makita tanan vehicles continuously (bisan newly created) no need to reload
@ws_router.websocket("/ws/vehicles/all/{fleet_id}")
async def all_vehicles_ws(websocket: WebSocket, fleet_id: str):
    await websocket.accept()
    try:
        while True:
            vehicles = []
            # Filter vehicles by fleet_id
            for vehicle in vehicle_collection.find({"fleet_id": fleet_id}):
                vehicles.append({
                    "id": str(vehicle["_id"]),
                    "location": vehicle.get("location"),  # can be None
                    "available_seats": vehicle.get("available_seats", 0),
                    "status": vehicle.get("status", "unavailable"),
                    "route": vehicle.get("route", ""),
                    "driverName": vehicle.get("driverName", ""),
                    "bound_for": vehicle.get("bound_for"),
                    "plate": vehicle.get("plate", "")
                })

            # Send updated list of vehicles for this fleet
            await websocket.send_json(vehicles)
            await asyncio.sleep(5)  # every 5 sec update

    except WebSocketDisconnect:
        print(
            f"Vehicle list WebSocket client for fleet {fleet_id} disconnected")


@ws_router.websocket("/ws/vehicles/available/{fleet_id}")
async def available_vehicles_ws(websocket: WebSocket, fleet_id: str):
    """Stream only available vehicles that have a location"""
    await websocket.accept()
    try:
        while True:
            vehicles = []
            # Query: only available vehicles with non-null latitude and longitude
            query = {
                "fleet_id": fleet_id,
                "status": {"$in": ["available", "full"]},
                "location.latitude": {"$ne": None},
                "location.longitude": {"$ne": None}
            }

            for vehicle in vehicle_collection.find(query):
                vehicles.append({
                    "id": str(vehicle["_id"]),
                    "location": vehicle.get("location"),
                    "available_seats": vehicle.get("available_seats", 0),
                    "route": vehicle.get("route", ""),
                    "driverName": vehicle.get("driverName", ""),
                    "plate": vehicle.get("plate", ""),
                    "status": vehicle.get("status", "unavailable"),
                    "bound_for": vehicle.get("bound_for"),
                    "status_details": vehicle.get("status_detail")
                })

            await websocket.send_json(vehicles)
            await asyncio.sleep(5)  # send updates every 5 seconds

    except WebSocketDisconnect:
        print(f"Available vehicle stream for fleet {fleet_id} disconnected")


# New WebSocket endpoint for vehicle-specific location monitoring via IoT predictions


# Function to broadcast device location updates (call from predict.py)
async def broadcast_prediction(device_id: str, fleet_id: str, prediction_data: dict, ml_request_data: dict, response_time_ms: float):
    """Broadcast device location update from IoT device ML prediction to WebSocket subscribers"""

    broadcast_message = {
        "type": "location_update",
        "timestamp": datetime.utcnow().isoformat(),
        "device_id": device_id,
        "latitude": prediction_data.get("latitude"),
        "longitude": prediction_data.get("longitude")
    }

    # Broadcast to device-specific subscribers
    device_subs = device_subscribers.get(device_id, [])
    disconnected_subs = []

    for ws in device_subs:
        try:
            await ws.send_json(broadcast_message)
        except Exception as e:
            print(f"Error sending to device {device_id} subscriber: {e}")
            disconnected_subs.append(ws)

    for ws in disconnected_subs:
        device_subs.remove(ws)

    # Broadcast to global device location subscribers
    global_disconnected = []
    for ws in all_device_updates_subscribers:
        try:
            await ws.send_json(broadcast_message)
        except Exception as e:
            print(f"Error sending to global device location subscriber: {e}")
            global_disconnected.append(ws)

    for ws in global_disconnected:
        all_device_updates_subscribers.remove(ws)
