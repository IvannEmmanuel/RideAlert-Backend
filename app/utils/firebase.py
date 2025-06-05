import firebase_admin
from firebase_admin import credentials, messaging
import os

# Only initialize once
if not firebase_admin._apps:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cred_path = os.path.join(BASE_DIR, "serviceAccountKey.json")
    cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred)

def send_push_notification(fcm_token, title, body):
    message = messaging.Message(
        notification=messaging.Notification(
            title=title,
            body=body,
        ),
        token=fcm_token,
    )
    response = messaging.send(message)
    print('Successfully sent message:', response)