# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Enhanced Authentication Middleware for AutoBot
Provides JWT-based authentication, session management, and role-based access control
"""

import datetime
import json
import secrets
from datetime import timezone
from typing import Dict, Tuple

from fastapi import HTTPException, Request, status

from autobot_shared.auth.jwt_core import (
    decode_jwt_or_none,
    encode_jwt,
    hash_password,
    verify_password,
)
from autobot_shared.logging_manager import get_logger
from autobot_shared.singleton_factory import lazy_singleton
from autobot_shared.ssot_config import config as ssot_config
from autobot_shared.time_utils import parse_utc_iso
from config.manager import get_config_manager
from security_layer import SecurityLayer
from utils.catalog_http_exceptions import raise_auth_error

logger = get_logger(__name__)

config = get_config_manager()


class AuthenticationMiddleware:
    def __init__(self):
        """Initialize authentication middleware with security config and sessions."""
        self.security_layer = SecurityLayer()
        self.security_config = config.get("security_config", {})
        self.enable_auth = self.security_config.get("enable_auth", True)
        self.jwt_secret = self._get_jwt_secret()
        self.jwt_expiry_hours = 24
        self.session_timeout_minutes = self.security_config.get("session_timeout_minutes", 30)
        self.max_failed_attempts = self.security_config.get("max_failed_attempts", 3)
        self.lockout_duration_minutes = self.security_config.get("lockout_duration_minutes", 15)

        # Use Redis for session storage if available, fallback to in-memory
        self.redis_client = None
        self._init_session_storage()

        # Fallback in-memory stores (used when Redis unavailable)
        self.active_sessions: Dict[str, dict] = {}
        self.failed_attempts: Dict[str, dict] = {}

        logger.info(f"AuthenticationMiddleware initialized. Auth enabled: {self.enable_auth}")

    def _init_session_storage(self):
        """Initialize Redis session storage using centralized client management"""
        try:
            if ssot_config.redis.enabled:
                from autobot_shared.redis_client import get_redis_client

                # Use sessions database for authentication sessions
                # REFACTORED: Use centralized Redis client management
                self.redis_client = get_redis_client(database="sessions", async_client=False)
                # Test connection
                self.redis_client.ping()
                logger.info("Redis session storage initialized with centralized client management")
        except Exception as e:
            logger.warning(f"Failed to initialize Redis session storage, using in-memory: {e}")
            self.redis_client = None

    def _get_jwt_secret(self) -> str:
        """Generate or retrieve JWT secret key securely"""
        # Priority order: AUTOBOT_JWT_SECRET -> SECRET_KEY -> Config file -> Generated secret

        # 1. Check dedicated JWT secret env var first (most specific)
        secret = config.jwt_secret
        if secret:
            return secret

        # 2. Fall back to SECRET_KEY env var (stable across restarts)
        secret = config.secret_key
        if secret:
            return secret

        # 3. Check configuration file
        secret = self.security_config.get("jwt_secret")
        if secret and len(secret) >= 32:
            return secret

        # 3. Generate and store a secure random secret
        logger.warning(  # codeql[py/clear-text-logging-sensitive-data]
            "No secure JWT secret found. Generating secure random secret."
        )
        secure_secret = secrets.token_urlsafe(64)  # 512-bit secret

        # Store in configuration for consistency across restarts
        try:
            # Update the config in memory using the correct method
            config.set_nested("security_config.jwt_secret", secure_secret)
            logger.info("Generated and stored secure JWT secret")  # noqa: codeql[py/clear-text-logging-sensitive-data]
            return secure_secret
        except Exception as e:
            # codeql[py/clear-text-logging-sensitive-data]
            logger.error("Failed to store JWT secret in config: %s", e)
            # Still return the secure secret even if we can't store it
            return secure_secret

    def hash_password(self, password: str) -> str:
        """Hash password using bcrypt."""
        return hash_password(password)

    def verify_password(self, password: str, hashed: str) -> bool:
        """Verify password against hash."""
        return verify_password(password, hashed)

    def is_account_locked(self, username: str) -> bool:
        """Check if account is locked due to failed attempts"""
        if username not in self.failed_attempts:
            return False

        attempt_data = self.failed_attempts[username]
        locked_until = attempt_data.get("locked_until")

        if locked_until and datetime.datetime.now(tz=timezone.utc) < locked_until:
            return True

        # Clear expired lockout
        if locked_until and datetime.datetime.now(tz=timezone.utc) >= locked_until:
            self.failed_attempts[username] = {"count": 0, "locked_until": None}

        return False

    def record_failed_attempt(self, username: str, ip_address: str):
        """Record failed login attempt and lock account if needed"""
        if username not in self.failed_attempts:
            self.failed_attempts[username] = {"count": 0, "locked_until": None}

        self.failed_attempts[username]["count"] += 1
        self.failed_attempts[username]["last_attempt"] = datetime.datetime.now(tz=timezone.utc)
        self.failed_attempts[username]["ip"] = ip_address

        if self.failed_attempts[username]["count"] >= self.max_failed_attempts:
            lockout_until = datetime.datetime.now(tz=timezone.utc) + datetime.timedelta(
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
            "email": f"admin@{ssot_config.auth.domain}",
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

    def _build_successful_auth_response(self, username: str, user_config: Dict, ip_address: str) -> Dict:
        """Issue #665: Extracted from authenticate_user to reduce function length.

        Build and return successful authentication response.
        """
        self.clear_failed_attempts(username)
        user_config["last_login"] = datetime.datetime.now(tz=timezone.utc).isoformat()

        self.security_layer.audit_log(
            action="login_successful",
            user=username,
            outcome="success",
            details={"ip": ip_address, "role": user_config.get("role", "user")},
        )

        return {
            "username": username,
            "role": user_config.get("role", "user"),
            "email": user_config.get("email", f"{username}@{ssot_config.auth.domain}"),
            "last_login": user_config["last_login"],
        }

    def authenticate_user(self, username: str, password: str, ip_address: str = "unknown") -> Dict | None:
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
            "iat": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
        }

        # Issue #684: Include org/user hierarchy in token
        if user_data.get("user_id"):
            payload["user_id"] = str(user_data["user_id"])
        if user_data.get("org_id"):
            payload["org_id"] = str(user_data["org_id"])

        return encode_jwt(payload, secret=self.jwt_secret, expiry_hours=self.jwt_expiry_hours)

    def verify_jwt_token(self, token: str) -> Dict | None:
        """Verify and decode JWT token."""
        payload = decode_jwt_or_none(token, self.jwt_secret)
        if payload is None:
            return None

        # Check if user is locked out even when token is structurally valid
        username = payload.get("username")
        if username and self.is_account_locked(username):
            return None

        return payload

    def create_session(self, user_data: Dict, request: Request) -> str:
        """Create authenticated session with Redis persistence"""
        # Generate secure session ID
        session_id = secrets.token_urlsafe(32)

        session_data = {
            "user_data": user_data,
            "created_at": datetime.datetime.now(tz=timezone.utc).isoformat(),
            "last_activity": datetime.datetime.now(tz=timezone.utc).isoformat(),
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

    def get_session(self, session_id: str) -> Dict | None:
        """Get active session data from Redis or in-memory store"""
        # Try Redis first
        if self.redis_client:
            try:
                session_key = f"session:{session_id}"
                session_data = self.redis_client.get(session_key)
                if session_data:
                    session = json.loads(session_data)
                    # Update last activity and extend TTL
                    session["last_activity"] = datetime.datetime.now(tz=timezone.utc).isoformat()
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
            last_activity = parse_utc_iso(last_activity)
            if last_activity.tzinfo is None:
                last_activity = last_activity.replace(tzinfo=datetime.timezone.utc)

        if datetime.datetime.now(tz=timezone.utc) - last_activity > datetime.timedelta(
            minutes=self.session_timeout_minutes
        ):
            del self.active_sessions[session_id]
            return None

        # Update last activity
        session["last_activity"] = datetime.datetime.now(tz=timezone.utc).isoformat()
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

    def _extract_user_from_jwt(self, request: Request) -> Dict | None:
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

    def _extract_user_from_session(self, request: Request) -> Dict | None:
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

    def _extract_user_from_dev_header(self, request: Request) -> Dict | None:
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
            "email": f"dev_{user_role}@{ssot_config.auth.domain}",
            "auth_method": "development",
        }

    async def _extract_user_from_run_jwt(self, request: Request) -> Dict | None:
        """Try to authenticate the request with a run-scoped JWT (SEC-2 #6473).

        Called as a fallback when user-JWT and session auth both fail.
        Uses the run JWT secret (separate from the user JWT secret) so
        forged tokens from one domain cannot authenticate in the other.

        Scope validation is intentionally NOT enforced here — the run JWT
        proves identity; individual endpoints apply scope checks if needed.

        Returns:
            Synthetic user dict with ``auth_method="run_jwt"`` on success,
            or ``None`` if the Bearer token is absent or not a valid run JWT.
        """
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return None

        token = auth_header.split(" ", 1)[1]
        try:
            from services.run_jwt import validate_run_jwt

            claims = await validate_run_jwt(token)
        except Exception:
            return None

        run_id = str(claims.get("run_id", ""))
        agent_id = str(claims.get("agent_id", ""))
        return {
            "username": f"run:{run_id}",
            "role": "run_jwt",
            "run_id": run_id,
            "agent_id": agent_id,
            "scope": list(claims.get("scope", [])),
            "auth_method": "run_jwt",
        }

    def get_user_from_request(self, request: Request) -> Dict | None:
        """
        Extract and validate user from request using multiple authentication methods.

        Priority: JWT token -> Session ID -> Development mode header.
        Issue #620, #960.
        """
        if not self.enable_auth:
            return self._get_auth_disabled_user()

        # Single-user mode: bypass auth (mirrors check_admin_permission behavior)
        try:
            from user_management.config import DeploymentMode, get_deployment_config

            deployment_config = get_deployment_config()
            if deployment_config.mode == DeploymentMode.SINGLE_USER:
                return self._get_auth_disabled_user()
        except Exception:
            logger.debug("Suppressed exception in try block", exc_info=True)

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
                "timestamp": datetime.datetime.now(tz=timezone.utc).isoformat(),
                "request_path": (str(request.url.path) if hasattr(request, "url") else "unknown"),
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

    def check_file_permissions(self, request: Request, operation: str) -> Tuple[bool, Dict | None]:
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
                self._log_file_access_denied(username, operation, user_role, user_data, request, ip_address)
                return False, user_data

            self._log_file_access_granted(username, operation, user_role, user_data, ip_address)
            return True, user_data

        except Exception as e:
            logger.error(f"Error checking file permissions for operation '{operation}': {e}")
            return False, None


get_auth_middleware = lazy_singleton(AuthenticationMiddleware)


async def get_current_user(request: Request) -> Dict:
    """
    Dependency for FastAPI endpoints to get current authenticated user.

    Issue #1779: Also accepts X-Internal-API-Key header for
    service-to-service calls (e.g. SLM frontend via nginx proxy).
    Returns a synthetic admin user dict when the internal key matches.

    SEC-2 #6473: Also accepts a run-scoped JWT (``Bearer <run-jwt>``) so
    MCP bridge workers and long-running tasks can authenticate without a
    full user session.  Scope enforcement is left to individual endpoints.

    Raises HTTPException if authentication fails.
    """
    # Issue #1779: Allow trusted internal services via API key
    _internal_key = config.misc.internal_api_key
    if _internal_key and request.headers.get("X-Internal-API-Key") == _internal_key:
        return {"username": "service:slm", "role": "admin", "service": True}

    middleware = get_auth_middleware()

    # Primary: user JWT / session / dev-header auth (sync, no Redis needed)
    user_data = middleware.get_user_from_request(request)
    if user_data:
        return user_data

    # Fallback: run-scoped JWT — async because it hits the Redis denylist.
    # SEC-2 #6473: run JWTs are valid ONLY on the refresh endpoint and MCP
    # bridge routes. Presenting a run JWT to any other REST endpoint returns
    # 403 so a scoped token cannot reach chat/knowledge/LLM write paths.
    run_user = await middleware._extract_user_from_run_jwt(request)
    if run_user:
        _RUN_JWT_ALLOWED_PREFIXES = ("/api/runs/", "/api/mcp/")
        if not any(request.url.path.startswith(p) for p in _RUN_JWT_ALLOWED_PREFIXES):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Run JWT not permitted on this endpoint",
            )
        return run_user

    raise_auth_error("AUTH_0002", "Authentication required")


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
    # Issue #1145: Allow trusted internal services (e.g. SLM backend) via API key.
    # The key is set via AUTOBOT_INTERNAL_API_KEY env var on both services.
    _internal_key = config.misc.internal_api_key
    if _internal_key and request.headers.get("X-Internal-API-Key") == _internal_key:
        logger.debug("Internal API key auth: granting admin access")
        return True

    # Check for single user mode - bypass auth and grant admin access
    from user_management.config import DeploymentMode, get_deployment_config

    deployment_config = get_deployment_config()
    if deployment_config.mode == DeploymentMode.SINGLE_USER:
        # In single user mode, all requests are treated as admin
        logger.debug("Single user mode: granting admin access")
        return True

    user_data = get_auth_middleware().get_user_from_request(request)

    if not user_data:
        raise_auth_error("AUTH_0002", "Authentication required")

    # Issue #744: Require explicit role - no guest fallback for security
    user_role = user_data.get("role")
    if not user_role:
        raise_auth_error("AUTH_0002", "User role not assigned - access denied")
    if user_role != "admin":
        raise_auth_error("AUTH_0003", "Admin permission required for this operation")

    return True


async def authenticate_websocket(websocket) -> dict | None:
    """Authenticate a WebSocket connection.

    Checks for JWT token in query params. Falls back to synthetic admin
    in single-user mode (mirrors get_user_from_request single-user bypass).
    Returns None if unauthenticated.

    Issue #2818: Add auth before websocket.accept() to reject unauthenticated
    connections at the protocol handshake level.

    Args:
        websocket: FastAPI WebSocket instance.

    Returns:
        User dict or None if authentication fails.
    """
    # Check query param token
    token = websocket.query_params.get("token")
    if token:
        try:
            auth = AuthenticationMiddleware()
            token_data = auth.verify_jwt_token(token)
            if token_data:
                result = {
                    "username": token_data["username"],
                    "role": token_data["role"],
                    "email": token_data.get("email", ""),
                    "auth_method": "jwt_websocket",
                }
                if token_data.get("user_id") is not None:
                    result["user_id"] = token_data["user_id"]
                if token_data.get("org_id") is not None:
                    result["org_id"] = token_data["org_id"]
                return result
        except Exception:
            logger.warning("WebSocket JWT authentication failed")
            return None

    # Single-user mode bypass — same logic as get_user_from_request
    try:
        from user_management.config import DeploymentMode, get_deployment_config

        deployment_config = get_deployment_config()
        if deployment_config.mode == DeploymentMode.SINGLE_USER:
            return {
                "username": "admin",
                "role": "admin",
                "email": f"admin@{ssot_config.auth.domain}",
                "source": "single_user_mode",
            }
    except Exception:
        logger.debug("Suppressed exception in single-user mode check", exc_info=True)

    return None
