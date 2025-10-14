"""
Background worker that continuously checks proximity between users and vehicles
and sends notifications without requiring frontend location updates.
"""
import asyncio
import logging
from datetime import datetime
from bson import ObjectId
from app.database import user_collection, vehicle_collection
from app.utils.notifications import check_and_notify
from pytz import timezone

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ph_tz = timezone("Asia/Manila")

class ProximityChecker:
    def __init__(self, check_interval: int = 10):
        """
        Initialize proximity checker
        
        Args:
            check_interval: Seconds between proximity checks (default: 10)
        """
        self.check_interval = check_interval
        self.is_running = False
        
    async def start(self):
        """Start the background proximity checking loop"""
        self.is_running = True
        logger.info(f"🚀 Proximity checker started (interval: {self.check_interval}s)")
        
        while self.is_running:
            try:
                await self._check_all_proximities()
                await asyncio.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"❌ Error in proximity checker loop: {str(e)}")
                await asyncio.sleep(5)  # Wait before retrying
    
    def stop(self):
        """Stop the background checker"""
        self.is_running = False
        logger.info("🛑 Proximity checker stopped")
    
    async def _check_all_proximities(self):
        """Check proximity for all users with valid locations"""
        try:
            # Get all users with valid locations and FCM tokens
            users = list(user_collection.find({
                "location.latitude": {"$exists": True, "$ne": None},
                "location.longitude": {"$exists": True, "$ne": None},
                "fcm_token": {"$exists": True, "$ne": None},
                "fleet_id": {"$exists": True, "$ne": None},
                "notify": True
            }))
            
            if not users:
                logger.debug("No users with valid locations to check")
                return
            
            logger.info(f"🔍 Checking proximity for {len(users)} users")
            
            # Group users by fleet_id for efficient querying
            fleet_users = {}
            for user in users:
                fleet_id = str(user["fleet_id"])
                if fleet_id not in fleet_users:
                    fleet_users[fleet_id] = []
                fleet_users[fleet_id].append(user)
            
            # Process each fleet
            total_checks = 0
            total_notifications = 0
            
            for fleet_id, fleet_user_list in fleet_users.items():
                # Get available vehicles for this fleet
                vehicles = list(vehicle_collection.find({
                    "fleet_id": fleet_id,
                    "status": "available",
                    "location.latitude": {"$exists": True, "$ne": None},
                    "location.longitude": {"$exists": True, "$ne": None}
                }))
                
                if not vehicles:
                    continue
                
                logger.info(f"🚌 Fleet {fleet_id}: {len(fleet_user_list)} users, {len(vehicles)} vehicles")
                
                # Check each user against each vehicle
                for user in fleet_user_list:
                    user_id = str(user["_id"])
                    user_loc = user.get("location")
                    
                    if not user_loc:
                        continue
                    
                    for vehicle in vehicles:
                        vehicle_id = str(vehicle["_id"])
                        vehicle_loc = vehicle.get("location")
                        
                        if not vehicle_loc:
                            continue
                        
                        total_checks += 1
                        
                        # Create location objects for check_and_notify
                        user_location = type("UserLoc", (), {
                            "latitude": user_loc.get("latitude"),
                            "longitude": user_loc.get("longitude")
                        })()
                        
                        vehicle_location = type("VehicleLoc", (), {
                            "latitude": vehicle_loc.get("latitude"),
                            "longitude": vehicle_loc.get("longitude")
                        })()
                        
                        # Check proximity and notify if needed
                        notified = await check_and_notify(
                            user_id,
                            user_location,
                            vehicle_location,
                            vehicle_id,
                            fleet_id
                        )
                        
                        if notified:
                            total_notifications += 1
            
            logger.info(f"✅ Proximity check complete: {total_checks} checks, {total_notifications} notifications sent")
            
        except Exception as e:
            logger.error(f"❌ Error in _check_all_proximities: {str(e)}")

# Global instance
proximity_checker = ProximityChecker(check_interval=10)

async def start_proximity_checker():
    """Start the proximity checker as a background task"""
    await proximity_checker.start()

def stop_proximity_checker():
    """Stop the proximity checker"""
    proximity_checker.stop()