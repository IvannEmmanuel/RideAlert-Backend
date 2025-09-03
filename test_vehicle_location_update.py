"""
Test script to verify that /predict endpoint updates vehicle location in the database

This script:
1. Creates a test vehicle in the database
2. Makes a prediction request
3. Verifies that the vehicle location was updated with corrected coordinates
"""

import requests
import time
import json
from pymongo import MongoClient
from bson import ObjectId


class VehicleLocationUpdateTest:
    def __init__(self, base_url="http://localhost:8000", mongo_url="mongodb://localhost:27017"):
        self.base_url = base_url
        self.client = MongoClient(mongo_url)
        self.db = self.client.ridealert  # Adjust database name if needed

    def create_test_vehicle(self):
        """Create a test vehicle in the database"""
        test_vehicle = {
            "location": {
                "latitude": 14.5995,  # Original location (Manila coordinates)
                "longitude": 120.9842
            },
            "vehicle_type": "newPUV",
            "capacity": 20,
            "available_seats": 15,
            "status": "available",
            "route": "Test Route",
            "driverName": "Test Driver",
            "plate": "TEST123",
            "device_id": "iot_device_001",
            "fleet_id": "fleet_001"
        }

        result = self.db.vehicles.insert_one(test_vehicle)
        vehicle_id = str(result.inserted_id)
        print(f"✅ Test vehicle created with ID: {vehicle_id}")
        print(
            f"📍 Initial location: lat={test_vehicle['location']['latitude']}, lng={test_vehicle['location']['longitude']}")
        return vehicle_id

    def get_vehicle_location(self, vehicle_id):
        """Get current vehicle location from database"""
        vehicle = self.db.vehicles.find_one({"_id": ObjectId(vehicle_id)})
        if vehicle:
            return vehicle.get("location", {})
        return None

    def wait_for_models(self, timeout=60, check_interval=5):
        """Wait for models to be ready"""
        print("🔄 Checking if models are ready...")

        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                response = requests.get(f"{self.base_url}/predict/status")
                status = response.json()

                if status.get("status") == "ready":
                    print("✅ Models are ready!")
                    return True
                elif status.get("status") == "loading":
                    print("⏳ Models are still loading...")
                elif status.get("status") == "error":
                    print(f"❌ Model loading failed: {status.get('error')}")
                    return False
                else:
                    print(f"⏳ Model status: {status.get('status', 'unknown')}")

            except requests.RequestException as e:
                print(f"❌ Error checking status: {e}")
                return False

            time.sleep(check_interval)

        print("⏰ Timeout waiting for models to load")
        return False

    def make_prediction(self, vehicle_id):
        """Make a prediction request"""
        prediction_data = {
            # Required identifiers - use the actual vehicle ID
            "vehicle_id": vehicle_id,
            "device_id": "iot_device_001",
            "fleet_id": "fleet_001",

            # GPS and sensor data
            "Cn0DbHz": 45.5,
            "Svid": 1,
            "SvElevationDegrees": 30.0,
            "SvAzimuthDegrees": 180.0,
            "IMU_MessageType": "ACCEL",
            "MeasurementX": 1000.0,
            "MeasurementY": 2000.0,
            "MeasurementZ": 3000.0,
            "BiasX": 0.1,
            "BiasY": 0.2,
            "BiasZ": 0.3,
            "WlsPositionXEcefMeters": -2700000.0,
            "WlsPositionYEcefMeters": -4300000.0,
            "WlsPositionZEcefMeters": 3800000.0
        }

        try:
            response = requests.post(
                f"{self.base_url}/predict",
                json=prediction_data
            )

            if response.status_code == 200:
                return {"status": "success", "data": response.json()}
            else:
                return {"status": "error", "message": response.json().get("detail", "Unknown error")}

        except requests.RequestException as e:
            return {"status": "error", "message": str(e)}

    def cleanup_test_vehicle(self, vehicle_id):
        """Remove the test vehicle from database"""
        result = self.db.vehicles.delete_one({"_id": ObjectId(vehicle_id)})
        if result.deleted_count > 0:
            print(f"🗑️ Test vehicle {vehicle_id} cleaned up")
        else:
            print(f"⚠️ Test vehicle {vehicle_id} was not found for cleanup")

    def run_test(self):
        """Run the complete test"""
        print("🧪 Starting Vehicle Location Update Test")
        print("="*50)

        # Step 1: Wait for models to be ready
        if not self.wait_for_models():
            print("❌ Test failed: Models not ready")
            return False

        # Step 2: Create test vehicle
        vehicle_id = self.create_test_vehicle()

        try:
            # Step 3: Get initial location
            initial_location = self.get_vehicle_location(vehicle_id)
            print(f"📍 Initial location: {initial_location}")

            # Step 4: Make prediction
            print("\n🎯 Making prediction request...")
            result = self.make_prediction(vehicle_id)

            if result["status"] == "success":
                print("✅ Prediction successful!")
                prediction_data = result["data"]
                corrected_lat = prediction_data["latitude"]
                corrected_lng = prediction_data["longitude"]
                print(
                    f"🎯 Predicted corrected coordinates: lat={corrected_lat:.6f}, lng={corrected_lng:.6f}")

                # Step 5: Check if vehicle location was updated
                print("\n🔍 Checking if vehicle location was updated in database...")
                time.sleep(1)  # Give a moment for the database update

                updated_location = self.get_vehicle_location(vehicle_id)
                print(f"📍 Updated location in DB: {updated_location}")

                # Step 6: Verify the update
                if updated_location:
                    db_lat = updated_location.get("latitude")
                    db_lng = updated_location.get("longitude")

                    if abs(db_lat - corrected_lat) < 0.000001 and abs(db_lng - corrected_lng) < 0.000001:
                        print(
                            "🎉 SUCCESS: Vehicle location was correctly updated in the database!")
                        print(
                            f"   Prediction: lat={corrected_lat:.6f}, lng={corrected_lng:.6f}")
                        print(
                            f"   Database:   lat={db_lat:.6f}, lng={db_lng:.6f}")
                        return True
                    else:
                        print(
                            "❌ FAILURE: Vehicle location in database doesn't match predicted coordinates")
                        print(
                            f"   Prediction: lat={corrected_lat:.6f}, lng={corrected_lng:.6f}")
                        print(
                            f"   Database:   lat={db_lat:.6f}, lng={db_lng:.6f}")
                        return False
                else:
                    print(
                        "❌ FAILURE: Could not retrieve updated vehicle location from database")
                    return False

            else:
                print(
                    f"❌ Prediction failed: {result.get('message', 'Unknown error')}")
                return False

        finally:
            # Step 7: Cleanup
            print("\n🧹 Cleaning up...")
            self.cleanup_test_vehicle(vehicle_id)

        return False


def main():
    test = VehicleLocationUpdateTest()
    success = test.run_test()

    if success:
        print("\n🎉 All tests passed! Vehicle location update is working correctly.")
    else:
        print("\n❌ Test failed! Please check the implementation.")


if __name__ == "__main__":
    main()
