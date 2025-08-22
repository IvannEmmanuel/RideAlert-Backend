import os
import json
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, messaging

# Load .env
load_dotenv()

# Initialize Firebase
service_account_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_KEY")
service_account_info = json.loads(service_account_json)
cred = credentials.Certificate(service_account_info)

if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)

# Replace this with a valid FCM token from your database
fcm_token = "ddSqsOErRxi0tZyfD1eBbJ:APA91bFS_3o-NVLv9MXm-Ci1PzhEpqvBxoHd7LcT-4aZiz1LJ7Tu36O3p3v07ZN3Zu-IihGI-Q3pctv1Y__26eW0MHvozUulgq1l5WmwO5sVUgUS4we6dvY"

# Create and send message
message = messaging.Message(
    notification=messaging.Notification(
        title="🚨 Test Alert",
        body="This is a test notification from your backend!",
    ),
    token=fcm_token,
)

try:
    response = messaging.send(message)
    print("✅ Notification sent successfully!")
    print("Response:", response)
except Exception as e:
    print("❌ Failed to send notification:")
    print(str(e))
