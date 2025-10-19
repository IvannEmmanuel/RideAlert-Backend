# # app/utils/token.py
# from jose import JWTError, jwt
# from datetime import datetime, timedelta
# from dotenv import load_dotenv
# import os

# load_dotenv()

# SECRET_KEY = os.getenv("SECRET_KEY")

# ACCESS_KEY = SECRET_KEY

# ALGORITHM = "HS256"


# #Creating an access token
# def create_access_token(data: dict):
#     to_encode = data.copy()
#     expire = datetime.utcnow() + timedelta(seconds=10)
#     to_encode.update({"exp": expire})
#     encoded_jwt = jwt.encode(to_encode, ACCESS_KEY, algorithm=ALGORITHM)
#     return encoded_jwt

# def create_refresh_token(data: dict):
#     to_encode = data.copy()
#     expire = datetime.utcnow() + timedelta(seconds=15)  # long-lived
#     to_encode.update({"exp": expire})
#     return jwt.encode(to_encode, ACCESS_KEY, algorithm=ALGORITHM)

# def verify_access_token(token: str):
#     try:
#         payload = jwt.decode(token, ACCESS_KEY, algorithms=[ALGORITHM])
#         return payload  # contains the user_id or email, etc.
#     except JWTError:
#         return None
    
# def verify_refresh_token(token: str):
#     try:
#         payload = jwt.decode(token, ACCESS_KEY, algorithms=[ALGORITHM])
#         return payload
#     except JWTError:
#         return None

from jose import JWTError, jwt
from datetime import datetime, timedelta
from dotenv import load_dotenv
import os
import logging

logger = logging.getLogger(__name__)
load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")
ACCESS_KEY = SECRET_KEY
ALGORITHM = "HS256"

# Token expiration times
ACCESS_TOKEN_EXPIRE_HOURS = 1
REFRESH_TOKEN_EXPIRE_DAYS = 30


def create_access_token(data: dict):
    """Create a short-lived access token (10 seconds)"""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, ACCESS_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def create_refresh_token(data: dict):
    """Create a long-lived refresh token (30 days)"""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, ACCESS_KEY, algorithm=ALGORITHM)


def verify_access_token(token: str) -> dict | None:
    """
    Verify an access token.
    
    PyJWT automatically checks expiration when decoding.
    If expired, jwt.decode() raises ExpiredSignatureError (a JWTError).
    
    Returns:
        dict: Token payload if valid
        None: If token is expired or invalid
    """
    try:
        payload = jwt.decode(token, ACCESS_KEY, algorithms=[ALGORITHM])
        logger.debug("Access token verified successfully")
        return payload
    except JWTError as e:
        logger.warning(f"Access token verification failed: {str(e)}")
        return None


def verify_refresh_token(token: str) -> dict | None:
    """
    Verify a refresh token.
    
    PyJWT automatically checks expiration when decoding.
    If expired, jwt.decode() raises ExpiredSignatureError (a JWTError).
    
    Returns:
        dict: Token payload if valid
        None: If token is expired or invalid
    """
    try:
        payload = jwt.decode(token, ACCESS_KEY, algorithms=[ALGORITHM])
        logger.debug("Refresh token verified successfully")
        return payload
    except JWTError as e:
        logger.warning(f"Refresh token verification failed: {str(e)}")
        return None