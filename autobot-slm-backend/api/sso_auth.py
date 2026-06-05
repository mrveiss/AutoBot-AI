# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SSO Authentication API

Public endpoints for SSO login flows (OAuth2, LDAP, SAML).
"""

import logging
import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.ssot_config import config
from services.auth import auth_service
from user_management.database import get_slm_session
from user_management.schemas.sso import LDAPLoginRequest, SSOLoginInitResponse
from user_management.services.base_service import TenantContext
from user_management.services.sso_service import (
    SSOAuthenticationError,
    SSOProviderNotFoundError,
    SSOService,
    SSOServiceError,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth/sso", tags=["sso-auth"])

# Callback URL allowlist (Security: MVA-3396 M-2)
_ALLOWED_CALLBACK_HOSTS = frozenset(
    host.strip().lower() for host in config.auth.sso_callback_hosts.split(",") if host.strip()
)


async def get_slm_db():
    """Dependency for SLM database session."""
    async with get_slm_session() as session:
        yield session


def _build_callback_url(request: Request) -> str:
    """Build OAuth2 callback URL from request headers with security validation.

    Security (MVA-3396 M-2):
    - Validates host against allowlist to prevent authorization code phishing
    - Enforces HTTPS in production when configured
    - Mitigates X-Forwarded-Host manipulation attacks

    Args:
        request: FastAPI request object

    Returns:
        Validated callback URL

    Raises:
        HTTPException: 400 if host is not in allowlist or scheme is invalid
    """
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host", request.url.netloc)

    # Normalize host for comparison (lowercase, strip port if present)
    normalized_host = host.lower().split(":")[0] if host else ""

    # Validate host against allowlist
    if normalized_host not in _ALLOWED_CALLBACK_HOSTS:
        logger.error(
            "OAuth callback rejected: host not in allowlist",
            extra={
                "requested_host": host,
                "normalized_host": normalized_host,
                "allowlist": list(_ALLOWED_CALLBACK_HOSTS),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid callback host",
        )

    # Enforce HTTPS in production
    if config.auth.enforce_https_callbacks and scheme != "https":
        logger.error(
            "OAuth callback rejected: HTTPS required",
            extra={
                "requested_scheme": scheme,
                "host": normalized_host,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Callback must use HTTPS",
        )

    return f"{scheme}://{host}/api/auth/sso/callback"


@router.get("/providers", response_model=list[dict])
async def list_active_providers(
    db: AsyncSession = Depends(get_slm_db),
) -> list[dict]:
    """List active SSO providers for login page."""
    context = TenantContext(is_platform_admin=False)
    sso_service = SSOService(db, context)

    providers, _ = await sso_service.list_providers(active_only=True)
    return [
        {
            "id": str(p.id),
            "name": p.name,
            "provider_type": p.provider_type,
            "is_social": p.is_social,
        }
        for p in providers
    ]


@router.get("/{provider_id}/login", response_model=SSOLoginInitResponse)
async def initiate_sso_login(
    provider_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_slm_db),
) -> SSOLoginInitResponse:
    """Initiate SSO login flow (OAuth2/SAML)."""
    logger.info("Initiating SSO login for provider: %s", provider_id)
    context = TenantContext(is_platform_admin=False)
    sso_service = SSOService(db, context)

    try:
        provider = await sso_service.get_provider(provider_id)
        callback_url = _build_callback_url(request)

        if provider.provider_type in ("ldap", "active_directory"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="LDAP login requires POST to /auth/sso/ldap/login",
            )

        redirect_url, state = await sso_service.initiate_oauth_login(provider_id, callback_url)

        return SSOLoginInitResponse(
            provider_id=provider.id,
            provider_type=provider.provider_type,
            provider_name=provider.name,
            redirect_url=redirect_url,
            state=state,
        )
    except SSOProviderNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Internal server error",
        ) from e
    except SSOServiceError as e:
        logger.error("Failed to initiate SSO login: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Internal server error",
        ) from e


@router.get("/callback")
async def oauth_callback(
    request: Request,
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_slm_db),
) -> RedirectResponse:
    """Handle OAuth2 callback."""
    logger.info("Processing OAuth2 callback")
    context = TenantContext(is_platform_admin=False)
    sso_service = SSOService(db, context)

    try:
        callback_url = _build_callback_url(request)
        user = await sso_service.complete_oauth_login(code, state, callback_url)

        # Convert User ORM object to dict-like structure for auth_service
        user_dict = type(
            "User",
            (),
            {
                "username": user.username,
                "is_admin": (user.is_platform_admin if hasattr(user, "is_platform_admin") else False),
            },
        )()

        token_response = await auth_service.create_token_response(user_dict)
        return RedirectResponse(
            url=f"/?token={token_response.access_token}",
            status_code=status.HTTP_302_FOUND,
        )
    except (SSOAuthenticationError, SSOProviderNotFoundError) as e:
        logger.error("OAuth callback failed: %s", e)
        return RedirectResponse(
            url="/login?error=sso_failed",
            status_code=status.HTTP_302_FOUND,
        )


@router.post("/ldap/login")
async def ldap_login(
    login_data: LDAPLoginRequest,
    db: AsyncSession = Depends(get_slm_db),
) -> dict:
    """Authenticate via LDAP/Active Directory."""
    logger.info("LDAP login attempt for user: %s", login_data.username)
    context = TenantContext(is_platform_admin=False)
    sso_service = SSOService(db, context)

    try:
        user = await sso_service.authenticate_ldap(
            login_data.provider_id,
            login_data.username,
            login_data.password,
        )

        # Convert User ORM object to dict-like structure for auth_service
        user_dict = type(
            "User",
            (),
            {
                "username": user.username,
                "is_admin": (user.is_platform_admin if hasattr(user, "is_platform_admin") else False),
            },
        )()

        token_response = await auth_service.create_token_response(user_dict)
        return {
            "access_token": token_response.access_token,
            "token_type": token_response.token_type,
            "expires_in": token_response.expires_in,
        }
    except SSOAuthenticationError as e:
        logger.error("LDAP login failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Internal server error",
        ) from e
    except SSOProviderNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Internal server error",
        ) from e


@router.post("/saml/callback")
async def saml_callback(
    SAMLResponse: str = Form(...),
    RelayState: str = Form(None),
    db: AsyncSession = Depends(get_slm_db),
) -> RedirectResponse:
    """Handle SAML assertion callback."""
    logger.info("Processing SAML callback")
    context = TenantContext(is_platform_admin=False)
    sso_service = SSOService(db, context)

    try:
        # Extract provider_id from RelayState
        from user_management.services.sso_service import _oauth_states

        provider_id = _oauth_states.pop(RelayState, None)
        if not provider_id:
            raise SSOAuthenticationError("Invalid SAML RelayState")

        user = await sso_service.complete_saml_login(provider_id, SAMLResponse)

        # Convert User ORM object to dict-like structure for auth_service
        user_dict = type(
            "User",
            (),
            {
                "username": user.username,
                "is_admin": (user.is_platform_admin if hasattr(user, "is_platform_admin") else False),
            },
        )()

        token_response = await auth_service.create_token_response(user_dict)
        return RedirectResponse(
            url=f"/?token={token_response.access_token}",
            status_code=status.HTTP_302_FOUND,
        )
    except SSOAuthenticationError as e:
        logger.error("SAML callback failed: %s", e)
        return RedirectResponse(
            url="/login?error=sso_failed",
            status_code=status.HTTP_302_FOUND,
        )
