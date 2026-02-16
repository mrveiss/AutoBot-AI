# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Authentication API endpoints for AutoBot
Provides login, logout, and session management functionality
"""

import datetime
import logging
from collections import defaultdict
from time import time
from typing import Dict, List, Optional

import jwt as pyjwt
from auth_middleware import auth_middleware
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, validator

from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from backend.user_management.database import db_session_context
from backend.user_management.services.user_service import UserService

router = APIRouter()
logger = logging.getLogger(__name__)


# Rate limiting for password change endpoint (stricter limits for security)
PASSWORD_CHANGE_RATE_WINDOW = 300  # 5 minutes
PASSWORD_CHANGE_MAX_ATTEMPTS = 5  # max attempts per window


async def _enrich_user_with_org_context(user_data: Dict) -> Dict:
    """Look up user in PostgreSQL to get user_id and org_id.

    Enriches the auth response with organizational hierarchy context.
    Non-critical: gracefully degrades if DB lookup fails.

    Helper for login (#684).
    """
    try:
        async with db_session_context() as session:
            user_service = UserService(session)
            db_user = await user_service.get_user_by_username(user_data["username"])
            if db_user:
                user_data["user_id"] = str(db_user.id)
                if db_user.org_id:
                    user_data["org_id"] = str(db_user.org_id)
    except Exception as e:
        logger.debug("Could not enrich user with org context: %s", e)
    return user_data


class PasswordChangeRateLimiter:
    """Rate limiter for password change attempts to prevent brute-force attacks."""

    def __init__(
        self,
        window: int = PASSWORD_CHANGE_RATE_WINDOW,
        max_attempts: int = PASSWORD_CHANGE_MAX_ATTEMPTS,
    ):
        """Initialize rate limiter."""
        self.window = window
        self.max_attempts = max_attempts
        self.attempts: Dict[str, List[float]] = defaultdict(list)

    def is_allowed(self, client_id: str) -> bool:
        """Check if password change attempt is allowed."""
        now = time()
        # Clean old attempts
        self.attempts[client_id] = [
            t for t in self.attempts[client_id] if now - t < self.window
        ]
        # Check limit
        if len(self.attempts[client_id]) >= self.max_attempts:
            return False
        # Record attempt
        self.attempts[client_id].append(now)
        return True

    def get_remaining(self, client_id: str) -> int:
        """Get remaining attempts for client."""
        now = time()
        self.attempts[client_id] = [
            t for t in self.attempts[client_id] if now - t < self.window
        ]
        return max(0, self.max_attempts - len(self.attempts[client_id]))


# Global rate limiter for password changes
password_change_limiter = PasswordChangeRateLimiter()


class LoginRequest(BaseModel):
    """Login request model"""

    username: str
    password: str

    @validator("username")
    def validate_username(cls, v):
        """Validate and sanitize username format."""
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
        """Validate password length constraints."""
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


class ChangePasswordRequest(BaseModel):
    """Change password request model"""

    current_password: str
    new_password: str

    @validator("new_password")
    def validate_new_password(cls, v):
        """Validate password strength requirements."""
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        if len(v) > 128:
            raise ValueError("Password too long")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class ChangePasswordResponse(BaseModel):
    """Change password response model"""

    success: bool
    message: str


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

        # Authenticate user against PostgreSQL database (Issue #888)
        async with db_session_context() as session:
            user_service = UserService(session)
            user = await user_service.authenticate(
                username_or_email=login_data.username,
                password=login_data.password,
                ip_address=ip_address,
            )

            if not user:
                # Generic error message to prevent username enumeration
                raise HTTPException(
                    status_code=401, detail="Invalid username or password"
                )

            # Build user data dict for JWT token
            user_data = {
                "username": user.username,
                "user_id": str(user.id),
                "role": "admin" if user.is_platform_admin else "user",
                "email": user.email,
                "last_login": user.updated_at.isoformat() if user.updated_at else None,
            }
            if user.org_id:
                user_data["org_id"] = str(user.org_id)

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
        logger.error("Login error for user %s: %s", login_data.username, e)
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
        logger.error("Logout error: %s", e)
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
    Get current authenticated user information.

    In single_user deployment mode, returns default admin user without requiring auth.
    """
    try:
        # Check deployment mode - in single_user mode, return synthetic admin
        from user_management.config import DeploymentMode, get_deployment_config

        config = get_deployment_config()
        if config.mode == DeploymentMode.SINGLE_USER:
            return {
                "username": "admin",
                "role": "admin",
                "email": "admin@autobot.local",
                "auth_method": "single_user",
                "authenticated": True,
                "deployment_mode": "single_user",
            }

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
            "deployment_mode": config.mode.value,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting user info: %s", e)
        raise HTTPException(status_code=500, detail="Error retrieving user information")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="check_authentication",
    error_code_prefix="AUTH",
)
@router.get("/check")
async def check_authentication(request: Request):
    """
    Quick authentication check endpoint.

    In single_user mode, always returns authenticated=True.
    """
    try:
        # Check deployment mode
        from user_management.config import DeploymentMode, get_deployment_config

        config = get_deployment_config()
        if config.mode == DeploymentMode.SINGLE_USER:
            return {
                "authenticated": True,
                "role": "admin",
                "auth_enabled": False,
                "deployment_mode": "single_user",
            }

        user_data = auth_middleware.get_user_from_request(request)

        return {
            "authenticated": user_data is not None,
            "role": user_data["role"] if user_data else None,
            "auth_enabled": auth_middleware.enable_auth,
            "deployment_mode": config.mode.value,
        }

    except Exception as e:
        logger.error("Auth check error: %s", e)
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
        logger.error("Permission check error for operation %s: %s", operation, e)
        return {
            "permitted": False,
            "operation": operation,
            "error": "Permission check failed",
        }


