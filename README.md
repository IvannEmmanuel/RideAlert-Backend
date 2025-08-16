# 🚗 **RideAlert - Real-Time Vehicle Tracking API**

---

## **Overview**

**RideAlert** is a **FastAPI-based backend** for real-time vehicle tracking and user management, using **MongoDB** for data storage and **gradient boosting ML model** for GPS correction predictions.

---

## **Features**

-   🧑‍💻 **User registration, login, and role-based access** (admin/user)
-   🚙 **Vehicle creation and real-time location tracking**
-   🔌 **WebSocket endpoint** for live vehicle location updates
-   🤖 **ML-powered GPS correction** using gradient boosting algorithm
-   🗄️ **MongoDB integration** for persistent storage

---

## **Setup Instructions**

1. **Clone this repository.**
2. **Install dependencies:**
    ```sh
    pip install -r requirements.txt
    ```
3. **Create a `.env` file in the root directory with:**
    ```
    MONGO_URI=<your-mongodb-uri>
    SECRET_KEY=<your-secret-key>
    # ML Model URLs (required for prediction service)
    ENHANCED_FEATURES_V6=<model-url>
    ENHANCED_LABEL_ENCODERS_V6=<model-url>
    GRADIENT_BOOSTING_MODEL_V6=<model-url>
    ROBUST_SCALER_V6=<model-url>
    ```
4. **Run the FastAPI server:**
   ```sh
   uvicorn app.main:app --reload or python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
   ```

---

## **API Endpoints**

| Method | Endpoint               | Description                              |
| ------ | ---------------------- | ---------------------------------------- |
| POST   | `/users/register`      | Register a new user                      |
| POST   | `/users/login`         | User login (returns JWT)                 |
| GET    | `/users/{user_id}`     | Get user info (admin only)               |
| POST   | `/vehicles/create`     | Create a new vehicle (admin only)        |
| GET    | `/vehicles/track/{id}` | Get vehicle location/status              |
| GET    | `/vehicles/all`        | List all vehicles with locations         |
| POST   | `/predict`             | ML prediction for GPS correction         |
| GET    | `/predict/status`      | Check ML model loading status            |
| WS     | `/ws/location`         | WebSocket for updating vehicle locations |

---

## **Project Structure**

```
app/
  ├── main.py           # FastAPI app entry point
  ├── database.py       # MongoDB connection and collections
  ├── routes/           # API and WebSocket routes
  │   ├── predict.py    # ML prediction endpoints
  │   └── ...          # Other route files
  ├── models/           # Data transformation helpers
  ├── schemas/          # Pydantic models for validation
  ├── utils/            # Utility functions (auth, hashing, ML models)
  │   ├── ml_model.py   # Gradient boosting model manager
  │   └── ...          # Other utilities
  ├── ml/              # ML model files (downloaded at runtime)
  └── dependencies/     # Dependency injection (auth, roles)
```

---

## **Machine Learning Features**

-   🤖 **Gradient Boosting Model** for GPS correction predictions
-   📊 **Real-time model loading** on server startup
-   🎯 **Testing mode** with ground truth comparison (configurable)
-   🔄 **Automatic model download** from cloud storage

---

## **Notes**

-   ⚡ **Requires Python 3.8+**
-   🗄️ **Make sure MongoDB is running and accessible**
-   🤖 **ML models are downloaded automatically on first startup**
-   🛠️ **For development, use the `--reload` flag with uvicorn**
