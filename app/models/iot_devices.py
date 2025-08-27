from typing import Dict, Any

def iot_devices(iot: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(iot["_id"]),                               # required
        "vehicle_id": str(iot["vehicle_id"]),                # required FK to vehicle
        "is_active": iot["is_active"],                 # required enum
        "last_update": iot.get("last_update"),               # optional datetime
        "createdAt": iot.get("createdAt")                    # optional datetime
    }