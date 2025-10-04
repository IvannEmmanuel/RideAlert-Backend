import sys
import os
import asyncio
from pathlib import Path

# 🔧 Fix imports: Add project root to path
project_root = Path(__file__).parent.parent  # app/ -> root
sys.path.insert(0, str(project_root))

# Now import
try:
    from app.database import user_collection, vehicle_collection, notification_logs_collection
    from app.utils.notifications import check_and_notify
    from app.utils.haversine import haversine_code
    from bson import ObjectId
    import logging
except ImportError as e:
    print(f"❌ Import failed: {e}")
    print("💡 Ensure you're in project root and __init__.py exists in app/")
    sys.exit(1)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_proximity():
    # Test data - REPLACE WITH YOUR REAL VALUES (from MongoDB Compass/shell)
    user_id = "68b4341b7b9024fa486f0697"  # Your fleet_id from logs; use as user_id for test
    vehicle_id = "68b3e4d19f1c8d7ccdb6c991"  # e.g., find one from db.vehicle_collection.findOne()
    
    # Fetch real user from DB for accuracy
    try:
        user_doc = user_collection.find_one({"_id": ObjectId(user_id)})
        if not user_doc:
            logger.error(f"❌ No user found with ID {user_id}")
            return
        logger.info(f"👤 Found user: {user_doc.get('first_name', 'Unknown')}, FCM: {user_doc.get('fcm_token', 'Missing')[:20]}...")
        
        # Use real user location if available, else mock close to a vehicle
        user_location = user_doc.get("location", {"latitude": 10.315698, "longitude": 123.885437})  # Cebu default
    except Exception as e:
        logger.error(f"❌ DB user fetch failed: {e}")
        return
    
    # Fetch a real available vehicle from same fleet
    try:
        fleet_id = user_doc.get("fleet_id", ObjectId(user_id))  # Fallback to user_id if no fleet
        vehicle_doc = vehicle_collection.find_one({
            "fleet_id": fleet_id,
            "status": "available",
            "location": {"$exists": True}
        })
        if not vehicle_doc:
            logger.warning("⚠️ No available vehicle found—creating mock")
            vehicle_doc = {
                "_id": ObjectId(vehicle_id or "68b3e4d19f1c8d7ccdb6c992"),
                "location": {"latitude": 10.3157, "longitude": 123.8854}  # ~50m from user default
            }
        else:
            vehicle_id = str(vehicle_doc["_id"])
        
        vehicle_location = vehicle_doc.get("location")
        logger.info(f"🚍 Found vehicle {vehicle_id}: {vehicle_location}")
    except Exception as e:
        logger.error(f"❌ DB vehicle fetch failed: {e}")
        # Fallback mock
        vehicle_location = {"latitude": 10.3157, "longitude": 123.8854}
    
    # Mock objects for the function (dicts with attr access)
    user_loc_obj = type("UserLoc", (), user_location)()
    vehicle_loc_obj = type("VehicleLoc", (), vehicle_location)()
    
    logger.info(f"🧪 Testing proximity for user {user_id}, vehicle {vehicle_id}")
    
    # Direct distance calc for sanity
    dist = haversine_code(
        user_loc_obj.latitude, user_loc_obj.longitude,
        vehicle_loc_obj.latitude, vehicle_loc_obj.longitude
    )
    logger.info(f"📏 Test distance: {dist:.0f}m")
    
    if dist > 500:
        logger.warning("💡 Dist too far—adjust vehicle coords in DB to <500m from user")
        return
    
    # Call the notify func
    success = await check_and_notify(user_id, user_loc_obj, vehicle_loc_obj, vehicle_id)
    
    if success:
        logger.info("🎉 Notification fired! Check your phone for FCM push.")
    else:
        logger.error("😞 No notification—check recent logs in notification_logs_collection")

# Run it
if __name__ == "__main__":
    asyncio.run(test_proximity())