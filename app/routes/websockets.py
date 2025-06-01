from fastapi import WebSocket, WebSocketDisconnect, APIRouter
from app.database import vehicle_collection
from bson import ObjectId
from app.schemas.vehicle import Location
from pydantic import ValidationError

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

            # Update location in MongoDB
            result = vehicle_collection.update_one(
                {"_id": oid},
                {"$set": {"location": location.dict()}}
            )

            if result.modified_count == 1:
                await websocket.send_text(f"Location updated for vehicle {vehicle_id}")
            else:
                await websocket.send_text(f"Vehicle {vehicle_id} not found")

    except WebSocketDisconnect:
        print("Client disconnected")
