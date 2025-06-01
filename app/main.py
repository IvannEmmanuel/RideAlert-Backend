from fastapi import FastAPI
from app.routes import user

app = FastAPI()

app.include_router(user.router)
# Include other routers as needed

@app.get("/")
def read_root():
    return {"message": "Server is running"}