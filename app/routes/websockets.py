from fastapi import WebSocket, WebSocketDisconnect, APIRouter
from bson import ObjectId
from pydantic import ValidationError
from app.database import vehicle_collection, user_collection, db
from app.schemas.vehicle import Location as VehicleLocation
from app.schemas.user import Location as UserLocation
from app.utils.tracking_logs import insert_gps_log
from app.utils.notifications import check_and_notify
from typing import Dict, List
import asyncio

ws_router = APIRouter(tags=["WebSocket"])

vehicle_subscribers: Dict[str, List[WebSocket]] = {}

@ws_router.websocket("/ws/location")
async def update_location(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()

            vehicle_id = data.get("vehicle_id")
            location_data = data.get("location")

            # Validate ObjectId
            try:
                oid = ObjectId(vehicle_id)
            except Exception:
                await websocket.send_text("Invalid vehicle_id format")
                continue

            # Debug: print all vehicle IDs in the collection
            print("Looking for vehicle:", oid)
            print("All vehicle IDs:", [str(v["_id"]) for v in vehicle_collection.find({}, {"_id": 1})])

            # Validate location structure
            try:
                location = VehicleLocation(**location_data)
            except ValidationError:
                await websocket.send_text("Invalid location format")
                continue

            # Update vehicle's location in MongoDB
            result = vehicle_collection.update_one(
                {"_id": oid},
                {"$set": {"location": location.dict()}}
            )

            # Insert tracking log
            try:
                insert_gps_log(db, vehicle_id, location.latitude, location.longitude)
            except Exception as e:
                await websocket.send_text(f"Error updating tracking log: {e}")
                continue

            # Notify all users tracking this vehicle
            tracking_users = user_collection.find({"tracking_vehicle_id": vehicle_id})
            for user in tracking_users:
                user_location = user.get("location")
                if user_location:
                    try:
                        await check_and_notify(
                            str(user["_id"]),
                            type("UserLoc", (), user_location)(),
                            location
                        )
                    except Exception as e:
                        await websocket.send_text(f"Error in check_and_notify: {e}")

            # After updating the vehicle's location in MongoDB
            if result.matched_count == 1:
                # Broadcast to all subscribers of this vehicle
                subscribers = vehicle_subscribers.get(vehicle_id, [])
                for ws in subscribers:
                    try:
                        await ws.send_json({
                            "vehicle_id": vehicle_id,
                            "location": location.dict(),
                            "updated": result.modified_count == 1
                        })
                    except Exception as e:
                        print(f"Error sending to subscriber: {e}")

                # Optionally, also send a response to the sender
                await websocket.send_json({
                    "vehicle_id": vehicle_id,
                    "location": location.dict(),
                    "updated": result.modified_count == 1
                })
            else:
                await websocket.send_text(f"Vehicle {vehicle_id} not found")

    except WebSocketDisconnect:
        print("Vehicle client disconnected")

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

            # Update location
            result = user_collection.update_one(
                {"_id": oid},
                {"$set": {"location": location.dict()}}
            )

            if result.modified_count == 1:
                await websocket.send_text(f"Location updated for that user {user_id}")
            else:
                await websocket.send_text(f"No location has change made for user {user_id}")

    except WebSocketDisconnect:
        print("User client is disconnected")

#para track ang vehicles continuously no need to reload
@ws_router.websocket("/ws/track-vehicle")
async def track_vehicle_ws(websocket: WebSocket):
    await websocket.accept()
    vehicle_id = None
    try:
        data = await websocket.receive_json()
        vehicle_id = data.get("vehicle_id")
        if not vehicle_id:
            await websocket.send_text("vehicle_id required")
            await websocket.close()
            return

        if vehicle_id not in vehicle_subscribers:
            vehicle_subscribers[vehicle_id] = []
        vehicle_subscribers[vehicle_id].append(websocket)

        while True:
            await websocket.receive_text()  # Keep connection alive so that it receive always.
    except WebSocketDisconnect:
        if vehicle_id and vehicle_id in vehicle_subscribers:
            subs = vehicle_subscribers[vehicle_id]
            if websocket in subs:
                subs.remove(websocket)
                if not subs:
                    vehicle_subscribers.pop(vehicle_id)
        print("Vehicle tracking client disconnected from user")

#para count tanan vehicles continuously (bisan newly created) no need to reload
@ws_router.websocket("/ws/vehicle-counts")
async def vehicle_counts_ws(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            # Query DB for counts
            total = vehicle_collection.count_documents({})
            available = vehicle_collection.count_documents({"status": "available"})
            full = vehicle_collection.count_documents({"status": "full"})
            unavailable = vehicle_collection.count_documents({"status": "unavailable"})

            await websocket.send_json({
                "total": total,
                "available": available,
                "full": full,
                "unavailable": unavailable
            })

            # You can tune this interval or replace with a change-stream if Mongo supports it
            await asyncio.sleep(5)
    except WebSocketDisconnect:
        print("Vehicle count client disconnected")


#para makita tanan vehicles continuously (bisan newly created) no need to reload
@ws_router.websocket("/ws/vehicles/all")
async def all_vehicles_ws(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            vehicles = []
            for vehicle in vehicle_collection.find():
                vehicle_location = vehicle.get("location", {})
                if vehicle_location.get("latitude") and vehicle_location.get("longitude"):
                    vehicles.append({
                        "id": str(vehicle["_id"]),
                        "location": {
                            "latitude": vehicle_location["latitude"],
                            "longitude": vehicle_location["longitude"]
                        },
                        "available_seats": vehicle.get("available_seats", 0),
                        "status": vehicle.get("status", "unavailable"),
                        "route": vehicle.get("route", ""),
                        "driverName": vehicle.get("driverName", ""),
                        "plate": vehicle.get("plate", "")
                    })

            await websocket.send_json(vehicles)

            await asyncio.sleep(5)

    except WebSocketDisconnect:
        print("Vehicle list WebSocket client disconnected")