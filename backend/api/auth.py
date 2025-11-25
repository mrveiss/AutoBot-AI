# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Authentication API endpoints for AutoBot
Provides login, logout, and session management functionality
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, validator

from src.auth_middleware import auth_middleware
from src.utils.error_boundaries import ErrorCategory, with_error_handling

router = APIRouter()
logger = logging.getLogger(__name__)


class LoginRequest(BaseModel):
    """Login request model"""

    username: str
    password: str

    @validator("username")
    def validate_username(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError("Username cannot be empty")
        if len(v) > 50:
            raise ValueError("Username too long")
        # Basic sanitization
        v = v.strip().lower()
        if not v.replace("_", "").replace("-", "").replace(".", "").isalnum():
            raise ValueError("Username contains invalid characters")
        return v

    @validator("password")
    def validate_password(cls, v):
        if not v or len(v) < 1:
            raise ValueError("Password cannot be empty")
        if len(v) > 128:
            raise ValueError("Password too long")
        return v


class LoginResponse(BaseModel):
    """Login response model"""

    success: bool
    message: str
    user: Optional[dict] = None
    token: Optional[str] = None
    session_id: Optional[str] = None


class LogoutRequest(BaseModel):
    """Logout request model"""

    session_id: Optional[str] = None


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="login",
    error_code_prefix="AUTH",
)
@router.post("/login", response_model=LoginResponse)
async def login(request: Request, login_data: LoginRequest):
    """
    Authenticate user and create session/token

    Returns JWT token and session ID for authenticated user
    """
    try:
        ip_address = request.client.host if request.client else "unknown"

        # Authenticate user
        user_data = auth_middleware.authenticate_user(
            username=login_data.username,
            password=login_data.password,
            ip_address=ip_address,
        )

        if not user_data:
            # Generic error message to prevent username enumeration
            raise HTTPException(status_code=401, detail="Invalid username or password")

        # Create JWT token
        jwt_token = auth_middleware.create_jwt_token(user_data)

        # Create session
        session_id = auth_middleware.create_session(user_data, request)

        # Remove sensitive data from response
        safe_user_data = {
            "username": user_data["username"],
            "role": user_data["role"],
            "email": user_data.get("email", ""),
            "last_login": user_data.get("last_login"),
        }

        return LoginResponse(
            success=True,
            message="Login successful",
            user=safe_user_data,
            token=jwt_token,
            session_id=session_id,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error for user {login_data.username}: {e}")
        raise HTTPException(
            status_code=500, detail="Authentication service temporarily unavailable"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="logout",
    error_code_prefix="AUTH",
)
@router.post("/logout")
async def logout(request: Request, logout_data: LogoutRequest):
    """
    Logout user and invalidate session
    """
    try:
        # Get session ID from request body or header
        session_id = logout_data.session_id or request.headers.get("X-Session-ID")

        if session_id:
            auth_middleware.invalidate_session(session_id)

        return {"success": True, "message": "Logged out successfully"}

    except Exception as e:
        logger.error(f"Logout error: {e}")
        # Don't fail logout on errors - return success
        return {"success": True, "message": "Logged out successfully"}


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_current_user_info",
    error_code_prefix="AUTH",
)
@router.get("/me")
async def get_current_user_info(request: Request):
    """
    Get current authenticated user information
    """
    try:
        user_data = auth_middleware.get_user_from_request(request)

        if not user_data:
            raise HTTPException(status_code=401, detail="Not authenticated")

        # Return safe user data (no sensitive info)
        return {
            "username": user_data["username"],
            "role": user_data["role"],
            "email": user_data.get("email", ""),
            "auth_method": user_data.get("auth_method", "unknown"),
            "authenticated": True,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting user info: {e}")
        raise HTTPException(status_code=500, detail="Error retrieving user information")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="check_authentication",
    error_code_prefix="AUTH",
)
@router.get("/check")
async def check_authentication(request: Request):
    """
    Quick authentication check endpoint
    """
    try:
        user_data = auth_middleware.get_user_from_request(request)

        return {
            "authenticated": user_data is not None,
            "role": user_data["role"] if user_data else None,
            "auth_enabled": auth_middleware.enable_auth,
        }

    except Exception as e:
        logger.error(f"Auth check error: {e}")
        return {
            "authenticated": False,
            "role": None,
            "auth_enabled": auth_middleware.enable_auth,
            "error": "Authentication check failed",
        }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="check_permission",
    error_code_prefix="AUTH",
)
@router.get("/permissions/{operation}")
async def check_permission(request: Request, operation: str):
    """
    Check if current user has permission for specific operation
    """
    try:
        has_permission, user_data = auth_middleware.check_file_permissions(
            request, operation
        )

        return {
            "permitted": has_permission,
            "operation": operation,
            "user_role": user_data["role"] if user_data else None,
            "username": user_data["username"] if user_data else None,
        }

    except Exception as e:
        logger.error(f"Permission check error for operation {operation}: {e}")
        return {
            "permitted": False,
            "operation": operation,
            "error": "Permission check failed",
        }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="change_password",
    error_code_prefix="AUTH",
)
@router.post("/change-password")
async def change_password(request: Request, old_password: str, new_password: str):
    """
    Change user password (placeholder - implement based on user store)
    """
    # This would require a persistent user store to implement properly
    # For now, return not implemented
    raise HTTPException(
        status_code=501,
        detail="Password change not implemented - requires persistent user store",
    )
