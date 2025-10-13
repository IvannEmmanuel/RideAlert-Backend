from pymongo import MongoClient
from dotenv import load_dotenv
import os

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")

client = MongoClient(MONGO_URI)

try:
    client.admin.command("ping")
    # Reduced logging for Railway deployment
    print("✅ MongoDB connected")
except Exception as e:
    print("❌ MongoDB connection error:", e)

db = client["ridealertDB"]
user_collection = db["users"]
vehicle_collection = db["vehicles"]
tracking_logs_collection = db["tracking_logs"]
notification_logs_collection = db["notification_logs"]
get_iot_devices_collection = db["iot_devices"]
get_fleets_collection = db["fleets"]
get_declared_routes_collection = db["declared_routes"]
notifications_collection = db["notifications_web_logs"]
