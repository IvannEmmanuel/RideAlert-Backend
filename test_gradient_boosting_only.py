#!/usr/bin/env python3
"""
Test script to verify that the ML model works with only gradient boosting
(no random forest)
"""

import requests
import json
import time


def test_prediction():
    """Test the prediction endpoint with only gradient boosting"""
    base_url = "http://127.0.0.1:8000"

    # Test data for prediction
    test_data = {
        "Cn0DbHz": 35.5,
        "Svid": 12,
        "SvElevationDegrees": 45.0,
        "SvAzimuthDegrees": 180.0,
        "IMU_MessageType": "ACCELEROMETER",
        "MeasurementX": 0.1,
        "MeasurementY": 0.2,
        "MeasurementZ": 9.8,
        "BiasX": 0.01,
        "BiasY": 0.02,
        "BiasZ": 0.03,
        "WlsPositionXEcefMeters": 1000000.0,
        "WlsPositionYEcefMeters": 2000000.0,
        "WlsPositionZEcefMeters": 3000000.0
    }

    print("🧪 Testing gradient boosting only prediction...")
    print(f"📡 Server URL: {base_url}")

    # First check if server is running
    try:
        response = requests.get(f"{base_url}/")
        print(f"✅ Server status: {response.json()}")
    except requests.exceptions.ConnectionError:
        print("❌ Server is not running. Please start it first.")
        return

    # Check prediction status
    try:
        response = requests.get(f"{base_url}/predict/status")
        status = response.json()
        print(f"📊 Prediction status: {status}")

        if status.get('status') == 'loading':
            print("⏳ Models are loading, waiting 30 seconds...")
            time.sleep(30)
            response = requests.get(f"{base_url}/predict/status")
            status = response.json()
            print(f"📊 Updated status: {status}")

    except Exception as e:
        print(f"⚠️ Status check error: {e}")

    # Make prediction
    try:
        print("🔮 Making prediction request...")
        response = requests.post(f"{base_url}/predict", json=test_data)

        if response.status_code == 200:
            result = response.json()
            print("✅ Prediction successful!")
            print(f"📈 Prediction result: {result['prediction']}")
            print(
                f"🌍 WLS coordinates: ({result['wls_latitude']:.6f}, {result['wls_longitude']:.6f})")
            print(
                f"🎯 Corrected coordinates: ({result['corrected_latitude']:.6f}, {result['corrected_longitude']:.6f})")
            print(f"📊 Model status: {result['model_status']}")

        elif response.status_code == 202:
            print("⏳ Models are still loading, try again later")
            print(f"Response: {response.json()}")

        elif response.status_code == 503:
            print("❌ Service unavailable")
            print(f"Error: {response.json()}")

        else:
            print(f"❌ Prediction failed with status {response.status_code}")
            print(f"Response: {response.text}")

    except Exception as e:
        print(f"❌ Prediction error: {e}")


if __name__ == "__main__":
    test_prediction()
