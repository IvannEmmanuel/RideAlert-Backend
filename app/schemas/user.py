from pydantic import BaseModel, EmailStr
from enum import Enum
from typing import Optional

class UserRole(str, Enum):
    user = "user"
    admin = "admin"

class UserBase(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    birthday: str
    address: str
    gender: str
    role: UserRole

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
    birthday: str
    gender: str
    address: str
    role: UserRole