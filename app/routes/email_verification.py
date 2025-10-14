from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr
from app.utils.email_sender import email_sender
from app.utils.rate_limiter import email_rate_limiter
import os

router = APIRouter(prefix="/auth", tags=["Email Verification"])

class SendVerificationRequest(BaseModel):
    email: EmailStr

class VerifyEmailRequest(BaseModel):
    email: EmailStr
    verification_code: str

@router.post("/send-verification-email")
async def send_verification_email(request: SendVerificationRequest):
    """Send verification email with OTP"""

    if email_rate_limiter.is_rate_limited(request.email):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many verification attempts. Please try again in 15 minutes."
        )
    
    # ✅ FIXED: Check Brevo configuration
    if not email_sender.brevo_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email service is not configured. Please contact administrator."
        )
    
    try:
        # Generate OTP
        otp = email_sender.generate_otp()
        
        # Store OTP
        email_sender.store_otp(request.email, otp)
        
        # Send email
        success = email_sender.send_verification_email(request.email, otp)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to send verification email. Please try again."
            )
        
        # For development - include OTP in response (remove in production)
        debug_info = {}
        if os.getenv("DEBUG", "").lower() == "true" or os.getenv("NODE_ENV") == "development":
            debug_info["debug_otp"] = otp
            print(f"🔓 DEBUG MODE: OTP for {request.email} is {otp}")
        
        return {
            "message": "Verification code sent successfully",
            **debug_info
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send verification email: {str(e)}"
        )

@router.post("/verify-email")
async def verify_email(request: VerifyEmailRequest):
    """Verify email with OTP"""
    try:
        # Verify OTP
        is_valid = email_sender.verify_otp(request.email, request.verification_code)
        
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired verification code"
            )
        
        return {
            "message": "Email verified successfully",
            "verified": True
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Verification failed: {str(e)}"
        )