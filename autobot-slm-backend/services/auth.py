# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
SLM Authentication Service

JWT-based authentication and user management.

Token verification strategy (#10197, epic #10193)
--------------------------------------------------
The SLM accepts tokens from two issuers during the migration window:

1. **Authority RS256 tokens** — issued by autobot-backend, signed with an RSA
   private key.  Verified here using the authority's public key fetched from its
   JWKS endpoint (Pattern B — SLM never holds the private key).  Claims are
   normalized to a common shape.

2. **Legacy SLM HS256 tokens** — issued by this service via
   ``create_access_token``.  Verified with ``settings.secret_key`` as before.

Routing is done by reading the ``alg`` header from the unverified JWT — an
RS256 token is NEVER verified with the HS256 secret, and vice-versa.  The
shared ``autobot_shared.auth.jwt_core`` algorithm-confusion guard applies on
every verification call, so ``alg=none`` and cross-algorithm attacks are
rejected before PyJWT is invoked.
"""

import logging
from datetime import timedelta
from typing import Callable

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.auth.jwt_core import _peek_alg, decode_jwt_or_none, encode_jwt, hash_password
from autobot_shared.auth.permissions import ROLE_PERMISSIONS, Permission, Role
from config import settings
from models.schemas import TokenResponse, UserCreate, UserResponse
from user_management.models.user import User

logger = logging.getLogger(__name__)

security = HTTPBearer()


class AuthService:
    """Handles authentication and authorization."""

    def hash_password(self, password: str) -> str:
        """Hash a password."""
        return hash_password(password)

    def create_access_token(self, data: dict, expires_delta: timedelta | None = None) -> str:
        """Create a JWT access token."""
        default_delta = timedelta(minutes=settings.access_token_expire_minutes)
        return encode_jwt(
            data,
            secret=settings.secret_key,
            expires_delta=expires_delta if expires_delta is not None else default_delta,
        )

    def decode_token(self, token: str) -> dict | None:
        """Decode and validate a JWT token (synchronous HS256 path only).

        Routes by ``alg`` header:
        - HS256 → legacy SLM token; verified with ``settings.secret_key``.
        - RS256 → authority token; cannot be verified synchronously (JWKS fetch
          is async).  Returns ``None`` so that callers with async context use
          ``decode_token_async`` instead.  Logs a debug note to avoid silent
          confusion in WebSocket / other sync call sites.

        Use ``decode_token_async`` in async contexts — it handles both alg
        values and performs JWKS key lookup for RS256 tokens.
        """
        alg = _peek_alg(token)
        if alg == "RS256":
            # RS256 verification is async; sync callers get None and should
            # migrate to decode_token_async.  This is not a security hole —
            # the token is simply treated as unverified rather than accepted.
            logger.debug(
                "decode_token (sync) received RS256 token; use decode_token_async in async contexts"
            )
            return None
        return decode_jwt_or_none(token, settings.secret_key)

    async def decode_token_async(self, token: str) -> dict | None:
        """Decode and validate a JWT token in an async context.

        Routes by ``alg`` header:
        - RS256 → authority token; fetches/caches JWKS from the authority
          endpoint and verifies via ``jwt_core.decode_jwt(public_key=...)``.
          Never falls back to HS256 for an RS256 token.
        - HS256 → legacy SLM token; verified with ``settings.secret_key``.
        - Any other / ``none`` → rejected (algorithm-confusion guard).

        Returns the normalized claims dict, or ``None`` on any failure.
        """
        alg = _peek_alg(token)

        if alg == "RS256":
            from services.jwks_verifier import verify_authority_token

            return await verify_authority_token(token)

        if alg == "HS256":
            return decode_jwt_or_none(token, settings.secret_key)

        # alg=none or unsupported — reject
        logger.warning("decode_token_async: rejecting token with unsupported alg=%r", alg)
        return None

    async def create_user(self, db: AsyncSession, user_data: UserCreate) -> UserResponse:
        """Create a new user."""
        result = await db.execute(select(User).where(User.username == user_data.username))
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already exists",
            )

        user = User(
            email=f"{user_data.username}@slm.local",
            username=user_data.username,
            password_hash=self.hash_password(user_data.password),
            is_platform_admin=user_data.is_admin,
            is_active=True,
            is_verified=False,
            mfa_enabled=False,
            preferences={},
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

        return UserResponse.model_validate(user)

    async def get_user_by_username(self, db: AsyncSession, username: str) -> User | None:
        """Get a user by username."""
        result = await db.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    async def create_token_response(self, user: User) -> TokenResponse:
        """Create a token response for a user."""
        role = Role.ADMIN.value if user.is_platform_admin else Role.USER.value
        access_token = self.create_access_token(
            data={"sub": user.username, "admin": user.is_platform_admin, "role": role}
        )
        return TokenResponse(
            access_token=access_token,
            token_type="bearer",  # nosec B106 - standard OAuth2 token type
            expires_in=settings.access_token_expire_minutes * 60,
        )


auth_service = AuthService()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """FastAPI dependency to get the current authenticated user.

    Accepts both authority RS256 tokens (verified via JWKS) and legacy SLM
    HS256 tokens.  Routing is determined by the JWT ``alg`` header so
    algorithm-confusion attacks are structurally prevented.
    """
    token = credentials.credentials
    payload = await auth_service.decode_token_async(token)

    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return payload


def require_permission(permission: Permission) -> Callable:
    """FastAPI dependency factory requiring a specific permission.

    Derives the user's role from the JWT 'role' field (preferred) or falls
    back to the legacy 'admin' boolean flag for tokens issued before role was
    included.  Raises 403 when the role lacks the required permission.

    Usage::

        @router.post("/endpoint")
        async def endpoint(
            _: dict = Depends(require_permission(Permission.ADMIN_CONFIG_WRITE)),
        ): ...
    """

    async def _check(current_user: dict = Depends(get_current_user)) -> dict:
        role_str = current_user.get("role")
        if role_str:
            try:
                role = Role(role_str)
            except ValueError:
                role = Role.USER
        else:
            role = Role.ADMIN if current_user.get("admin", False) else Role.USER

        if permission not in ROLE_PERMISSIONS.get(role, []):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {permission.value} required",
            )
        return current_user

    return _check


async def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """FastAPI dependency requiring admin privileges (legacy binary check).

    Prefer require_permission(Permission.ADMIN_SYSTEM) for new endpoints.
    Retained for backward compatibility with any callers not yet migrated.
    """
    if not current_user.get("admin", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return current_user


async def get_slm_db():
    """Local dependency for SLM database session."""
    from user_management.database import get_slm_session

    async with get_slm_session() as session:
        yield session


async def get_api_key_user(
    x_api_key: str = Header(None, alias="X-API-Key"),
    db: AsyncSession = Depends(get_slm_db),
) -> dict:
    """FastAPI dependency to authenticate via API key.

    Args:
        x_api_key: API key from X-API-Key header
        db: Database session

    Returns:
        User payload dict (similar to JWT payload)

    Raises:
        HTTPException: If API key is invalid or missing
    """
    from user_management.services.api_key_service import APIKeyService
    from user_management.services.base_service import TenantContext

    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    context = TenantContext(is_platform_admin=True)
    api_key_service = APIKeyService(db, context)

    api_key = await api_key_service.validate_key(x_api_key)
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    user = await _get_user_for_api_key(db, api_key.user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found for API key",
        )

    return {
        "sub": user.username,
        "admin": user.is_platform_admin,
        "api_key_id": str(api_key.id),
    }


async def _get_user_for_api_key(db: AsyncSession, user_id):
    """Get user by ID for API key authentication.

    Helper for get_api_key_user dependency (Issue #576 Phase 5).

    Args:
        db: Database session
        user_id: User UUID

    Returns:
        User instance or None
    """
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()
