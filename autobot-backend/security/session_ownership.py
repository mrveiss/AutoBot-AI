# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
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

from auth_middleware import auth_middleware
from fastapi import HTTPException, Request

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

    def _get_org_sessions_key(self, org_id: str) -> str:
        """Generate Redis key for organization's session set (#684)."""
        return f"org_chat_sessions:{org_id}"

    def _get_team_sessions_key(self, team_id: str) -> str:
        """Generate Redis key for team's session set (#684)."""
        return f"team_chat_sessions:{team_id}"

    def _get_session_context_key(self, session_id: str) -> str:
        """Generate Redis key for session org/team context (#684)."""
        return f"chat_session_context:{session_id}"

    async def set_session_owner(
        self,
        session_id: str,
        username: str,
        org_id: str | None = None,
        team_id: str | None = None,
    ) -> bool:
        """
        Associate a chat session with its owner and org/team context.

        Args:
            session_id: Chat session ID
            username: Owner username
            org_id: Organization ID (#684)
            team_id: Team ID for team-scoped sessions (#684)

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

            # Issue #684: Store org/team indices
            if org_id:
                await self._store_org_session_index(session_id, org_id)
            if team_id:
                await self._store_team_session_index(session_id, team_id)
            if org_id or team_id:
                await self._store_session_context(session_id, org_id, team_id)

            logger.info("Session %s... assigned to owner %s", session_id[:8], username)
            return True

        except Exception as e:
            logger.error("Failed to set session owner: %s", e)
            return False

    async def _store_org_session_index(self, session_id: str, org_id: str) -> None:
        """Store session in organization's session set (#684)."""
        org_key = self._get_org_sessions_key(org_id)
        await self.redis.sadd(org_key, session_id)
        await self.redis.expire(org_key, 2592000)  # 30 days

    async def _store_team_session_index(self, session_id: str, team_id: str) -> None:
        """Store session in team's session set (#684)."""
        team_key = self._get_team_sessions_key(team_id)
        await self.redis.sadd(team_key, session_id)
        await self.redis.expire(team_key, 2592000)  # 30 days

    async def _store_session_context(
        self, session_id: str, org_id: str | None, team_id: str | None
    ) -> None:
        """Store org/team context for a session (#684)."""
        ctx_key = self._get_session_context_key(session_id)
        context = {}
        if org_id:
            context["org_id"] = org_id
        if team_id:
            context["team_id"] = team_id
        if context:
            await self.redis.hset(ctx_key, mapping=context)
            await self.redis.expire(ctx_key, self.ownership_ttl)

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
            logger.error("Failed to get session owner: %s", e)
            return None

    def _get_authenticated_user(self, session_id: str, request: Request) -> Dict:
        """
        Get authenticated user from request, raising HTTPException if not authenticated.

        Issue #281: Extracted helper for authentication check.

        Args:
            session_id: Chat session ID (for logging)
            request: FastAPI request object

        Returns:
            Dict with user data

        Raises:
            HTTPException: 401 if not authenticated
        """
        user_data = auth_middleware.get_user_from_request(request)

        if not user_data:
            logger.warning(
                f"Unauthenticated access attempt to session {session_id[:8]}..."
            )
            raise HTTPException(
                status_code=401,
                detail="Authentication required to access conversations",
            )

        return user_data

    async def _get_enforcement_mode(self) -> str:
        """
        Get enforcement mode from feature flags with safe default.

        Issue #281: Extracted helper for enforcement mode retrieval.

        Returns:
            Enforcement mode string: "disabled", "log_only", or "enforced"
        """
        if not self.feature_flags:
            return "disabled"

        try:
            mode_enum = await self.feature_flags.get_enforcement_mode()
            return mode_enum.value
        except Exception as e:
            logger.error(f"Failed to get enforcement mode: {e}, defaulting to disabled")
            return "disabled"

    def _audit_log_violation(
        self,
        username: str,
        session_id: str,
        stored_owner: str,
        request: Request,
        enforcement_mode: str,
    ) -> None:
        """
        Audit log an unauthorized access violation.

        Issue #281: Extracted helper for violation audit logging.

        Args:
            username: User attempting access
            session_id: Session being accessed
            stored_owner: Actual owner of session
            request: FastAPI request object
            enforcement_mode: Current enforcement mode
        """
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
            logger.error("Failed to write audit log: %s", e)

    async def _record_violation_metrics(
        self,
        session_id: str,
        username: str,
        stored_owner: str,
        request: Request,
        enforcement_mode: str,
    ) -> None:
        """
        Record violation in metrics service for analysis.

        Issue #281: Extracted helper for violation metrics recording.

        Args:
            session_id: Session being accessed
            username: User attempting access
            stored_owner: Actual owner of session
            request: FastAPI request object
            enforcement_mode: Current enforcement mode
        """
        if not self.metrics_service:
            return

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
            logger.error("Failed to record violation metrics: %s", e)

    def _audit_log_success(
        self, username: str, session_id: str, request: Request, enforcement_mode: str
    ) -> None:
        """
        Audit log successful session access.

        Issue #281: Extracted helper for success audit logging.

        Args:
            username: User accessing session
            session_id: Session being accessed
            request: FastAPI request object
            enforcement_mode: Current enforcement mode
        """
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
            logger.error("Failed to write audit log: %s", e)

    async def _check_ownership_mismatch(
        self,
        username: str,
        session_id: str,
        stored_owner: str,
        user_data: Dict,
        request: Request,
        enforcement_mode: str,
    ) -> Dict:
        """Handle ownership mismatch with org admin bypass.

        Helper for validate_ownership (#684).
        """
        # Issue #684: Org admins can access any session in their org
        if await self._is_org_admin_access(user_data, session_id):
            logger.info(
                "Org admin %s accessing session %s... via admin privilege",
                username,
                session_id[:8],
            )
            self._audit_log_success(username, session_id, request, enforcement_mode)
            return {
                "authorized": True,
                "user_data": user_data,
                "reason": "org_admin",
            }

        # Issue #689: Check if session is shared with this user
        user_id = user_data.get("user_id", username)
        if await self.is_shared_with_user(session_id, user_id):
            logger.info(
                "User %s accessing shared session %s...",
                username,
                session_id[:8],
            )
            self._audit_log_success(username, session_id, request, enforcement_mode)
            return {
                "authorized": True,
                "user_data": user_data,
                "reason": "shared_access",
            }

        return await self._handle_unauthorized_access(
            username,
            session_id,
            stored_owner,
            user_data,
            request,
            enforcement_mode,
        )

    async def _is_org_admin_access(self, user_data: Dict, session_id: str) -> bool:
        """Check if user is an org admin accessing a session in their org.

        Helper for validate_ownership (#684).
        """
        user_role = user_data.get("role", "")
        user_org_id = user_data.get("org_id")
        if user_role not in ("admin", "org_admin") or not user_org_id:
            return False
        session_ctx = await self.get_session_context(session_id)
        return session_ctx.get("org_id") == user_org_id

    async def _handle_unauthorized_access(
        self,
        username: str,
        session_id: str,
        stored_owner: str,
        user_data: Dict,
        request: Request,
        enforcement_mode: str,
    ) -> Dict:
        """
        Handle unauthorized access attempt based on enforcement mode.

        Issue #281: Extracted helper for unauthorized access handling.

        Args:
            username: User attempting access
            session_id: Session being accessed
            stored_owner: Actual owner of session
            user_data: Authenticated user data
            request: FastAPI request object
            enforcement_mode: Current enforcement mode

        Returns:
            Dict with authorization result (for log_only mode)

        Raises:
            HTTPException: 403 if enforced mode
        """
        logger.warning(
            f"[{enforcement_mode.upper()} MODE] Unauthorized access: "
            f"user {username} tried to access session {session_id[:8]}... owned by {stored_owner}"
        )

        # Always audit log and record metrics
        self._audit_log_violation(
            username, session_id, stored_owner, request, enforcement_mode
        )
        await self._record_violation_metrics(
            session_id, username, stored_owner, request, enforcement_mode
        )

        # Mode-specific behavior
        if enforcement_mode == "log_only":
            logger.warning(
                f"[LOG_ONLY MODE] Would block access but allowing due to log-only mode: "
                f"{username} accessing session owned by {stored_owner}"
            )
            return {
                "authorized": True,
                "user_data": user_data,
                "reason": "log_only_mode",
                "violation_logged": True,
                "actual_owner": stored_owner,
            }
        else:
            raise HTTPException(
                status_code=403,
                detail="You do not have permission to access this conversation",
            )

    async def _resolve_fast_paths(
        self,
        session_id: str,
        user_data: Dict,
    ) -> Optional[Dict]:
        """Helper for validate_ownership. Ref: #1088.

        Checks the two early-exit conditions that bypass ownership lookup:
        1. Auth is disabled globally (development mode).
        2. Enforcement mode is "disabled".

        Returns the result dict when a fast path applies, or None to signal
        that the caller should proceed to the full ownership check.
        """
        if user_data.get("auth_disabled") or not auth_middleware.enable_auth:
            logger.debug(
                f"Auth disabled - allowing access to session {session_id[:8]}..."
            )
            return {
                "authorized": True,
                "user_data": user_data,
                "reason": "auth_disabled",
            }

        enforcement_mode = await self._get_enforcement_mode()

        if enforcement_mode == "disabled":
            logger.debug(
                f"[DISABLED MODE] Skipping ownership validation for session {session_id[:8]}..."
            )
            return {
                "authorized": True,
                "user_data": user_data,
                "reason": "enforcement_disabled",
            }

        return None

    async def _resolve_ownership(
        self,
        session_id: str,
        username: str,
        user_data: Dict,
        request: Request,
        enforcement_mode: str,
    ) -> Dict:
        """Helper for validate_ownership. Ref: #1088.

        Performs the Redis ownership lookup and resolves the result into one of:
        - legacy_migration  (no stored owner — claim it now)
        - mismatch path     (owner differs — delegate to _check_ownership_mismatch)
        - owner_match       (user owns the session)

        Args:
            session_id: Chat session ID
            username: Authenticated username
            user_data: Authenticated user data dict
            request: FastAPI request object
            enforcement_mode: Current enforcement mode string

        Returns:
            Dict with authorization result and user data
        """
        stored_owner = await self.get_session_owner(session_id)

        if not stored_owner:
            logger.warning(
                "Session %s... has no owner (legacy session)", session_id[:8]
            )
            await self.set_session_owner(
                session_id,
                username,
                org_id=user_data.get("org_id"),
                team_id=None,
            )
            return {
                "authorized": True,
                "user_data": user_data,
                "reason": "legacy_migration",
            }

        if stored_owner != username:
            return await self._check_ownership_mismatch(
                username, session_id, stored_owner, user_data, request, enforcement_mode
            )

        logger.debug(
            "Authorized access: user %s accessing own session %s...",
            username,
            session_id[:8],
        )
        self._audit_log_success(username, session_id, request, enforcement_mode)
        return {"authorized": True, "user_data": user_data, "reason": "owner_match"}

    async def validate_ownership(self, session_id: str, request: Request) -> Dict:
        """
        Validate that requesting user owns the session with feature flag support.

        Issue #281: Refactored from 163 lines to use extracted helper methods.

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
        user_data = self._get_authenticated_user(session_id, request)
        username = user_data["username"]

        fast_path_result = await self._resolve_fast_paths(session_id, user_data)
        if fast_path_result is not None:
            return fast_path_result

        enforcement_mode = await self._get_enforcement_mode()
        return await self._resolve_ownership(
            session_id, username, user_data, request, enforcement_mode
        )

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
            logger.error("Failed to get user sessions: %s", e)
            return []

    async def get_org_sessions(self, org_id: str) -> list[str]:
        """Get all sessions for an organization (#684)."""
        try:
            org_key = self._get_org_sessions_key(org_id)
            sessions = await self.redis.smembers(org_key)
            if not sessions:
                return []
            return [s.decode() if isinstance(s, bytes) else s for s in sessions]
        except Exception as e:
            logger.error("Failed to get org sessions: %s", e)
            return []

    async def get_team_sessions(self, team_id: str) -> list[str]:
        """Get all sessions for a team (#684)."""
        try:
            team_key = self._get_team_sessions_key(team_id)
            sessions = await self.redis.smembers(team_key)
            if not sessions:
                return []
            return [s.decode() if isinstance(s, bytes) else s for s in sessions]
        except Exception as e:
            logger.error("Failed to get team sessions: %s", e)
            return []

    # =========================================================================
    # SESSION SHARING (Issue #689)
    # =========================================================================

    def _get_shared_session_key(self, session_id: str) -> str:
        """Redis key for users a session is shared with (#689)."""
        return "session:shared_with:%s" % session_id

    def _get_user_shared_sessions_key(self, user_id: str) -> str:
        """Redis key for sessions shared WITH a user (#689)."""
        return "user:shared_sessions:%s" % user_id

    async def share_session(
        self,
        session_id: str,
        shared_with_ids: list[str],
        shared_by: str,
    ) -> bool:
        """Share a session with other users (#689).

        Args:
            session_id: Session to share
            shared_with_ids: User IDs to share with
            shared_by: Username of the person sharing

        Returns:
            True if successful
        """
        try:
            shared_key = self._get_shared_session_key(session_id)
            for user_id in shared_with_ids:
                await self.redis.sadd(shared_key, user_id)
                user_key = self._get_user_shared_sessions_key(user_id)
                await self.redis.sadd(user_key, session_id)
                await self.redis.expire(user_key, 2592000)  # 30 days

            await self.redis.expire(shared_key, 2592000)  # 30 days
            logger.info(
                "Session %s... shared by %s with %d users",
                session_id[:8],
                shared_by,
                len(shared_with_ids),
            )
            return True
        except Exception as e:
            logger.error("Failed to share session: %s", e)
            return False

    async def is_shared_with_user(self, session_id: str, user_id: str) -> bool:
        """Check if a session is shared with a user (#689)."""
        try:
            shared_key = self._get_shared_session_key(session_id)
            return bool(await self.redis.sismember(shared_key, user_id))
        except Exception as e:
            logger.error("Failed to check shared status: %s", e)
            return False

    async def get_shared_sessions(self, user_id: str) -> list[str]:
        """Get all sessions shared with a user (#689)."""
        try:
            key = self._get_user_shared_sessions_key(user_id)
            sessions = await self.redis.smembers(key)
            if not sessions:
                return []
            return [s.decode() if isinstance(s, bytes) else s for s in sessions]
        except Exception as e:
            logger.error("Failed to get shared sessions: %s", e)
            return []

    async def get_session_context(self, session_id: str) -> dict:
        """Get org/team context for a session (#684)."""
        try:
            ctx_key = self._get_session_context_key(session_id)
            context = await self.redis.hgetall(ctx_key)
            if not context:
                return {}
            return {
                (k.decode() if isinstance(k, bytes) else k): (
                    v.decode() if isinstance(v, bytes) else v
                )
                for k, v in context.items()
            }
        except Exception as e:
            logger.error("Failed to get session context: %s", e)
            return {}


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
    from services.access_control_metrics import get_metrics_service
    from services.feature_flags import get_feature_flags

    from autobot_shared.redis_client import get_redis_client as get_redis_manager

    # Get Redis connection for main database
    redis = await get_redis_manager(async_client=True, database="main")

    # Get feature flags service (optional, gracefully degrade if unavailable)
    try:
        feature_flags = await get_feature_flags()
    except Exception as e:
        logger.warning("Feature flags unavailable, defaulting to disabled mode: %s", e)
        feature_flags = None

    # Get metrics service (optional)
    try:
        metrics_service = await get_metrics_service()
    except Exception as e:
        logger.warning("Metrics service unavailable: %s", e)
        metrics_service = None

    # Create validator with all dependencies
    validator = SessionOwnershipValidator(
        redis, feature_flags=feature_flags, metrics_service=metrics_service
    )

    return await validator.validate_ownership(session_id, request)
