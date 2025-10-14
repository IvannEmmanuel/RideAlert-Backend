# from app.utils.haversine import haversine_code
# from bson import ObjectId
# from app.database import user_collection
# from app.utils.firebase import send_push_notification
# import asyncio

# async def check_and_notify(user_id, user_location, vehicle_location):
#     # haversine_code should return distance in meters
#     distance = haversine_code(
#         user_location.latitude,
#         user_location.longitude,
#         vehicle_location.latitude,
#         vehicle_location.longitude
#     )
#     if distance <= 500:  # 500 meters
#         # Fetch user's FCM token
#         user_data = user_collection.find_one({"_id": ObjectId(user_id)})
#         fcm_token = user_data.get("fcm_token")
#         if fcm_token:
#             await send_fcm_notification(fcm_token, "PUV Nearby", "A PUV is nearby!")

# async def send_fcm_notification(fcm_token, title, body):
#     # Run the synchronous send_push_notification in a thread for async compatibility
#     loop = asyncio.get_event_loop()
#     await loop.run_in_executor(
#         None,
#         lambda: send_push_notification(fcm_token, title, body)
#     )

from app.utils.haversine import haversine_code
from bson import ObjectId, errors
from app.database import user_collection, notification_logs_collection
from app.utils.firebase import send_push_notification
import asyncio
from datetime import datetime, timedelta
import logging
from pytz import timezone

ph_tz = timezone("Asia/Manila")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def check_and_notify(user_id, user_location, vehicle_location, vehicle_id=None, fleet_id=None):
    """
    Check distance between user and vehicle and send tiered notifications:
    - <=500m: first notification (ONCE)
    - <=100m: second notification (ONCE)
    - Reset both if distance >500m
    """
    try:
        # Calculate distance
        distance = haversine_code(
            user_location.latitude,
            user_location.longitude,
            vehicle_location.latitude,
            vehicle_location.longitude
        )
        logger.info(f"Distance for user {user_id} vehicle {vehicle_id}: {distance:.1f}m")

        # Query for existing log with ALL matching fields
        query = {
            "user_id": ObjectId(user_id),
            "vehicle_id": vehicle_id,
            "fleet_id": ObjectId(fleet_id)
        }
        state = notification_logs_collection.find_one(query)

        if distance > 500:
            # Reset notifications if user moves away
            if state:
                notification_logs_collection.update_one(
                    query,
                    {
                        "$set": {
                            "notified_500m": False,
                            "notified_100m": False,
                            "last_distance": distance,
                            "timestamp": datetime.now(ph_tz)
                        }
                    }
                )
                logger.info(f"🔄 Reset notifications for user {user_id} vehicle {vehicle_id} (distance: {distance:.1f}m)")
            return False

        # Initialize state if first time
        if not state:
            notification_logs_collection.insert_one({
                "user_id": ObjectId(user_id),
                "vehicle_id": vehicle_id,
                "fleet_id": ObjectId(fleet_id),
                "notified_500m": False,
                "notified_100m": False,
                "last_distance": distance,
                "timestamp": datetime.now(ph_tz),
                "notification_type": "proximity_state"
            })
            state = {"notified_500m": False, "notified_100m": False}
            logger.info(f"📝 Created new notification state for user {user_id} vehicle {vehicle_id}")

        notified = False
        updates = {}

        # Tier 1: 100m notification (ONLY if not already sent)
        if distance <= 100 and not state.get("notified_100m", False):
            logger.info(f"🔔 Attempting 100m notification for user {user_id}")
            if await _send_tiered_notification(
                user_id,
                f"PUV Very Close! ({int(distance)}m)",
                "A PUV is now within 100m—time to board!",
                vehicle_id
            ):
                updates["notified_100m"] = True
                updates["notified_500m"] = True  # ← KEY FIX: Mark 500m as sent too!
                notified = True
                logger.info(f"✅ Sent 100m notification to user {user_id}")

        # Tier 2: 500m notification (ONLY if not already sent)
        elif distance <= 500 and not state.get("notified_500m", False):
            logger.info(f"🔔 Attempting 500m notification for user {user_id}")
            if await _send_tiered_notification(
                user_id,
                f"PUV Nearby! ({int(distance)}m)",
                "A PUV has entered 500m range.",
                vehicle_id
            ):
                updates["notified_500m"] = True
                notified = True
                logger.info(f"✅ Sent 500m notification to user {user_id}")

        # Apply updates to MongoDB
        if updates:
            updates.update({
                "last_distance": distance,
                "timestamp": datetime.now(ph_tz)
            })
            notification_logs_collection.update_one(query, {"$set": updates})
            logger.info(f"💾 Updated notification state: {updates}")

        return notified

    except Exception as e:
        logger.error(f"❌ check_and_notify error for user {user_id}: {str(e)}")
        return False

async def _send_tiered_notification(user_id, title, body, vehicle_id=None):
    """
    Send FCM notification AND insert a log into notification_logs_collection
    """
    try:
        user_data = user_collection.find_one({"_id": ObjectId(user_id)})
        if not user_data or not user_data.get("fcm_token"):
            logger.error(f"❌ No FCM token for user {user_id}")
            return False

        fcm_token = user_data["fcm_token"]

        # Send FCM
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: send_push_notification(fcm_token, title, body)
        )

        if result:
            # Insert log for frontend
            notification_logs_collection.insert_one({
                "user_id": ObjectId(user_id),
                "fleet_id": ObjectId(user_data.get("fleet_id")),
                "vehicle_id": vehicle_id,
                "message": body,
                "createdAt": datetime.now(ph_tz),
                "notification_type": "proximity_alert"
            })
            logger.info(f"✅ Notification sent & logged: {title}")
        return result

    except Exception as e:
        logger.error(f"❌ Error sending notification for user {user_id}: {str(e)}")
        return False

async def send_fcm_notification(fcm_token, title, body):
    """
    Send FCM notification asynchronously
    """
    try:
        # Run the synchronous send_push_notification in a thread pool
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: send_push_notification(fcm_token, title, body)
        )
        return True
    except Exception as e:
        logger.error(f"Error sending FCM notification: {str(e)}")
        return False

async def send_proximity_notification(user_id, vehicle_id, distance):
    """
    Send proximity notification for specific user and vehicle
    """
    try:
        user_data = user_collection.find_one({"_id": ObjectId(user_id)})
        if not user_data:
            logger.error(f"User {user_id} not found")
            return False
            
        fcm_token = user_data.get("fcm_token")
        if not fcm_token:
            logger.error(f"No FCM token found for user {user_id}")
            return False
        
        # Check if notification was sent recently
        recent_notification = notification_logs_collection.find_one({
            "user_id": user_id,
            "vehicle_id": vehicle_id,
            "timestamp": {"$gte": datetime.utcnow() - timedelta(minutes=5)}
        })
        
        if recent_notification:
            logger.info(f"Recent notification exists for user {user_id}, skipping")
            return False
        
        success = await send_fcm_notification(
            fcm_token,
            "PUV Nearby!",
            f"A PUV is {distance}m away from you!"
        )
        
        if success:
            # Log the notification
            notification_logs_collection.insert_one({
                "user_id": user_id,
                "vehicle_id": vehicle_id,
                "distance": distance,
                "timestamp": datetime.now(ph_tz),
                "notification_type": "proximity_manual"
            })
            logger.info(f"Manual proximity notification sent to user {user_id}")
            return True
        
        return False
        
    except Exception as e:
        logger.error(f"Error in send_proximity_notification: {str(e)}")
        return False