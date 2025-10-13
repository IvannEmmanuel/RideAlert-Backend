from typing import Dict, Any

def fleets(admin: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(admin["_id"]),
        "company_name": admin["company_name"],
        "company_code": admin["company_code"], #String Unique
        "contact_info": admin.get("contact_info", []),
        "subscription_plan": admin["subscription_plan"],
        "is_active": admin["is_active"],
        "last_updated": admin.get("last_updated"),
        "approved_by": admin.get("approved_by"),
        "approved_in": admin.get("approved_in"),
        "created_at": admin.get("created_at"),
        "max_vehicles": admin["max_vehicles"],
        "role": admin["role"],
        "plan_price": admin.get("plan_price"),
        "pdf_files": admin.get("pdf_files", []) #added
    }