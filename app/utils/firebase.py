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
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Only initialize once
if not firebase_admin._apps:
    try:
        BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cred_path = os.path.join(BASE_DIR, "serviceAccountKey.json")
        
        if not os.path.exists(cred_path):
            logger.error(f"Service account key not found at: {cred_path}")
            raise FileNotFoundError(f"Service account key not found at: {cred_path}")
        
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
        logger.info("Firebase Admin SDK is initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize the Firebase: {str(e)}")
        raise

def send_push_notification(fcm_token, title, body, data=None):
    """
    Send push notification via FCM (Firebase Cloud Messaging)
    """
    try:
        # Validate input
        if not fcm_token or not title or not body:
            logger.error("Missing required parameters for the notification")
            return False
        
        # Create message
        message_data = {
            'notification': messaging.Notification(
                title=title,
                body=body,
            ),
            'token': fcm_token,
        }
        
        # Add custom data if provided
        if data:
            message_data['data'] = data
        
        message = messaging.Message(**message_data)
        
        # Send message
        response = messaging.send(message)
        logger.info(f'Successfully sent message: {response}')
        return True
        
    except messaging.UnregisteredError:
        logger.error(f'FCM token is unregistered: {fcm_token}')
        return False
    except messaging.SenderIdMismatchError:
        logger.error(f'FCM token sender ID mismatch: {fcm_token}')