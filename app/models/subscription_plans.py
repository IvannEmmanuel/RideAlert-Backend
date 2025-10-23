from typing import Dict, Any

def subscription_plan_entity(plan: Dict[str, Any]) -> Dict[str, Any]:
    """Convert MongoDB subscription plan document to dictionary"""
    return {
        "id": str(plan["_id"]),
        "plan_name": plan["plan_name"],
        "plan_code": plan["plan_code"],
        "description": plan.get("description"),
        "price": plan["price"],
        "max_vehicles": plan["max_vehicles"],
        "features": plan.get("features", []),
        "is_active": plan.get("is_active", True),
        "created_at": plan.get("created_at"),
        "last_updated": plan.get("last_updated")
    }