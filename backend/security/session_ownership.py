"""
Session Ownership Validation for AutoBot Chat System
Implements access control for conversation data across distributed VMs

CRITICAL SECURITY: Prevents unauthorized access to conversation data
CVSS 9.1 vulnerability fix - session ownership validation

FEATURE FLAG SUPPORT:
- DISABLED: No ownership validation (development mode)
- LOG_ONLY: Validate and audit violations, but don't block access
- ENFORCED: Full enforcement with access blocking
"""

import logging
from typing import Dict, Optional

from fastapi import HTTPException, Request

from src.auth_middleware import auth_middleware
from src.constants.network_constants import NetworkConstants

logger = logging.getLogger(__name__)


class SessionOwnershipValidator:
    """
    Validates and enforces session ownership for conversation access control.

    Supports gradual rollout with three enforcement modes:
    - DISABLED: Skip validation entirely
    - LOG_ONLY: Validate and audit, but don't block
    - ENFORCED: Full enforcement with blocking
    """

    def __init__(self, redis_client, feature_flags=None, metrics_service=None):
        """
        Initialize session ownership validator.

        Args:
            redis_client: Async Redis client for ownership data
            feature_flags: Optional feature flags service for enforcement mode
            metrics_service: Optional metrics service for violation tracking
        """
        self.redis = redis_client
        self.ownership_ttl = 86400  # 24 hours (match conversation TTL)
        self.feature_flags = feature_flags
        self.metrics_service = metrics_service

    def _get_ownership_key(self, session_id: str) -> str:
        """Generate Redis key for session ownership."""
        return f"chat_session_owner:{session_id}"

    def _get_user_sessions_key(self, username: str) -> str:
        """Generate Redis key for user's session set."""
        return f"user_chat_sessions:{username}"

    async def set_session_owner(self, session_id: str, username: str) -> bool:
        """
        Associate a chat session with its owner.

        Args:
            session_id: Chat session ID
            username: Owner username

        Returns:
            True if successful
        """
        try:
            # Store ownership mapping
            ownership_key = self._get_ownership_key(session_id)
            await self.redis.set(ownership_key, username, ex=self.ownership_ttl)

            # Add to user's session set
            user_sessions_key = self._get_user_sessions_key(username)
            await self.redis.sadd(user_sessions_key, session_id)
            await self.redis.expire(user_sessions_key, 2592000)  # 30 days

            logger.info(f"Session {session_id[:8]}... assigned to owner {username}")
            return True

        except Exception as e:
            logger.error(f"Failed to set session owner: {e}")
            return False

    async def get_session_owner(self, session_id: str) -> Optional[str]:
        """
        Get the owner of a chat session.

        Args:
            session_id: Chat session ID

        Returns:
            Owner username if exists, None otherwise
        """
        try:
            ownership_key = self._get_ownership_key(session_id)
            owner = await self.redis.get(ownership_key)
            # Handle both bytes and str responses from Redis
            if owner is None:
                return None
            return owner.decode() if isinstance(owner, bytes) else owner
        except Exception as e:
            logger.error(f"Failed to get session owner: {e}")
            return None

    async def validate_ownership(self, session_id: str, request: Request) -> Dict:
        """
        Validate that requesting user owns the session with feature flag support.

        Enforcement modes:
        - DISABLED: Skip validation, allow all authenticated access
        - LOG_ONLY: Validate and audit violations, but don't block
        - ENFORCED: Full enforcement, block unauthorized access

        Args:
            session_id: Chat session ID
            request: FastAPI request object

        Returns:
            Dict with validation result and user data

        Raises:
            HTTPException: 401 if not authenticated, 403 if not authorized (ENFORCED mode only)
        """
        # Get authenticated user from request
        user_data = auth_middleware.get_user_from_request(request)

        if not user_data:
            logger.warning(
                f"Unauthenticated access attempt to session {session_id[:8]}..."
            )
            raise HTTPException(
                status_code=401,
                detail="Authentication required to access conversations",
            )

        username = user_data["username"]

        # If auth is disabled globally, allow all access (development mode)
        if user_data.get("auth_disabled") or not auth_middleware.enable_auth:
            logger.debug(
                f"Auth disabled - allowing access to session {session_id[:8]}..."
            )
            return {
                "authorized": True,
                "user_data": user_data,
                "reason": "auth_disabled",
            }

        # Get enforcement mode from feature flags
        enforcement_mode = "disabled"  # Default to disabled (safe)
        if self.feature_flags:
            try:
                from backend.services.feature_flags import EnforcementMode

                mode_enum = await self.feature_flags.get_enforcement_mode()
                enforcement_mode = mode_enum.value
            except Exception as e:
                logger.error(
                    f"Failed to get enforcement mode: {e}, defaulting to disabled"
                )

        # FAST PATH: If enforcement is DISABLED, skip validation entirely
        if enforcement_mode == "disabled":
            logger.debug(
                f"[DISABLED MODE] Skipping ownership validation for session {session_id[:8]}..."
            )
            return {
                "authorized": True,
                "user_data": user_data,
                "reason": "enforcement_disabled",
            }

        # Perform ownership check (for both LOG_ONLY and ENFORCED modes)
        stored_owner = await self.get_session_owner(session_id)

        # If no owner stored, this might be a legacy session
        if not stored_owner:
            logger.warning(f"Session {session_id[:8]}... has no owner (legacy session)")
            # Assign to current user (migration support)
            await self.set_session_owner(session_id, username)
            return {
                "authorized": True,
                "user_data": user_data,
                "reason": "legacy_migration",
            }

        # Check if user owns the session
        if stored_owner != username:
            # Unauthorized access detected
            logger.warning(
                f"[{enforcement_mode.upper()} MODE] Unauthorized access: "
                f"user {username} tried to access session {session_id[:8]}... owned by {stored_owner}"
            )

            # ALWAYS audit log violations (regardless of mode)
            try:
                auth_middleware.security_layer.audit_log(
                    action="unauthorized_conversation_access",
                    user=username,
                    outcome="log_only" if enforcement_mode == "log_only" else "denied",
                    details={
                        "session_id": session_id[:16] + "...",
                        "actual_owner": stored_owner,
                        "attempted_by": username,
                        "ip": request.client.host if request.client else "unknown",
                        "enforcement_mode": enforcement_mode,
                    },
                )
            except Exception as e:
                logger.error(f"Failed to write audit log: {e}")

            # Record violation in metrics (for analysis during LOG_ONLY phase)
            if self.metrics_service:
                try:
                    await self.metrics_service.record_violation(
                        session_id=session_id,
                        username=username,
                        actual_owner=stored_owner,
                        endpoint=str(request.url.path),
                        ip_address=request.client.host if request.client else "unknown",
                        enforcement_mode=enforcement_mode,
                    )
                except Exception as e:
                    logger.error(f"Failed to record violation metrics: {e}")

            # MODE-SPECIFIC BEHAVIOR
            if enforcement_mode == "log_only":
                # LOG_ONLY: Audit and log, but allow access
                logger.warning(
                    f"[LOG_ONLY MODE] Would block access but allowing due to log-only mode: "
                    f"{username} accessing session owned by {stored_owner}"
                )
                return {
                    "authorized": True,  # Allow access in log-only mode
                    "user_data": user_data,
                    "reason": "log_only_mode",
                    "violation_logged": True,
                    "actual_owner": stored_owner,
                }
            else:
                # ENFORCED: Block access
                raise HTTPException(
                    status_code=403,
                    detail="You do not have permission to access this conversation",
                )

        # Authorized access (user owns the session)
        logger.debug(
            f"Authorized access: user {username} accessing own session {session_id[:8]}..."
        )

        # Audit log successful access
        try:
            auth_middleware.security_layer.audit_log(
                action="conversation_accessed",
                user=username,
                outcome="success",
                details={
                    "session_id": session_id[:16] + "...",
                    "ip": request.client.host if request.client else "unknown",
                    "enforcement_mode": enforcement_mode,
                },
            )
        except Exception as e:
            logger.error(f"Failed to write audit log: {e}")

        return {"authorized": True, "user_data": user_data, "reason": "owner_match"}

    async def get_user_sessions(self, username: str) -> list[str]:
        """
        Get all sessions owned by a user.

        Args:
            username: Owner username

        Returns:
            List of session IDs
        """
        try:
            user_sessions_key = self._get_user_sessions_key(username)
            sessions = await self.redis.smembers(user_sessions_key)
            if not sessions:
                return []
            # Handle both bytes and str responses from Redis
            return [s.decode() if isinstance(s, bytes) else s for s in sessions]
        except Exception as e:
            logger.error(f"Failed to get user sessions: {e}")
            return []


