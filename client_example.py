"""
Example client for the RideAlert Backend ML Prediction API

This example shows how to:
1. Check if the server and models are ready
2. Wait for models to load if needed
3. Make predictions once ready
"""

import requests
import time
import json


class RideAlertClient:
    def __init__(self, base_url="http://localhost:8000"):
        self.base_url = base_url

    def check_server_status(self):
        """Check overall server status"""
        try:
            response = requests.get(f"{self.base_url}/status")
            return response.json()
        except requests.RequestException as e:
            return {"error": str(e)}

    def check_prediction_status(self):
        """Check if prediction service is ready"""
        try:
            response = requests.get(f"{self.base_url}/predict/status")
            return response.json()
        except requests.RequestException as e:
            return {"error": str(e)}

    def wait_for_models(self, timeout=300, check_interval=10):
        """Wait for models to be ready"""
        print("🔄 Checking if models are ready...")

        start_time = time.time()
        while time.time() - start_time < timeout:
            status = self.check_prediction_status()

            if "error" in status:
                print(f"❌ Error checking status: {status['error']}")
                return False

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

            time.sleep(check_interval)

        print("⏰ Timeout waiting for models to load")
        return False

    def predict(self, prediction_data):
        """Make a prediction"""
        try:
            response = requests.post(
                f"{self.base_url}/predict",
                json=prediction_data
            )

            if response.status_code == 202:
                # Models still loading
                return {"status": "loading", "message": response.json().get("detail")}
            elif response.status_code == 200:
                return {"status": "success", "data": response.json()}
            else:
                return {"status": "error", "message": response.json().get("detail", "Unknown error")}

        except requests.RequestException as e:
            return {"status": "error", "message": str(e)}


def main():
    # Example usage
    client = RideAlertClient()

    # Check server status
    print("🚀 Checking server status...")
    server_status = client.check_server_status()
    print(f"Server status: {json.dumps(server_status, indent=2)}")

    # Wait for models to be ready
    if not client.wait_for_models():
        print("❌ Models failed to load, exiting")
        return

    # Example prediction data
    prediction_data = {
        # Required identifiers
        "vehicle_id": "vehicle_001",  # Replace with your actual vehicle ID
        "device_id": "iot_device_001",  # Replace with your actual IoT device ID

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

    # Make prediction
    print("\n🎯 Making prediction...")
    result = client.predict(prediction_data)

    if result["status"] == "success":
        print("✅ Prediction successful!")
        data = result["data"]
        print(
            f"Corrected coordinates: {data['corrected_latitude']}, {data['corrected_longitude']}")
        print(f"Full response: {json.dumps(data, indent=2)}")
    else:
        print(f"❌ Prediction failed: {result.get('message', 'Unknown error')}")


if __name__ == "__main__":
    main()
