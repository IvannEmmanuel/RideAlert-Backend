from fastapi import WebSocket, WebSocketDisconnect, APIRouter
from bson import ObjectId
from pydantic import ValidationError
from app.database import vehicle_collection, user_collection, db
from app.schemas.vehicle import Location as VehicleLocation
from app.schemas.user import Location as UserLocation
from app.utils.tracking_logs import insert_gps_log
from app.utils.notifications import check_and_notify
from typing import Dict, List

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
                await websocket.send_text("Invalid user_id format")
                continue

            # Validate location schema
            try:
                location = UserLocation(**location_data)
            except ValidationError:
                await websocket.send_text("Invalid location format")
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
                await websocket.send_text(f"Location updated for user {user_id}")
            else:
                await websocket.send_text(f"No location changes made for user {user_id}")

    except WebSocketDisconnect:
        print("User client disconnected")

@ws_router.websocket("/ws/track-vehicle")
async def track_vehicle_ws(websocket: WebSocket):
    await websocket.accept()
    try:
        data = await websocket.receive_json()
        vehicle_id = data.get("vehicle_id")
        if not vehicle_id:
            await websocket.send_text("vehicle_id required")
            await websocket.close()
            return

        # Register this websocket as a subscriber for this vehicle
        if vehicle_id not in vehicle_subscribers:
            vehicle_subscribers[vehicle_id] = []
        vehicle_subscribers[vehicle_id].append(websocket)

        while True:
            await websocket.receive_text()  # Keep connection alive
    except WebSocketDisconnect:
        # Remove from subscribers on disconnect
        for subs in vehicle_subscribers.values():
            if websocket in subs:
                subs.remove(websocket)