# Dependency function for FastAPI endpoints
async def validate_session_ownership(session_id: str, request: Request) -> Dict:
    """
    FastAPI dependency to validate session ownership with feature flag support.

    Integrates with:
    - Feature flags service (for enforcement mode)
    - Metrics service (for violation tracking)
    - Audit logging (for compliance)

    Usage:
        @router.get("/chat/sessions/{session_id}")
        async def get_session(
            session_id: str,
            request: Request,
            ownership: Dict = Depends(validate_session_ownership)
        ):
            # Access is already validated
            user_data = ownership["user_data"]
            ...

    Args:
        session_id: Chat session ID from URL path
        request: FastAPI request object

    Returns:
        Dict with authorization status and user data

    Raises:
        HTTPException: 401 if not authenticated, 403 if not authorized (ENFORCED mode)
    """
    from backend.services.access_control_metrics import get_metrics_service
    from backend.services.feature_flags import get_feature_flags
    from backend.utils.async_redis_manager import get_redis_manager

    # Get Redis connection
    redis_manager = await get_redis_manager()
    redis = await redis_manager.main()

    # Get feature flags service (optional, gracefully degrade if unavailable)
    try:
        feature_flags = await get_feature_flags()
    except Exception as e:
        logger.warning(f"Feature flags unavailable, defaulting to disabled mode: {e}")
        feature_flags = None

    # Get metrics service (optional)
    try:
        metrics_service = await get_metrics_service()
    except Exception as e:
        logger.warning(f"Metrics service unavailable: {e}")
        metrics_service = None

    # Create validator with all dependencies
    validator = SessionOwnershipValidator(
        redis, feature_flags=feature_flags, metrics_service=metrics_service
    )

    return await validator.validate_ownership(session_id, request)
