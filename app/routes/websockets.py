from fastapi import WebSocket, WebSocketDisconnect, APIRouter
from app.database import vehicle_collection
from app.utils.tracking_logs import insert_gps_log
from app.database import db
from bson import ObjectId
from app.schemas.vehicle import Location
from pydantic import ValidationError
from app.schemas.user import Location as UserLocation
from app.database import user_collection

ws_router = APIRouter(tags=["WebSocket"])

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

            # Validate location structure
            try:
                location = Location(**location_data)
            except ValidationError:
                await websocket.send_text("Invalid location format")
                continue

            # Update vehicle's location in MongoDB
            result = vehicle_collection.update_one(
                {"_id": oid},
                {"$set": {"location": location.dict()}}
            )

            # update tracking_logs
            try:
                insert_gps_log(db, vehicle_id, location.latitude, location.longitude)
            except Exception as e:
                await websocket.send_text(f"Error updating tracking log: {e}")
                continue

            if result.modified_count == 1:
                await websocket.send_text(f"Location updated for vehicle {vehicle_id}")
            else:
                await websocket.send_text(f"Vehicle {vehicle_id} not found")

    except WebSocketDisconnect:
        print("Client disconnected")

@ws_router.websocket("/ws/user-location")
async def update_user_location(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()

            user_id = data.get("user_id")
            location_data = data.get("location")

            # Validate ObjectId
            try:
                oid = ObjectId(user_id)
            except Exception:
                await websocket.send_text("Invalid user_id format")
                continue

            # Validate location structure
            try:
                location = UserLocation(**location_data)
            except ValidationError:
                await websocket.send_text("Invalid location format")
                continue

            # Update user's location in MongoDB
            result = user_collection.update_one(
                {"_id": oid},
                {"$set": {"location": location.dict()}}
            )

            if result.modified_count == 1:
                await websocket.send_text(f"Location updated for user {user_id}")
            else:
                await websocket.send_text(f"User {user_id} not found")

    except WebSocketDisconnect:
        print("User client disconnected")