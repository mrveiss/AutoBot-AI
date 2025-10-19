"""
Enhanced Authentication Middleware for AutoBot
Provides JWT-based authentication, session management, and role-based access control
"""

import datetime
import hashlib
import hmac
import json
import logging
import os
import secrets
from typing import Dict, Optional, Tuple

import bcrypt
import jwt
from fastapi import HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.unified_config import config
from src.security_layer import SecurityLayer
from src.constants.network_constants import NetworkConstants

logger = logging.getLogger(__name__)


class AuthenticationMiddleware:
    def __init__(self):
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
        """Initialize Redis session storage using standardized pool manager"""
        try:
            redis_config = config.get_redis_config()
            if redis_config["enabled"]:
                from src.redis_pool_manager import get_redis_sync

                # Use sessions database for authentication sessions
                self.redis_client = get_redis_sync("sessions")
                # Test connection
                self.redis_client.ping()
                logger.info("Redis session storage initialized with pool manager")
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
            logger.error(f"Failed to store JWT secret in config: {e}")
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
            logger.error(f"Password verification error: {e}")
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

    def authenticate_user(
        self, username: str, password: str, ip_address: str = "unknown"
    ) -> Optional[Dict]:
        """
        Authenticate user with enhanced security measures

        Returns:
            Dict with user info if successful, None if failed
        """
        if not self.enable_auth:
            # Return default admin user when auth is disabled
            return {
                "username": "admin",
                "role": "admin",
                "email": "admin@autobot.local",
                "auth_disabled": True,
            }

        # Check if account is locked
        if self.is_account_locked(username):
            self.security_layer.audit_log(
                action="login_attempt_locked_account",
                user=username,
                outcome="denied",
                details={"ip": ip_address, "reason": "account_locked"},
            )
            raise HTTPException(
                status_code=423,
                detail="Account is temporarily locked due to excessive failed attempts",
            )

        # Get user from configuration
        allowed_users = self.security_config.get("allowed_users", {})
        if username not in allowed_users:
            self.record_failed_attempt(username, ip_address)
            self.security_layer.audit_log(
                action="login_attempt",
                user=username,
                outcome="denied",
                details={"ip": ip_address, "reason": "user_not_found"},
            )
            return None

        user_config = allowed_users[username]
        password_hash = user_config.get("password_hash", "")

        # Verify password
        if not self.verify_password(password, password_hash):
            self.record_failed_attempt(username, ip_address)
            self.security_layer.audit_log(
                action="login_attempt",
                user=username,
                outcome="denied",
                details={"ip": ip_address, "reason": "invalid_password"},
            )
            return None

        # Clear failed attempts on successful login
        self.clear_failed_attempts(username)

        # Update last login time (in production, persist this to database)
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

    def create_jwt_token(self, user_data: Dict) -> str:
        """Create JWT token for authenticated user"""
        payload = {
            "username": user_data["username"],
            "role": user_data["role"],
            "email": user_data.get("email", ""),
            "iat": datetime.datetime.utcnow(),
            "exp": datetime.datetime.utcnow()
            + datetime.timedelta(hours=self.jwt_expiry_hours),
        }

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
            logger.warning(f"Invalid JWT token: {e}")
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
                logger.debug(f"Session {session_id[:8]}... stored in Redis")
            except Exception as e:
                logger.warning(f"Failed to store session in Redis: {e}")
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
                logger.warning(f"Failed to get session from Redis: {e}")

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
                    logger.debug(f"Session {session_id[:8]}... removed from Redis")
            except Exception as e:
                logger.warning(f"Failed to remove session from Redis: {e}")

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

    def get_user_from_request(self, request: Request) -> Optional[Dict]:
        """
        Extract and validate user from request using multiple authentication methods

        Priority:
        1. JWT token in Authorization header
        2. Session ID in header
        3. Development mode header (X-User-Role)
        4. Default guest access
        """
        if not self.enable_auth:
            return {
                "username": "admin",
                "role": "admin",
                "email": "admin@autobot.local",
                "auth_disabled": True,
            }

        # Method 1: JWT Token Authentication
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            token_data = self.verify_jwt_token(token)
            if token_data:
                return {
                    "username": token_data["username"],
                    "role": token_data["role"],
                    "email": token_data.get("email", ""),
                    "auth_method": "jwt",
                }

        # Method 2: Session ID Authentication
        session_id = request.headers.get("X-Session-ID")
        if session_id:
            session = self.get_session(session_id)
            if session and session.get("user_data"):
                user_data = session["user_data"].copy()
                user_data["auth_method"] = "session"
                return user_data

        # Method 3: Development Mode (X-User-Role header)
        dev_mode = config.get("development.debug", False)
        if dev_mode:
            user_role = request.headers.get("X-User-Role", "guest")
            return {
                "username": f"dev_{user_role}",
                "role": user_role,
                "email": f"dev_{user_role}@autobot.local",
                "auth_method": "development",
            }

        # Method 4: Default guest access
        return {
            "username": "guest",
            "role": "guest",
            "email": "guest@autobot.local",
            "auth_method": "guest",
        }

    def check_file_permissions(
        self, request: Request, operation: str
    ) -> Tuple[bool, Optional[Dict]]:
        """
        Enhanced permission checking with comprehensive security measures

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

            # Check permission using SecurityLayer
            has_permission = self.security_layer.check_permission(
                user_role=user_role,
                action_type=f"files.{operation}",
                resource=f"file_operation:{operation}",
            )

            if not has_permission:
                # Enhanced audit logging for denied access
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
                            str(request.url.path)
                            if hasattr(request, "url")
                            else "unknown"
                        ),
                    },
                )
                return False, user_data

            # Log successful access
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

            return True, user_data

        except Exception as e:
            logger.error(
                f"Error checking file permissions for operation '{operation}': {e}"
            )
            # Fail secure - deny access on error
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
        raise HTTPException(status_code=401, detail="Authentication required")
    return user_data


def require_file_permission(operation: str):
    """
    Decorator factory for file operations requiring specific permissions
    """

    def decorator(func):
        async def wrapper(request: Request, *args, **kwargs):
            has_permission, user_data = auth_middleware.check_file_permissions(
                request, operation
            )
            if not has_permission:
                raise HTTPException(
                    status_code=403,
                    detail=f"Insufficient permissions for file {operation} operation",
                )
            # Add user data to request state for use in endpoint
            request.state.user = user_data
            return await func(request, *args, **kwargs)

        return wrapper

    return decorator
