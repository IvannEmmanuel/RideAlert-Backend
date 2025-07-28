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
    background_loader.start_background_loading()
    print("📦 Background model loading initiated")
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


@app.get("/status")
def server_status():
    """Get overall server status including model loading"""
    model_status = background_loader.get_status()
    return {
        "server": "running",
        "models": model_status
    }
