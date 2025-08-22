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
fcm_token = "etNPUYgHQXiq6iFUrGb2RE:APA91bGTW7TGPN-3NywgBdSw_K0feZAPGG-SWUv2NClQJvvGjo0KBUnga_8mhMSN8de0zoVbP3KvlpqNoqBDGV2whox8syvGZp_Lx2Yu54iHPme4icL_W44"

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
