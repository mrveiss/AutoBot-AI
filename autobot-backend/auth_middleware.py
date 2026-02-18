# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Enhanced Authentication Middleware for AutoBot
Provides JWT-based authentication, session management, and role-based access control
"""

import datetime
import json
import logging
import os
import secrets
from typing import Dict, Optional, Tuple

import bcrypt
import jwt
from backend.utils.catalog_http_exceptions import raise_auth_error
from config import UnifiedConfigManager
from fastapi import Request
from security_layer import SecurityLayer

logger = logging.getLogger(__name__)

# Create singleton config instance
config = UnifiedConfigManager()


class AuthenticationMiddleware:
    def __init__(self):
        """Initialize authentication middleware with security config and sessions."""
        self.security_layer = SecurityLayer()
        self.security_config = config.get("security_config", {})
        self.enable_auth = self.security_config.get("enable_auth", True)
        self.jwt_secret = self._get_jwt_secret()
        self.jwt_algorithm = "HS256"
        self.jwt_expiry_hours = 24
        self.session_timeout_minutes = self.security_config.get(
            "session_timeout_minutes", 30
        )
        self.max_failed_attempts = self.security_config.get("max_failed_attempts", 3)
        self.lockout_duration_minutes = self.security_config.get(
            "lockout_duration_minutes", 15
        )

        # Use Redis for session storage if available, fallback to in-memory
        self.redis_client = None
        self._init_session_storage()

        # Fallback in-memory stores (used when Redis unavailable)
        self.active_sessions: Dict[str, dict] = {}
        self.failed_attempts: Dict[str, dict] = {}

        logger.info(
            f"AuthenticationMiddleware initialized. Auth enabled: {self.enable_auth}"
        )

    def _init_session_storage(self):
        """Initialize Redis session storage using centralized client management"""
        try:
            redis_config = config.get_redis_config()
            if redis_config["enabled"]:
                from autobot_shared.redis_client import get_redis_client

                # Use sessions database for authentication sessions
                # REFACTORED: Use centralized Redis client management
                self.redis_client = get_redis_client(
                    database="sessions", async_client=False
                )
                # Test connection
                self.redis_client.ping()
                logger.info(
                    "Redis session storage initialized with centralized client management"
                )
        except Exception as e:
            logger.warning(
                f"Failed to initialize Redis session storage, using in-memory: {e}"
            )
            self.redis_client = None

    def _get_jwt_secret(self) -> str:
        """Generate or retrieve JWT secret key securely"""
        # Priority order: Environment variable -> Config file -> Generated secure secret

        # 1. Check environment variable first (most secure)
        secret = os.getenv("AUTOBOT_JWT_SECRET")
        if secret and len(secret) >= 32:
            return secret

        # 2. Check configuration file
        secret = self.security_config.get("jwt_secret")
        if secret and len(secret) >= 32:
            return secret

        # 3. Generate and store a secure random secret
        logger.warning("No secure JWT secret found. Generating secure random secret.")
        secure_secret = secrets.token_urlsafe(64)  # 512-bit secret

        # Store in configuration for consistency across restarts
        try:
            # Update the config in memory using the correct method
            config.set_nested("security_config.jwt_secret", secure_secret)
            logger.info("Generated and stored secure JWT secret")
            return secure_secret
        except Exception as e:
            logger.error("Failed to store JWT secret in config: %s", e)
            # Still return the secure secret even if we can't store it
            return secure_secret

    def hash_password(self, password: str) -> str:
        """Hash password using bcrypt"""
        salt = bcrypt.gensalt(rounds=12)
        return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

    def verify_password(self, password: str, hashed: str) -> bool:
        """Verify password against hash"""
        try:
            return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
        except Exception as e:
            logger.error("Password verification error: %s", e)
            return False

    def is_account_locked(self, username: str) -> bool:
        """Check if account is locked due to failed attempts"""
        if username not in self.failed_attempts:
            return False

        attempt_data = self.failed_attempts[username]
        locked_until = attempt_data.get("locked_until")

        if locked_until and datetime.datetime.now() < locked_until:
            return True

        # Clear expired lockout
        if locked_until and datetime.datetime.now() >= locked_until:
            self.failed_attempts[username] = {"count": 0, "locked_until": None}

        return False

    def record_failed_attempt(self, username: str, ip_address: str):
        """Record failed login attempt and lock account if needed"""
        if username not in self.failed_attempts:
            self.failed_attempts[username] = {"count": 0, "locked_until": None}

        self.failed_attempts[username]["count"] += 1
        self.failed_attempts[username]["last_attempt"] = datetime.datetime.now()
        self.failed_attempts[username]["ip"] = ip_address

        if self.failed_attempts[username]["count"] >= self.max_failed_attempts:
            lockout_until = datetime.datetime.now() + datetime.timedelta(
                minutes=self.lockout_duration_minutes
            )
            self.failed_attempts[username]["locked_until"] = lockout_until

            # Audit log the lockout
            self.security_layer.audit_log(
                action="account_locked",
                user=username,
                outcome="security_action",
                details={
                    "reason": "excessive_failed_attempts",
                    "failed_attempts": self.failed_attempts[username]["count"],
                    "locked_until": lockout_until.isoformat(),
                    "ip": ip_address,
                },
            )

    def clear_failed_attempts(self, username: str):
        """Clear failed attempts after successful login"""
        if username in self.failed_attempts:
            del self.failed_attempts[username]

    def _get_auth_disabled_user(self) -> Dict:
        """Issue #665: Extracted from authenticate_user to reduce function length.

        Returns default admin user dict when auth is disabled.
        """
        return {
            "username": "admin",
            "role": "admin",
            "email": "admin@autobot.local",
            "auth_disabled": True,
        }

    def _handle_locked_account(self, username: str, ip_address: str) -> None:
        """Issue #665: Extracted from authenticate_user to reduce function length.

        Handle locked account login attempt - logs and raises auth error.
        """
        self.security_layer.audit_log(
            action="login_attempt_locked_account",
            user=username,
            outcome="denied",
            details={"ip": ip_address, "reason": "account_locked"},
        )
        raise_auth_error(
            "AUTH_0001",
            "Account is temporarily locked due to excessive failed attempts",
        )

    def _handle_failed_login(self, username: str, ip_address: str, reason: str) -> None:
        """Issue #665: Extracted from authenticate_user to reduce function length.

        Record failed login attempt and audit log.
        """
        self.record_failed_attempt(username, ip_address)
        self.security_layer.audit_log(
            action="login_attempt",
            user=username,
            outcome="denied",
            details={"ip": ip_address, "reason": reason},
        )

    def _build_successful_auth_response(
        self, username: str, user_config: Dict, ip_address: str
    ) -> Dict:
        """Issue #665: Extracted from authenticate_user to reduce function length.

        Build and return successful authentication response.
        """
        self.clear_failed_attempts(username)
        user_config["last_login"] = datetime.datetime.now().isoformat()

        self.security_layer.audit_log(
            action="login_successful",
            user=username,
            outcome="success",
            details={"ip": ip_address, "role": user_config.get("role", "user")},
        )

        return {
            "username": username,
            "role": user_config.get("role", "user"),
            "email": user_config.get("email", f"{username}@autobot.local"),
            "last_login": user_config["last_login"],
        }

    def authenticate_user(
        self, username: str, password: str, ip_address: str = "unknown"
    ) -> Optional[Dict]:
        """Authenticate user with enhanced security measures.

        Returns:
            Dict with user info if successful, None if failed
        """
        if not self.enable_auth:
            return self._get_auth_disabled_user()

        if self.is_account_locked(username):
            self._handle_locked_account(username, ip_address)

        allowed_users = self.security_config.get("allowed_users", {})
        if username not in allowed_users:
            self._handle_failed_login(username, ip_address, "user_not_found")
            return None

        user_config = allowed_users[username]
        if not self.verify_password(password, user_config.get("password_hash", "")):
            self._handle_failed_login(username, ip_address, "invalid_password")
            return None

        return self._build_successful_auth_response(username, user_config, ip_address)

    def create_jwt_token(self, user_data: Dict) -> str:
        """Create JWT token for authenticated user."""
        payload = {
            "username": user_data["username"],
            "role": user_data["role"],
            "email": user_data.get("email", ""),
            "iat": datetime.datetime.utcnow(),
            "exp": (
                datetime.datetime.utcnow()
                + datetime.timedelta(hours=self.jwt_expiry_hours)
            ),
        }

        # Issue #684: Include org/user hierarchy in token
        if user_data.get("user_id"):
            payload["user_id"] = str(user_data["user_id"])
        if user_data.get("org_id"):
            payload["org_id"] = str(user_data["org_id"])

        return jwt.encode(payload, self.jwt_secret, algorithm=self.jwt_algorithm)

    def verify_jwt_token(self, token: str) -> Optional[Dict]:
        """Verify and decode JWT token"""
        try:
            payload = jwt.decode(
                token, self.jwt_secret, algorithms=[self.jwt_algorithm]
            )

            # Check if user still exists and is active
            username = payload.get("username")
            if username and self.is_account_locked(username):
                return None

            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("JWT token expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning("Invalid JWT token: %s", e)
            return None

    def create_session(self, user_data: Dict, request: Request) -> str:
        """Create authenticated session with Redis persistence"""
        # Generate secure session ID
        session_id = secrets.token_urlsafe(32)

        session_data = {
            "user_data": user_data,
            "created_at": datetime.datetime.now().isoformat(),
            "last_activity": datetime.datetime.now().isoformat(),
            "ip_address": request.client.host if request.client else "unknown",
            "user_agent": request.headers.get("User-Agent", "unknown"),
        }

        # Store in Redis if available, otherwise in-memory
        if self.redis_client:
            try:
                session_key = f"session:{session_id}"
                self.redis_client.setex(
                    session_key,
                    self.session_timeout_minutes * 60,  # TTL in seconds
                    json.dumps(session_data, default=str),
                )
                logger.debug("Session %s... stored in Redis", session_id[:8])
            except Exception as e:
                logger.warning("Failed to store session in Redis: %s", e)
                # Fallback to in-memory
                self.active_sessions[session_id] = session_data
        else:
            self.active_sessions[session_id] = session_data

        return session_id

    def get_session(self, session_id: str) -> Optional[Dict]:
        """Get active session data from Redis or in-memory store"""
        # Try Redis first
        if self.redis_client:
            try:
                session_key = f"session:{session_id}"
                session_data = self.redis_client.get(session_key)
                if session_data:
                    session = json.loads(session_data)
                    # Update last activity and extend TTL
                    session["last_activity"] = datetime.datetime.now().isoformat()
                    self.redis_client.setex(
                        session_key,
                        self.session_timeout_minutes * 60,
                        json.dumps(session, default=str),
                    )
                    return session
            except Exception as e:
                logger.warning("Failed to get session from Redis: %s", e)

        # Fallback to in-memory
        if session_id not in self.active_sessions:
            return None

        session = self.active_sessions[session_id]

        # Check session timeout for in-memory sessions
        last_activity = session.get("last_activity")
        if isinstance(last_activity, str):
            last_activity = datetime.datetime.fromisoformat(last_activity)

        if datetime.datetime.now() - last_activity > datetime.timedelta(
            minutes=self.session_timeout_minutes
        ):
            del self.active_sessions[session_id]
            return None

        # Update last activity
        session["last_activity"] = datetime.datetime.now().isoformat()
        return session

    def invalidate_session(self, session_id: str):
        """Invalidate/logout session from Redis and in-memory"""
        user_data = {}

        # Remove from Redis if available
        if self.redis_client:
            try:
                session_key = f"session:{session_id}"
                session_data = self.redis_client.get(session_key)
                if session_data:
                    session = json.loads(session_data)
                    user_data = session.get("user_data", {})
                    self.redis_client.delete(session_key)
                    logger.debug("Session %s... removed from Redis", session_id[:8])
            except Exception as e:
                logger.warning("Failed to remove session from Redis: %s", e)

        # Remove from in-memory store
        if session_id in self.active_sessions:
            if not user_data:  # If we didn't get user data from Redis
                user_data = self.active_sessions[session_id].get("user_data", {})
            del self.active_sessions[session_id]

        self.security_layer.audit_log(
            action="logout",
            user=user_data.get("username", "unknown"),
            outcome="success",
            details={"session_id": session_id[:16] + "..."},  # Partial ID for audit
        )

    def _extract_user_from_jwt(self, request: Request) -> Optional[Dict]:
        """
        Extract user from JWT token in Authorization header.

        Returns user dict if valid JWT found, None otherwise.
        Issue #620, #684: Includes org hierarchy context.
        """
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return None

        token = auth_header.split(" ")[1]
        token_data = self.verify_jwt_token(token)
        if not token_data:
            return None

        user = {
            "username": token_data["username"],
            "role": token_data["role"],
            "email": token_data.get("email", ""),
            "auth_method": "jwt",
        }

        # Issue #684: Include org hierarchy from token
        if token_data.get("user_id"):
            user["user_id"] = token_data["user_id"]
        if token_data.get("org_id"):
            user["org_id"] = token_data["org_id"]

        return user

    def _extract_user_from_session(self, request: Request) -> Optional[Dict]:
        """
        Extract user from session ID in header.

        Returns user dict if valid session found, None otherwise.
        Issue #620.
        """
        session_id = request.headers.get("X-Session-ID")
        if not session_id:
            return None

        session = self.get_session(session_id)
        if not session or not session.get("user_data"):
            return None

        user_data = session["user_data"].copy()
        user_data["auth_method"] = "session"
        return user_data

    def _extract_user_from_dev_header(self, request: Request) -> Optional[Dict]:
        """
        Extract user from development mode X-User-Role header.

        Only works when debug mode is enabled.
        Issue #620.
        """
        dev_mode = config.get("development.debug", False)
        if not dev_mode:
            return None

        user_role = request.headers.get("X-User-Role")
        if not user_role:
            return None

        return {
            "username": f"dev_{user_role}",
            "role": user_role,
            "email": f"dev_{user_role}@autobot.local",
            "auth_method": "development",
        }

    def get_user_from_request(self, request: Request) -> Optional[Dict]:
        """
        Extract and validate user from request using multiple authentication methods.

        Priority: JWT token -> Session ID -> Development mode header.
        Issue #620.
        """
        if not self.enable_auth:
            return self._get_auth_disabled_user()

        # Try authentication methods in priority order
        user = self._extract_user_from_jwt(request)
        if user:
            return user

        user = self._extract_user_from_session(request)
        if user:
            return user

        user = self._extract_user_from_dev_header(request)
        if user:
            return user

        # Issue #756: Security hardening - no guest fallback
        logger.debug("No valid authentication found, denying access")
        return None

    def _log_file_access_denied(
        self,
        username: str,
        operation: str,
        user_role: str,
        user_data: Dict,
        request: Request,
        ip_address: str,
    ) -> None:
        """
        Log denied file access with comprehensive audit details.

        Args:
            username: Username attempting access
            operation: File operation attempted
            user_role: Role of the user
            user_data: User data dictionary
            request: FastAPI request object
            ip_address: Client IP address

        Issue #620.
        """
        self.security_layer.audit_log(
            action="file_access_denied",
            user=username,
            outcome="denied",
            details={
                "operation": operation,
                "permission_required": f"files.{operation}",
                "user_role": user_role,
                "auth_method": user_data.get("auth_method", "unknown"),
                "user_agent": request.headers.get("User-Agent", "unknown"),
                "ip": ip_address,
                "timestamp": datetime.datetime.now().isoformat(),
                "request_path": (
                    str(request.url.path) if hasattr(request, "url") else "unknown"
                ),
            },
        )

    def _log_file_access_granted(
        self,
        username: str,
        operation: str,
        user_role: str,
        user_data: Dict,
        ip_address: str,
    ) -> None:
        """
        Log successful file access with audit details.

        Args:
            username: Username granted access
            operation: File operation granted
            user_role: Role of the user
            user_data: User data dictionary
            ip_address: Client IP address

        Issue #620.
        """
        self.security_layer.audit_log(
            action="file_access_granted",
            user=username,
            outcome="success",
            details={
                "operation": operation,
                "user_role": user_role,
                "auth_method": user_data.get("auth_method", "unknown"),
                "ip": ip_address,
            },
        )

    def check_file_permissions(
        self, request: Request, operation: str
    ) -> Tuple[bool, Optional[Dict]]:
        """
        Enhanced permission checking with comprehensive security measures.

        Issue #620: Refactored to use helper methods for audit logging.

        Returns:
            Tuple of (permission_granted: bool, user_data: Dict)
        """
        try:
            user_data = self.get_user_from_request(request)
            if not user_data:
                return False, None

            user_role = user_data["role"]
            username = user_data["username"]
            ip_address = request.client.host if request.client else "unknown"

            has_permission = self.security_layer.check_permission(
                user_role=user_role,
                action_type=f"files.{operation}",
                resource=f"file_operation:{operation}",
            )

            if not has_permission:
                self._log_file_access_denied(
                    username, operation, user_role, user_data, request, ip_address
                )
                return False, user_data

            self._log_file_access_granted(
                username, operation, user_role, user_data, ip_address
            )
            return True, user_data

        except Exception as e:
            logger.error(
                f"Error checking file permissions for operation '{operation}': {e}"
            )
            return False, None


# Global authentication middleware instance
auth_middleware = AuthenticationMiddleware()


def get_current_user(request: Request) -> Dict:
    """
    Dependency for FastAPI endpoints to get current authenticated user
    Raises HTTPException if authentication fails
    """
    user_data = auth_middleware.get_user_from_request(request)
    if not user_data:
        raise_auth_error("AUTH_0002", "Authentication required")
    return user_data


def require_file_permission(operation: str):
    """
    Decorator factory for file operations requiring specific permissions
    """

    def decorator(func):
        """Wrap function with permission check for the specified operation."""

        async def wrapper(request: Request, *args, **kwargs):
            """Check permission and execute function with user in request state."""
            has_permission, user_data = auth_middleware.check_file_permissions(
                request, operation
            )
            if not has_permission:
                raise_auth_error(
                    "AUTH_0003",
                    f"Insufficient permissions for file {operation} operation",
                )
            # Add user data to request state for use in endpoint
            request.state.user = user_data
            return await func(request, *args, **kwargs)

        return wrapper

    return decorator


def check_admin_permission(request: Request) -> bool:
    """
    FastAPI dependency to check if user has admin permission.

    Use as: Depends(check_admin_permission)

    Args:
        request: FastAPI Request object

    Returns:
        True if user has admin role

    Raises:
        HTTPException: 401 if not authenticated, 403 if not admin
    """
    # Check for single user mode - bypass auth and grant admin access
    from user_management.config import DeploymentMode, get_deployment_config

    deployment_config = get_deployment_config()
    if deployment_config.mode == DeploymentMode.SINGLE_USER:
        # In single user mode, all requests are treated as admin
        logger.debug("Single user mode: granting admin access")
        return True

    user_data = auth_middleware.get_user_from_request(request)

    if not user_data:
        raise_auth_error("AUTH_0002", "Authentication required")

    # Issue #744: Require explicit role - no guest fallback for security
    user_role = user_data.get("role")
    if not user_role:
        raise_auth_error("AUTH_0002", "User role not assigned - access denied")
    if user_role != "admin":
        raise_auth_error("AUTH_0003", "Admin permission required for this operation")

    return True
