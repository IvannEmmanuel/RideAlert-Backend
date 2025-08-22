import os
import json
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# Get the Firebase key from .env
key = os.getenv("FIREBASE_SERVICE_ACCOUNT_KEY")

# Try to parse it
try:
    parsed = json.loads(key)
    print("✅ JSON parsed successfully!")
    print("Project ID:", parsed.get("project_id"))
    print("Client Email:", parsed.get("client_email"))
except Exception as e:
    print("❌ JSON parsing failed:")
    print(str(e))