def _check_password_change_rate_limit(username: str, ip_address: str) -> None:
    """Check rate limit for password change attempts."""
    client_id = f"{username}:{ip_address}"
    if not password_change_limiter.is_allowed(client_id):
        remaining_time = PASSWORD_CHANGE_RATE_WINDOW // 60
        auth_middleware.security_layer.audit_log(
            action="password_change_rate_limited",
            user=username,
            outcome="denied",
            details={"ip": ip_address, "reason": "rate_limit_exceeded"},
        )
        raise HTTPException(
            status_code=429,
            detail=f"Too many password change attempts. Please try again in {remaining_time} minutes.",
        )


def _verify_current_password(
    username: str, current_password: str, ip_address: str
) -> str:
    """Verify current password and return the hash. Raises HTTPException on failure."""
    allowed_users = auth_middleware.security_config.get("allowed_users", {})
    if username not in allowed_users:
        raise HTTPException(status_code=404, detail="User not found in system")

    user_config = allowed_users[username]
    current_password_hash = user_config.get("password_hash", "")

    if not auth_middleware.verify_password(current_password, current_password_hash):
        auth_middleware.security_layer.audit_log(
            action="password_change_failed",
            user=username,
            outcome="denied",
            details={"ip": ip_address, "reason": "invalid_current_password"},
        )
        raise HTTPException(status_code=401, detail="Current password is incorrect")

    return current_password_hash


def _persist_password_change(username: str, new_password_hash: str) -> None:
    """Persist password change to config file."""
    from config import UnifiedConfigManager

    # Update in-memory config
    allowed_users = auth_middleware.security_config.get("allowed_users", {})
    allowed_users[username]["password_hash"] = new_password_hash

    # Persist to disk
    config_manager = UnifiedConfigManager()
    config_manager.set_nested(
        f"security_config.allowed_users.{username}.password_hash",
        new_password_hash,
    )
    config_manager.save_settings()


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="change_password",
    error_code_prefix="AUTH",
)
@router.post("/change-password", response_model=ChangePasswordResponse)
async def change_password(request: Request, password_data: ChangePasswordRequest):
    """
    Change the current user's password.

    Requires the current password for verification before allowing the change.
    Password must meet strength requirements (8+ chars, upper/lower/digit).
    Rate limited to 5 attempts per 5 minutes.
    """
    try:
        from user_management.config import DeploymentMode, get_deployment_config

        config = get_deployment_config()
        if config.mode == DeploymentMode.SINGLE_USER:
            raise HTTPException(
                status_code=400,
                detail="Password change is not available in single-user mode",
            )

        user_data = auth_middleware.get_user_from_request(request)
        if not user_data or user_data.get("auth_method") == "guest":
            raise HTTPException(status_code=401, detail="Authentication required")

        username = user_data.get("username")
        if not username:
            raise HTTPException(status_code=401, detail="Unable to identify user")

        ip_address = request.client.host if request.client else "unknown"

        _check_password_change_rate_limit(username, ip_address)
        _verify_current_password(username, password_data.current_password, ip_address)

        new_password_hash = auth_middleware.hash_password(password_data.new_password)
        _persist_password_change(username, new_password_hash)

        auth_middleware.security_layer.audit_log(
            action="password_changed",
            user=username,
            outcome="success",
            details={"ip": ip_address},
        )
        logger.info("Password changed successfully for user: %s", username)

        return ChangePasswordResponse(
            success=True, message="Password changed successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Password change error: %s", e)
        raise HTTPException(
            status_code=500, detail="Failed to change password. Please try again."
        )


def _decode_refresh_token(token: str) -> Dict:
    """Decode JWT for refresh, allowing recently expired tokens (1h grace).

    Helper for refresh_token (#827).
    """
    try:
        payload = pyjwt.decode(
            token,
            auth_middleware.jwt_secret,
            algorithms=[auth_middleware.jwt_algorithm],
            options={"verify_exp": False},
        )
    except pyjwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc

    exp = payload.get("exp")
    if exp:
        exp_time = datetime.datetime.fromtimestamp(exp, tz=datetime.timezone.utc)
        now = datetime.datetime.now(tz=datetime.timezone.utc)
        if now > exp_time + datetime.timedelta(hours=1):
            raise HTTPException(
                status_code=401,
                detail="Token expired beyond refresh window",
            )
    return payload


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="refresh_token",
    error_code_prefix="AUTH",
)
@router.post("/refresh")
async def refresh_token(request: Request):
    """Refresh an existing JWT token before or shortly after expiry.

    Accepts a valid (or recently expired within 1h) JWT and returns
    a fresh token with a new expiry window.
    """
    from user_management.config import DeploymentMode, get_deployment_config

    config = get_deployment_config()
    if config.mode == DeploymentMode.SINGLE_USER:
        return {
            "success": True,
            "token": "single_user_mode",
            "expiresIn": 86400,
        }

    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="No token provided")

    token = auth_header.split(" ")[1]
    payload = _decode_refresh_token(token)

    user_data = {
        "username": payload["username"],
        "role": payload["role"],
        "email": payload.get("email", ""),
    }
    # Issue #684: Preserve org hierarchy across token refresh
    if payload.get("user_id"):
        user_data["user_id"] = payload["user_id"]
    if payload.get("org_id"):
        user_data["org_id"] = payload["org_id"]
    new_token = auth_middleware.create_jwt_token(user_data)
    expiry_seconds = auth_middleware.jwt_expiry_hours * 3600

    return {
        "success": True,
        "token": new_token,
        "expiresIn": expiry_seconds,
    }
