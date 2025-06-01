from pydantic import BaseModel, EmailStr
from typing import Optional

class UserBase(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    birthday: str
    address: str
    gender: str

class UserCreate(UserBase):
    password: str

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