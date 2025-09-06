from typing import List, Dict
from fastapi import WebSocket

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                self.disconnect(connection)

class FleetConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, fleet_id: str):
        await websocket.accept()
        if fleet_id not in self.active_connections:
            self.active_connections[fleet_id] = []
        self.active_connections[fleet_id].append(websocket)

    def disconnect(self, websocket: WebSocket, fleet_id: str):
        if fleet_id in self.active_connections and websocket in self.active_connections[fleet_id]:
            self.active_connections[fleet_id].remove(websocket)
            if not self.active_connections[fleet_id]:
                del self.active_connections[fleet_id]

    async def broadcast(self, message: dict, fleet_id: str):
        if fleet_id in self.active_connections:
            for connection in self.active_connections[fleet_id][:]:
                try:
                    await connection.send_json(message)
                except Exception:
                    self.disconnect(connection, fleet_id)

# Separate managers for different endpoints
fleet_count_manager = ConnectionManager()  # For /fleets/ws/count-fleets
fleet_all_manager = ConnectionManager()    # For /fleets/ws/all
user_count_manager = ConnectionManager()   # For /users/ws/count-users
vehicle_count_manager = ConnectionManager() # For /vehicles/ws/count-vehicles
vehicle_all_manager = FleetConnectionManager() # For /vehicles/ws/vehicles/all/{fleet_id}
fleet_details_manager = FleetConnectionManager() # For /fleets/{fleet_id}/ws
iot_device_all_manager = ConnectionManager() # For /iot_devices/ws/all