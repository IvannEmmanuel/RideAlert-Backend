# import firebase_admin
# from firebase_admin import credentials, messaging
# import os

# # Only initialize once
# if not firebase_admin._apps:
#     BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
#     cred_path = os.path.join(BASE_DIR, "serviceAccountKey.json")
#     cred = credentials.Certificate(cred_path)
#     firebase_admin.initialize_app(cred)

# def send_push_notification(fcm_token, title, body):
#     message = messaging.Message(
#         notification=messaging.Notification(
#             title=title,
#             body=body,
#         ),
#         token=fcm_token,
#     )
#     response = messaging.send(message)
#     print('Successfully sent message:', response)

import firebase_admin
from firebase_admin import credentials, messaging
import os
import json
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Set up logging with reduced verbosity for Railway
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# Only initialize once
if not firebase_admin._apps:
    try:
        # Try to get service account from environment variable first (Railway deployment)
        service_account_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_KEY")

        if service_account_json:
            # Parse JSON from environment variable
            service_account_info = json.loads(service_account_json)
            cred = credentials.Certificate(service_account_info)
            logger.info("Firebase initialized with environment variable")
        else:
            # Fallback to local file (development)
            BASE_DIR = os.path.dirname(
                os.path.dirname(os.path.abspath(__file__)))
            cred_path = os.path.join(BASE_DIR, "serviceAccountKey.json")

            if not os.path.exists(cred_path):
                logger.error(f"Service account key not found at: {cred_path}")
                raise FileNotFoundError(
                    f"Service account key is not found at: {cred_path}")

            cred = credentials.Certificate(cred_path)
            logger.info("Firebase initialized with local service account file")

        firebase_admin.initialize_app(cred)
        logger.info("Firebase Admin SDK is initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize the Firebase Admin: {str(e)}")
        raise


# def send_push_notification(fcm_token, title, body, data=None):
#     """
#     Send the push notification via FCM (Firebase Cloud Messaging)
#     """
#     try:
#         # Validate input
#         if not fcm_token or not title or not body:
#             logger.error("Missing required parameters for notification")
#             return False

#         # Create message
#         message_data = {
#             'notification': messaging.Notification(
#                 title=title,
#                 body=body,
#             ),
#             'token': fcm_token,
#         }

#         # Add custom data if provided
#         if data:
#             message_data['data'] = data

#         message = messaging.Message(**message_data)

#         # Send message
#         response = messaging.send(message)
#         logger.info(f'Successfully sent message: {response}')
#         return True

#     except messaging.UnregisteredError:
#         logger.error(f'FCM token is unregistered: {fcm_token}')
#         return False
#     except messaging.SenderIdMismatchError:
#         logger.error(f'FCM token sender ID mismatch: {fcm_token}')

def send_push_notification(fcm_token, title, body, data=None):
    """
    Send the push notification via FCM (Firebase Cloud Messaging)
    with high priority and channel for heads-up display.
    """
    try:
        if not fcm_token or not title or not body:
            logger.error("Missing required parameters for notification")
            return False

        android_notification = messaging.AndroidNotification(
            title=title,
            body=body,
            sound="default",
            channel_id="high_priority_channel",  # Must match frontend
        )

        android_config = messaging.AndroidConfig(
            priority="high",
            notification=android_notification,
        )

        message = messaging.Message(
            token=fcm_token,
            android=android_config,
            data=data or {},  # Optional custom payload
        )

        response = messaging.send(message)
        logger.info(f"✅ Successfully sent message: {response}")
        return True

    except messaging.UnregisteredError:
        logger.error(f"❌ FCM token is unregistered: {fcm_token}")
        return False
    except messaging.SenderIdMismatchError:
        logger.error(f"❌ FCM token sender ID mismatch: {fcm_token}")
        return False
    except Exception as e:
        logger.error(f"❌ Failed to send push notification: {str(e)}")
        return False