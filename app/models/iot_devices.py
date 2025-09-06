from typing import Dict, Any

def iot_devices(iot: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(iot["_id"]),                               # required
        "vehicle_id": str(iot["vehicle_id"]),                # required
        "company_name": iot.get("company_name"),         # optional string
        "is_active": iot["is_active"],                 # required enum
        "device_model": iot.get("device_model"),           # optional string
        "last_update": iot.get("last_update"),               # optional datetime
        "device_name": iot.get("device_name"),               # optional string
        "notes": iot.get("notes"),                       # optional string
        "createdAt": iot.get("createdAt")                    # optional datetime
    }