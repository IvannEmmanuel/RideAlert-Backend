from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.utils.ml_model import ml_manager
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


@router.post("/predict")
async def predict(request: PredictionRequest):
    try:
        input_data = request.dict()
        input_data['SignalQuality'] = input_data['Cn0DbHz'] * \
            math.sin(math.radians(input_data['SvElevationDegrees']))
        input_data['WLS_Distance'] = math.sqrt(
            input_data['WlsPositionXEcefMeters']**2 +
            input_data['WlsPositionYEcefMeters']**2 +
            input_data['WlsPositionZEcefMeters']**2
        )
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
            "corrected_longitude": corrected_lng
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
