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
    Check distance between user and vehicle, send notification if within range of the user
    """
    try:
        # Calculate distance using haversine formula
        distance = haversine_code(
            user_location.latitude,
            user_location.longitude,
            vehicle_location.latitude,
            vehicle_location.longitude
        )
        
        logger.info(f"Distance calculated: {distance}m for user {user_id}")
        
        if distance <= 500:  # 500 meters threshold
            # Check if notification was sent recently (avoid spam)
            recent_notification = notification_logs_collection.find_one({
                "user_id": user_id,
                "vehicle_id": vehicle_id,
                "timestamp": {"$gte": datetime.utcnow() - timedelta(minutes=5)}
            })
            
            if recent_notification:
                logger.info(f"Recent notification found for user {user_id}, skipping")
                return False
            
            # Fetch user's FCM token
            user_data = user_collection.find_one({"_id": ObjectId(user_id)})
            if not user_data:
                logger.error(f"User {user_id} not found")
                return False
                
            fcm_token = user_data.get("fcm_token")
            if not fcm_token:
                logger.error(f"No FCM token found for user {user_id}")
                return False
            
            # Send FCM notification
            success = await send_fcm_notification(
                fcm_token, 
                "PUV Nearby!", 
                f"A PUV is {int(distance)}m away from you!"
            )
            
            if success:
                # Log the notification
                notification_logs_collection.insert_one({
                    "user_id": user_id,
                    "vehicle_id": vehicle_id,
                    "distance": distance,
                    "timestamp": datetime.utcnow(),
                    "notification_type": "proximity"
                })
                logger.info(f"Notification sent successfully to user {user_id}")
                return True
            else:
                logger.error(f"Failed to send notification to user {user_id}")
                return False
                
    except Exception as e:
        logger.error(f"Error in check_and_notify: {str(e)}")
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