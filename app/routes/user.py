from fastapi import APIRouter, HTTPException, Depends, Body
from app.schemas.user import UserCreate, UserInDB, UserLogin, Location
from app.database import user_collection
from app.models.user import user_helper
from bson import ObjectId
from app.utils.pasword_hashing import hash_password
from app.utils.pasword_hashing import verify_password
from app.utils.token import create_access_token
from fastapi.responses import JSONResponse
from app.dependencies.roles import admin_required, user_required, user_or_admin_required


router = APIRouter(prefix="/users", tags=["Users"])

@router.post("/register", response_model=UserInDB)
def create_user(user: UserCreate):
    if user_collection.find_one({"email": user.email}):
        raise HTTPException(status_code=400, detail="Email already registered")

    user_dict = user.dict()
    user_dict["password"] = hash_password(user.password)  # hash here
    user_dict["role"] = user.role or "user"

    result = user_collection.insert_one(user_dict)
    created_user = user_collection.find_one({"_id": result.inserted_id})
    return user_helper(created_user)

@router.get("/{user_id}", response_model=UserInDB)
def get_user(user_id: str, current_user: dict = Depends(user_or_admin_required)):
    user = user_collection.find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user_helper(user)

@router.post("/login")
def login_user(login_data: UserLogin):
    user = user_collection.find_one({"email": login_data.email})

    if not user or not verify_password(login_data.password, user["password"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token_data = {
        "user_id": str(user["_id"]),
        "email": user["email"],
        "role": user["role"]
    }

    access_token = create_access_token(token_data)

    return JSONResponse(content={
        "access_token": access_token,
        "user": {
            "id": str(user["_id"]),
            "first_name": user.get("first_name"),
            "last_name": user.get("last_name"),
            "email": user.get("email"),
            "gender": user.get("gender"),
            "address": user.get("address"),
            "role": user.get("role"),
            "location": user.get("location", {})
        }
    })

@router.post("/location")
def update_location(
    location: Location,
    current_user: dict = Depends(user_or_admin_required)
):
    user_id = current_user.get("user_id") or current_user.get("_id")
    if not user_id:
        raise HTTPException(status_code=400, detail="User ID not found in token")

    result = user_collection.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"location": location.dict()}}
    )

    if result.matched_count == 1:
        return {"message": "The location is updated successfully"}

    raise HTTPException(status_code=404, detail="User not found")


@router.post("/fcm-token")
async def save_fcm_token(
    user_id: str = Body(...),
    fcm_token: str = Body(...)
):
    result = user_collection.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"fcm_token": fcm_token}}
    )
    if result.modified_count == 1:
        return {"message": "FCM token saved"}
    raise HTTPException(status_code=404, detail="User not found")