from fastapi import FastAPI
from app.routes import user
from app.routes import vehicle
from app.routes.websockets import ws_router

app = FastAPI()

app.include_router(user.router)
app.include_router(vehicle.router)
app.include_router(ws_router)
# Include other routers as needed

@app.get("/")
def read_root():
    return {"message": "Server is running"}