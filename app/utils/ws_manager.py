from typing import List, Dict
from fastapi import WebSocket, WebSocketDisconnect
from datetime import datetime

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
        disconnected = []
        for connection in self.active_connections[:]:  # Create a copy to iterate
            try:
                await connection.send_json(message)
            except Exception as e:
                print(f"❌ DEBUG: Connection error during broadcast: {str(e)}")
                disconnected.append(connection)
        
        # Clean up disconnected clients
        for connection in disconnected:
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
            disconnected = []
            for connection in self.active_connections[fleet_id][:]:  # Create a copy
                try:
                    await connection.send_json(message)
                except Exception as e:
                    print(f"❌ DEBUG: Connection error during broadcast: {str(e)}")
                    disconnected.append(connection)
            
            # Clean up disconnected clients
            for connection in disconnected:
                self.disconnect(connection, fleet_id)

class RoleBasedConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {
            "superadmin": [],
            "admin": [],
            "all": []
        }

    async def connect(self, websocket: WebSocket, user_role: str = "all"):
        if user_role in self.active_connections:
            self.active_connections[user_role].append(websocket)
        self.active_connections["all"].append(websocket)

    def disconnect(self, websocket: WebSocket):
        """Remove websocket from all role lists"""
        for role in self.active_connections:
            if websocket in self.active_connections[role]:
                self.active_connections[role].remove(websocket)

    async def broadcast_to_role(self, message: dict, role: str):
        disconnected = []
        print(f"📢 DEBUG: Broadcasting to {role} role. Connected clients: {len(self.active_connections.get(role, []))}")
        
        for websocket in self.active_connections.get(role, [])[:]:  # Create a copy
            try:
                await websocket.send_json(message)
                print(f"✅ DEBUG: Successfully sent to {role} client")
            except Exception as e:
                print(f"❌ DEBUG: Failed to send to {role} client: {str(e)}")
                disconnected.append(websocket)
        
        # Clean up disconnected clients
        for websocket in disconnected:
            self.disconnect(websocket)

    async def broadcast(self, message: dict):
        disconnected = []
        # Iterate through all roles and their connections
        for role in self.active_connections:
            for websocket in self.active_connections[role][:]:  # Create a copy
                try:
                    await websocket.send_json(message)
                except Exception as e:
                    print(f"❌ DEBUG: Connection error in {role}: {str(e)}")
                    disconnected.append(websocket)
        
        # Clean up disconnected clients (only once per websocket)
        seen = set()
        for websocket in disconnected:
            if id(websocket) not in seen:
                self.disconnect(websocket)
                seen.add(id(websocket))

class EtaManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, vehicle_id: str):
        await websocket.accept()
        if vehicle_id not in self.active_connections:
            self.active_connections[vehicle_id] = []
        self.active_connections[vehicle_id].append(websocket)

    def disconnect(self, websocket: WebSocket, vehicle_id: str):
        if vehicle_id in self.active_connections:
            if websocket in self.active_connections[vehicle_id]:
                self.active_connections[vehicle_id].remove(websocket)
            if not self.active_connections[vehicle_id]:
                del self.active_connections[vehicle_id]

    async def broadcast_eta(self, vehicle_id: str, eta_data: dict):
        if vehicle_id in self.active_connections:
            disconnected = []
            for websocket in self.active_connections[vehicle_id][:]:  # Create a copy
                try:
                    await websocket.send_json({
                        "type": "eta_update",
                        "vehicle_id": vehicle_id,
                        "timestamp": datetime.utcnow().isoformat(),
                        "data": eta_data
                    })
                except (WebSocketDisconnect, RuntimeError) as e:
                    print(f"❌ DEBUG: ETA connection error: {str(e)}")
                    disconnected.append(websocket)
            
            # Remove disconnected clients
            for websocket in disconnected:
                self.disconnect(websocket, vehicle_id)

# Separate managers for different endpoints
fleet_count_manager = ConnectionManager()  # For /fleets/ws/count-fleets
fleet_all_manager = ConnectionManager()    # For /fleets/ws/all
user_count_manager = ConnectionManager()   # For /users/ws/count-users
vehicle_count_manager = ConnectionManager() # For /vehicles/ws/count-vehicles
vehicle_all_manager = FleetConnectionManager() # For /vehicles/ws/vehicles/all/{fleet_id}
fleet_details_manager = FleetConnectionManager() # For /fleets/{fleet_id}/ws
iot_device_all_manager = ConnectionManager() # For /iot_devices/ws/all
iot_device_fleet_manager = FleetConnectionManager() # For /iot_devices/ws/fleet/{fleet_id} #NEWLY ADDED
stats_count_manager = ConnectionManager()  # For /stats/count WebSocket
stats_verified_manager = ConnectionManager()  # For /stats/verified WebSocket
routes_all_manager = ConnectionManager()  # For /declared_routes/ws/routes (superadmin real-time updates)
notification_manager = RoleBasedConnectionManager()  # For role-based notifications
eta_manager = EtaManager() # For /ws/vehicles/eta/{vehicle_id}
