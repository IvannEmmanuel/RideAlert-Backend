from typing import Dict, Any

def iot_devices(iot: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(iot["_id"]),                               # required
        "vehicle_id": str(iot["vehicle_id"]),                # 
        "is_active": iot["is_active"],                 # required enum
        "fleet_id": str(iot["fleet_id"]),
        "last_update": iot.get("last_update"),               # optional datetime
        "device_name": iot.get("device_name"),               #
        "createdAt": iot.get("createdAt")                    # optional datetime
    }