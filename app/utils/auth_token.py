# app/utils/token.py
from jose import JWTError, jwt
from datetime import datetime, timedelta
from dotenv import load_dotenv
import os

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")

ACCESS_KEY = SECRET_KEY

ALGORITHM = "HS256"


#Creating an access token
def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(hours=1)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, ACCESS_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def create_refresh_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=30)  # long-lived
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, ACCESS_KEY, algorithm=ALGORITHM)

def verify_access_token(token: str):
    try:
        payload = jwt.decode(token, ACCESS_KEY, algorithms=[ALGORITHM])
        return payload  # contains the user_id or email, etc.
    except JWTError:
        return None