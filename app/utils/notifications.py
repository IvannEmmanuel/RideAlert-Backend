from app.utils.haversine import haversine_code
from bson import ObjectId
from app.database import user_collection
from app.utils.firebase import send_push_notification
import asyncio

async def check_and_notify(user_id, user_location, vehicle_location):
    # haversine_code should return distance in meters
    distance = haversine_code(
        user_location.latitude,
        user_location.longitude,
        vehicle_location.latitude,
        vehicle_location.longitude
    )
    if distance <= 500:  # 500 meters
        # Fetch user's FCM token
        user_data = user_collection.find_one({"_id": ObjectId(user_id)})
        fcm_token = user_data.get("fcm_token")
        if fcm_token:
            await send_fcm_notification(fcm_token, "PUV Nearby", "A PUV is nearby!")

async def send_fcm_notification(fcm_token, title, body):
    # Run the synchronous send_push_notification in a thread for async compatibility
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        lambda: send_push_notification(fcm_token, title, body)
    )