from app.workers.background_status_checker import start_background_status_checker
from fastapi import FastAPI
from fastapi import Response
from app.routes import user
from app.routes import vehicle
from app.routes.websockets import ws_router
from app.routes.notifications_router import router as notifications_router
from app.routes.iot_devices import router as iot_router
from app.routes.fleets import router as fleets_router
from app.routes.email_verification import router as email_router
from app.routes.route_assignment import router as route_assignment_router
from app.routes.notification_web import router as notifications_collection
from app.routes.subscription_plans import router as get_subscription_plans_collection
from app.routes import predict
from app.routes import models
import app.routes.declared_routes as declared_routes
from fastapi.middleware.cors import CORSMiddleware
from app.utils.background_loader import background_loader
from app.middleware.token_validation import token_validation_middleware  # ADD THIS
from contextlib import asynccontextmanager
from app.workers.proximity_checker import start_proximity_checker, stop_proximity_checker
from app.routes.vehicle import background_eta_updater
import logging
import asyncio

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global proximity_task
    global eta_task

    # Startup
    print("🚀 FastAPI starting up...")

    # Start background model loader
    try:
        background_loader.start_background_loading()
        print("📦 Background loading configured (models will load on-demand)")
    except Exception as e:
        print(f"⚠️ Background loader setup warning: {e}")

    # Start background status checker
    try:
        start_background_status_checker()
        print("✅ Background status checker started")
        logger.info("✅ Background status checker started")
    except Exception as e:
        print(f"⚠️ Background status checker startup warning: {e}")
        logger.error(f"⚠️ Background status checker startup warning: {e}")

    # Start proximity checker
    try:
        proximity_task = asyncio.create_task(start_proximity_checker())
        print("✅ Proximity checker started")
    except Exception as e:
        print(f"⚠️ Proximity checker startup warning: {e}")

    # Start ETA background updater
    try:
        eta_task = asyncio.create_task(background_eta_updater())
        print("✅ ETA background updater started")
    except Exception as e:
        print(f"⚠️ ETA background updater startup warning: {e}")

    yield

    # Shutdown
    print("🔄 FastAPI shutting down...")

    # Stop proximity checker
    try:
        stop_proximity_checker()
        if proximity_task:
            proximity_task.cancel()
            try:
                await proximity_task
            except asyncio.CancelledError:
                print("✅ Proximity checker stopped")
    except Exception as e:
        print(f"⚠️ Proximity checker shutdown warning: {e}")

    # Stop ETA updater
    try:
        if eta_task:
            eta_task.cancel()
            try:
                await eta_task
            except asyncio.CancelledError:
                print("✅ ETA background updater stopped")
    except Exception as e:
        print(f"⚠️ ETA background updater shutdown warning: {e}")


app = FastAPI(lifespan=lifespan)

# Add CORS middleware first
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173",
                   "https://ride-alert-admin-panel.vercel.app",
                   "http://localhost:5174",
                   "http://localhost:8081",
                   "https://ridealertadminpanel.onrender.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)

# Add token validation middleware AFTER CORS
app.middleware("http")(token_validation_middleware)

# Include routers
app.include_router(user.router)
app.include_router(vehicle.router)
app.include_router(ws_router)
app.include_router(notifications_router)
app.include_router(predict.router)
app.include_router(models.router)
app.include_router(iot_router)
app.include_router(fleets_router)
app.include_router(email_router)
app.include_router(declared_routes.router)
app.include_router(route_assignment_router)
app.include_router(notifications_collection)
app.include_router(get_subscription_plans_collection)

@app.get("/")
def read_root():
    return {"message": "Server is running",
            "proximity_checker": "active",
            "eta_updater": "active"}


@app.get("/health")
def health_check():
    """Health check endpoint for Railway deployment"""
    return {
        "status": "healthy",
        "message": "RideAlert Backend is running",
        "proximity_checker": "active",
        "eta_updater": "active"
    }


@app.head("/healthz")
def healthz_head():
    """Lightweight liveness probe (HEAD) with no body"""
    return Response(status_code=200)


@app.get("/status")
def server_status():
    """Get overall server status including model loading"""
    model_status = background_loader.get_status()
    return {
        "server": "running",
        "models": model_status,
        "proximity_checker": "running" if proximity_task and not proximity_task.done() else "stopped",
        "eta_updater": "running" if 'eta_task' in globals() and eta_task and not eta_task.done() else "stopped"
    }


@app.post("/admin/reload-models")
def reload_models():
    """Manually trigger model reloading (useful after setting environment variables)"""
    try:
        if background_loader.is_loading:
            return {"message": "Models are already loading", "status": "loading"}

        background_loader.load_complete = False
        background_loader.load_error = None
        background_loader.is_loading = True

        import threading

        def load_models_now():
            try:
                print("🔄 Manual model loading triggered...")
                print(
                    f"📊 Initial state: loading={background_loader.is_loading}, complete={background_loader.load_complete}, error={background_loader.load_error}")

                print("🧠 Attempting memory-optimized model loading...")
                import gc
                gc.collect()

                try:
                    print("📦 Loading models with memory optimization...")
                    background_loader.ml_manager._load_all()
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

        thread = threading.Thread(target=load_models_now)
        thread.daemon = True
        thread.start()

        return {"message": "Manual model loading started", "status": "loading"}
    except Exception as e:
        return {"message": f"Failed to start model loading: {str(e)}", "status": "error"}