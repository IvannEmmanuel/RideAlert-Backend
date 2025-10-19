from fastapi import Depends, HTTPException, status
from app.dependencies.auth import get_current_user

def super_admin_required(current_user: dict = Depends(get_current_user)):
    """Only superadmin role allowed"""
    if current_user.get("role") != "superadmin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super Admin access required"
        )
    return current_user

def admin_required(current_user: dict = Depends(get_current_user)):
    """Only admin role allowed"""
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user

def user_required(current_user: dict = Depends(get_current_user)):
    """Only user role allowed"""
    if current_user.get("role") != "user":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User access required"
        )
    return current_user

def user_or_admin_required(current_user: dict = Depends(get_current_user)):
    """Both user and admin roles allowed"""
    if current_user.get("role") not in ("user", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access this resource."
        )
    return current_user

def super_and_admin_required(current_user: dict = Depends(get_current_user)):
    """Both superadmin and admin roles allowed"""
    if current_user.get("role") not in ("superadmin", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access this resource."
        )
    return current_user

def fleet_owner_required(current_user: dict = Depends(get_current_user)):
    """Fleet owner (admin or superadmin) required"""
    if current_user.get("role") not in ("admin", "superadmin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Fleet owner access required"
        )
    return current_user