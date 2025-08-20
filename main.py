from fastapi import FastAPI, HTTPException
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
    allow_origins=["http://localhost:5173"],  # Allow all origins, adjust as needed
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
    try:
        # Basic health check
        health_status = {
            "status": "healthy", 
            "message": "RideAlert Backend is running",
            "timestamp": "2025-08-16"
        }
        
        # Optional: Check database connection (non-blocking)
        try:
            from app.database import get_database
            db = get_database()
            # Simple ping to check connection
            db.command('ping')
            health_status["database"] = "connected"
        except Exception as db_error:
            # Don't fail the health check if DB is temporarily unavailable
            health_status["database"] = "warning"
            health_status["db_message"] = "Database connection issue (non-critical)"
        
        # Check ML model status (non-blocking)
        try:
            ml_status = background_loader.get_status()
            health_status["ml_models"] = ml_status.get("status", "unknown")
        except Exception:
            health_status["ml_models"] = "not_checked"
        
        return health_status
        
    except Exception as e:
        # If health check itself fails, return error but still return 200
        return {
            "status": "degraded",
            "message": "Health check encountered issues",
            "error": str(e)
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
                print(
                    f"📊 Initial state: loading={background_loader.is_loading}, complete={background_loader.load_complete}, error={background_loader.load_error}")

                # Try memory-optimized loading
                print("🧠 Attempting memory-optimized model loading...")
                import gc
                import os

                # Force garbage collection before loading
                gc.collect()

                # Load models with memory optimization
                try:
                    print("📦 Loading models with memory optimization...")
                    background_loader.ml_manager._load_all()

                    # Force garbage collection after loading
                    gc.collect()

                    background_loader.load_complete = True
                    background_loader.is_loading = False
                    background_loader.load_error = None

                    print("✅ Memory-optimized model loading completed!")
                    print(
                        f"📊 Final state: loading={background_loader.is_loading}, complete={background_loader.load_complete}")

                except MemoryError as me:
                    error_msg = f"Railway memory limit exceeded: {str(me)}"
                    print(f"💾 {error_msg}")
                    background_loader.load_error = f"Memory limit exceeded. Try upgrading Railway plan."
                    background_loader.is_loading = False
                    background_loader.load_complete = False

                except Exception as model_error:
                    error_msg = f"Model loading error: {str(model_error)}"
                    print(f"❌ {error_msg}")
                    background_loader.load_error = error_msg
                    background_loader.is_loading = False
                    background_loader.load_complete = False

            except Exception as e:
                error_msg = f"Manual model loading failed: {str(e)}"
                print(f"❌ {error_msg}")
                background_loader.load_error = error_msg
                background_loader.is_loading = False
                background_loader.load_complete = False

        # Start in daemon thread
        thread = threading.Thread(target=load_models_now)
        thread.daemon = True
        thread.start()

        return {"message": "Manual model loading started", "status": "loading"}
    except Exception as e:
        return {"message": f"Failed to start model loading: {str(e)}", "status": "error"}
