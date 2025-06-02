from datetime import datetime
from bson import ObjectId

def insert_gps_log(db, vehicle_id: str, latitude: float, longitude: float):
    db["tracking_logs"].update_one(
        {"vehicle_id": vehicle_id},
        {
            "$push": { #if you want to append on it just use $push / $set to replace the whole gps_data
                "gps_data": {
                    "latitude": latitude,
                    "longitude": longitude,
                    "timestamp": datetime.utcnow()
                }
            }
        },
        upsert=True  # Creates the document if it doesn't exist
    )