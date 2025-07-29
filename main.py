from fastapi import FastAPI
from app.routes import user
from app.routes import vehicle
from app.routes.websockets import ws_router
from app.routes.notifications_router import router as notifications_router
from app.routes import predict
from app.routes import models
from fastapi.middleware.cors import CORSMiddleware
from app.utils.background_loader import background_loader
from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("🚀 FastAPI starting up...")
    try:
        background_loader.start_background_loading()
        print("📦 Background model loading initiated (optional)")
    except Exception as e:
        print(f"⚠️ Model loading startup warning: {e}")
        print("📋 App will continue without ML models")
    yield
    # Shutdown
    print("🔄 FastAPI shutting down...")


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins, adjust as needed
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods, adjust as needed
    allow_headers=["*"],  # Allow all headers, adjust as needed
)

app.include_router(user.router)
app.include_router(vehicle.router)
app.include_router(ws_router)
app.include_router(notifications_router)
app.include_router(predict.router)
app.include_router(models.router)
# Include other routers as needed


@app.get("/")
def read_root():
    return {"message": "Server is running"}


@app.get("/health")
def health_check():
    """Health check endpoint for Railway deployment"""
    return {
        "status": "healthy",
        "message": "RideAlert Backend is running"
    }


@app.get("/status")
def server_status():
    """Get overall server status including model loading"""
    model_status = background_loader.get_status()
    return {
        "server": "running",
        "models": model_status
    }


@app.post("/admin/reload-models")
def reload_models():
    """Manually trigger model reloading (useful after setting environment variables)"""
    try:
        if background_loader.is_loading:
            return {"message": "Models are already loading", "status": "loading"}
        
        # Reset the loader state
        background_loader.load_complete = False
        background_loader.load_error = None
        background_loader.is_loading = False
        
        # Start loading again
        background_loader.start_background_loading()
        return {"message": "Model loading triggered", "status": "started"}
    except Exception as e:
        return {"message": f"Failed to start model loading: {str(e)}", "status": "error"}
