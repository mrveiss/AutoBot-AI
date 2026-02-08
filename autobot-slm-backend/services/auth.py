# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Authentication Service

JWT-based authentication and user management.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from models.database import User
from models.schemas import TokenResponse, UserCreate, UserResponse
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings

logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()


class AuthService:
    """Handles authentication and authorization."""

    def __init__(self):
        self.algorithm = "HS256"

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash."""
        return pwd_context.verify(plain_password, hashed_password)

    def hash_password(self, password: str) -> str:
        """Hash a password."""
        return pwd_context.hash(password)

    def create_access_token(
        self, data: dict, expires_delta: Optional[timedelta] = None
    ) -> str:
        """Create a JWT access token."""
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(
                minutes=settings.access_token_expire_minutes
            )
        to_encode.update({"exp": expire})
        return jwt.encode(to_encode, settings.secret_key, algorithm=self.algorithm)

    def decode_token(self, token: str) -> Optional[dict]:
        """Decode and validate a JWT token."""
        try:
            payload = jwt.decode(
                token, settings.secret_key, algorithms=[self.algorithm]
            )
            return payload
        except JWTError as e:
            logger.warning("JWT decode error: %s", e)
            return None

    async def authenticate_user(
        self, db: AsyncSession, username: str, password: str
    ) -> Optional[User]:
        """Authenticate a user by username and password."""
        result = await db.execute(select(User).where(User.username == username))
        user = result.scalar_one_or_none()

        if not user:
            return None
        if not user.is_active:
            return None
        if not self.verify_password(password, user.password_hash):
            return None

        user.last_login = datetime.utcnow()
        await db.commit()

        return user

    async def create_user(
        self, db: AsyncSession, user_data: UserCreate
    ) -> UserResponse:
        """Create a new user."""
        result = await db.execute(
            select(User).where(User.username == user_data.username)
        )
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already exists",
            )

        user = User(
            username=user_data.username,
            password_hash=self.hash_password(user_data.password),
            is_admin=user_data.is_admin,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

        return UserResponse.model_validate(user)

    async def get_user_by_username(
        self, db: AsyncSession, username: str
    ) -> Optional[User]:
        """Get a user by username."""
        result = await db.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    async def create_token_response(self, user: User) -> TokenResponse:
        """Create a token response for a user."""
        access_token = self.create_access_token(
            data={"sub": user.username, "admin": user.is_admin}
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
    """FastAPI dependency to get the current authenticated user."""
    token = credentials.credentials
    payload = auth_service.decode_token(token)

    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return payload


async def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """FastAPI dependency requiring admin privileges."""
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
    from user_management.models.user import User

    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()
