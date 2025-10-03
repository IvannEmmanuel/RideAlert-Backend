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
from bson import ObjectId
from app.database import user_collection, notification_logs_collection
from app.utils.firebase import send_push_notification
import asyncio
from datetime import datetime, timedelta
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def check_and_notify(user_id, user_location, vehicle_location, vehicle_id=None):
    """
    Check distance between user and vehicle, send tiered notifications:
    - Once at <=500m
    - Once more at <=100m
    - Skip if already notified at that tier for this user-vehicle
    - Reset if distance >500m
    """
    try:
        # Calculate distance using haversine formula
        distance = haversine_code(
            user_location.latitude,
            user_location.longitude,
            vehicle_location.latitude,
            vehicle_location.longitude
        )
        
        logger.info(f"Distance calculated: {distance}m for user {user_id} and vehicle {vehicle_id}")
        
        if distance > 500:
            # Reset notifications if far away (allow re-entry)
            notification_logs_collection.update_one(
                {"user_id": user_id, "vehicle_id": vehicle_id},
                {"$set": {"notified_500m": False, "notified_100m": False}}
            )
            logger.info(f"Reset notifications for user {user_id} and vehicle {vehicle_id} (distance >500m)")
            return False
        
        # Fetch or create notification state for this user-vehicle
        state_query = {"user_id": user_id, "vehicle_id": vehicle_id}
        state = notification_logs_collection.find_one(state_query)
        if not state:
            # First time: Initialize
            notification_logs_collection.insert_one({
                "user_id": user_id,
                "vehicle_id": vehicle_id,
                "notified_500m": False,
                "notified_100m": False,
                "last_distance": distance,
                "timestamp": datetime.utcnow(),
                "notification_type": "proximity_state"
            })
            state = {"notified_500m": False, "notified_100m": False}
        
        notified = False
        
        # Tier 1: 500m notification
        if distance <= 500 and not state.get("notified_500m", False):
            logger.info(f"Triggering 500m notification for user {user_id}")
            success = await _send_tiered_notification(
                user_id, f"PUV Nearby! ({int(distance)}m)", "A PUV has entered 500m range."
            )
            if success:
                notification_logs_collection.update_one(
                    state_query,
                    {"$set": {"notified_500m": True, "last_distance": distance, "timestamp": datetime.utcnow()}}
                )
                notified = True
        
        # Tier 2: 100m notification
        elif distance <= 100 and not state.get("notified_100m", False):
            logger.info(f"Triggering 100m notification for user {user_id}")
            success = await _send_tiered_notification(
                user_id, f"PUV Very Close! ({int(distance)}m)", "A PUV is now within 100m—time to board!"
            )
            if success:
                notification_logs_collection.update_one(
                    state_query,
                    {"$set": {"notified_100m": True, "last_distance": distance, "timestamp": datetime.utcnow()}}
                )
                notified = True
        else:
            logger.info(f"No new tier for user {user_id} and vehicle {vehicle_id} (distance: {distance}m)")
        
        return notified
        
    except Exception as e:
        logger.error(f"Error in check_and_notify: {str(e)}")
        return False
    
async def _send_tiered_notification(user_id, title, body):
    """
    Helper to send FCM and log
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
        
        # Send FCM
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: send_push_notification(fcm_token, title, body)
        )
        
        if result:  # Assuming send_push_notification returns True on success
            logger.info(f"Tiered notification sent to user {user_id}: {title}")
            return True
        else:
            logger.error(f"Failed to send tiered notification to user {user_id}")
            return False
            
    except Exception as e:
        logger.error(f"Error sending tiered notification: {str(e)}")
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
                "timestamp": datetime.utcnow(),
                "notification_type": "proximity_manual"
            })
            logger.info(f"Manual proximity notification sent to user {user_id}")
            return True
        
        return False
        
    except Exception as e:
        logger.error(f"Error in send_proximity_notification: {str(e)}")
        return False