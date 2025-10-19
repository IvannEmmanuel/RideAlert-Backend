from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer
from app.utils.auth_token import verify_access_token
import logging

logger = logging.getLogger(__name__)
security = HTTPBearer()

async def get_current_user(credentials = Depends(security)):
    """
    Extract and verify the current user from the JWT token.
    
    This dependency:
    1. Extracts the Bearer token from the Authorization header
    2. Verifies the token signature and expiration
    3. Returns the decoded payload or raises 401
    
    The frontend interceptor catches the 401 and automatically:
    - Calls /fleets/refresh with the refresh_token
    - Gets a new access_token
    - Retries the original request with the new token
    """
    token = credentials.credentials
    
    # Verify token (includes expiration check via PyJWT)
    payload = verify_access_token(token)
    
    if not payload:
        logger.warning("Token verification failed - token is expired or invalid")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired or invalid",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Extract user info from token payload
    user_id = payload.get("fleet_id") or payload.get("user_id") or payload.get("id")
    email = payload.get("email")
    role = payload.get("role")
    
    if not user_id:
        logger.error("Token missing required user_id/fleet_id")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing required user information",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return {
        "user_id": user_id,
        "fleet_id": user_id,
        "email": email,
        "role": role
    }