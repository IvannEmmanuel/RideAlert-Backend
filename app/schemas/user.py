from pydantic import BaseModel, EmailStr
from enum import Enum
from typing import Optional

class UserRole(str, Enum):
    user = "user"
    admin = "admin"

class Location(BaseModel):
    latitude: float
    longitude: float

class UserBase(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    address: str
    gender: str
    role: UserRole
    location: Optional[Location] = None

class UserCreate(UserBase):
    password: str
    role: Optional[UserRole] = None  # optional field

class UserInDB(UserBase):
    id: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserPublic(BaseModel):
    id: str
    first_name: str
    last_name: str
    email: EmailStr
    gender: str
    address: str
    role: UserRole