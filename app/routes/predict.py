from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.utils.background_loader import background_loader
import math

router = APIRouter()


class PredictionRequest(BaseModel):
    Cn0DbHz: float
    Svid: int
    SvElevationDegrees: float
    SvAzimuthDegrees: float
    IMU_MessageType: str
    MeasurementX: float
    MeasurementY: float
    MeasurementZ: float
    BiasX: float
    BiasY: float
    BiasZ: float
    WlsPositionXEcefMeters: float
    WlsPositionYEcefMeters: float
    WlsPositionZEcefMeters: float


@router.get("/predict/status")
async def get_prediction_status():
    """Check if the prediction service is ready"""
    status = background_loader.get_status()
    return status


@router.post("/predict")
async def predict(request: PredictionRequest):
    try:
        # Check if models are ready
        status = background_loader.get_status()

        if status["status"] == "error":
            raise HTTPException(
                status_code=503,
                detail=f"Models failed to load: {status.get('error', 'Unknown error')}"
            )

        if status["status"] == "loading":
            raise HTTPException(
                status_code=202,  # Accepted, but processing
                detail="Models are still being downloaded and loaded in the background. Please try again in a moment."
            )

        if status["status"] == "not_started":
            # Fallback: start loading if somehow not started
            background_loader.start_background_loading()
            raise HTTPException(
                status_code=202,
                detail="Model loading initiated. Please try again in a few minutes."
            )

        # Get the ML manager (should be ready now)
        ml_manager = background_loader.get_ml_manager()
        if not ml_manager:
            raise HTTPException(
                status_code=503,
                detail="Models are not ready yet. Please try again."
            )

        input_data = request.dict()
        input_data['SignalQuality'] = input_data['Cn0DbHz'] * \
            math.sin(math.radians(input_data['SvElevationDegrees']))
        input_data['WLS_Distance'] = math.sqrt(
            input_data['WlsPositionXEcefMeters']**2 +
            input_data['WlsPositionYEcefMeters']**2 +
            input_data['WlsPositionZEcefMeters']**2
        )

        # Models are loaded, prediction should be fast
        prediction = ml_manager.predict(input_data)

        # Get WLS latitude and longitude from input (ground truth columns are not present, so use WLS ECEF)
        # Use pyproj to convert ECEF to lat/lon
        from pyproj import Transformer
        transformer = Transformer.from_crs(
            "EPSG:4978", "EPSG:4326", always_xy=True)
        wls_lng, wls_lat, _ = transformer.transform(
            input_data['WlsPositionXEcefMeters'],
            input_data['WlsPositionYEcefMeters'],
            input_data['WlsPositionZEcefMeters']
        )
        corrected_lat = wls_lat + prediction[0]
        corrected_lng = wls_lng + prediction[1]

        return {
            "prediction": prediction,
            "wls_latitude": wls_lat,
            "wls_longitude": wls_lng,
            "corrected_latitude": corrected_lat,
            "corrected_longitude": corrected_lng,
            "model_status": "ready"
        }
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        error_msg = str(e)
        raise HTTPException(
            status_code=500, detail=f"Prediction error: {error_msg}")
