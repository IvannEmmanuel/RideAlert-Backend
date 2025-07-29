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
        print("📦 Background loading configured (models will load on-demand)")
    except Exception as e:
        print(f"⚠️ Background loader setup warning: {e}")
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
        background_loader.is_loading = True
        
        # Start actual model loading in background thread
        import threading
        def load_models_now():
            try:
                print("🔄 Manual model loading triggered...")
                background_loader.ml_manager._load_all()
                background_loader.load_complete = True
                background_loader.is_loading = False
                print("✅ Manual model loading completed!")
            except Exception as e:
                error_msg = f"Manual model loading failed: {str(e)}"
                print(f"❌ {error_msg}")
                background_loader.load_error = error_msg
                background_loader.is_loading = False
        
        # Start in daemon thread
        thread = threading.Thread(target=load_models_now)
        thread.daemon = True
        thread.start()
        
        return {"message": "Manual model loading started", "status": "loading"}
    except Exception as e:
        return {"message": f"Failed to start model loading: {str(e)}", "status": "error"}
