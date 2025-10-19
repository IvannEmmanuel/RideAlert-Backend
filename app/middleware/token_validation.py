from fastapi import Request
import logging

logger = logging.getLogger(__name__)

async def token_validation_middleware(request: Request, call_next):
    """
    This middleware is now a pass-through.
    Token validation happens at the route level via dependencies.
    This middleware can be used for logging or other purposes.
    """
    # Log the request
    logger.debug(f"{request.method} {request.url.path}")
    
    response = await call_next(request)
    return response