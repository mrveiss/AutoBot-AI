# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
SSO Authentication API

Public endpoints for SSO login flows (OAuth2, LDAP, SAML).
"""

import logging
import os
import uuid
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.proxy_utils import get_client_ip
from autobot_shared.rate_limiter import RateLimiter
from config import settings
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

# Rate limiters (Security: MVA-3397 M-1)
# SSO login initiation: 10 requests/minute per IP (provider enumeration prevention)
_sso_login_limiter = RateLimiter(
    scope_prefix="sso_login",
    default_tier="anonymous",
    requests_per_minute=10,
    requests_per_hour=300,
)

# OAuth callback: 20 requests/minute per IP (allow legitimate retries)
_sso_callback_limiter = RateLimiter(
    scope_prefix="sso_callback",
    default_tier="anonymous",
    requests_per_minute=20,
    requests_per_hour=600,
)

# LDAP login: 5 requests/minute per username (bruteforce protection)
_ldap_login_limiter = RateLimiter(
    scope_prefix="ldap_login",
    default_tier="anonymous",
    requests_per_minute=5,
    requests_per_hour=150,
)


def _get_allowed_callback_hosts() -> frozenset[str]:
    """Get allowed callback hosts for OAuth redirects (MVA-3542)."""
    hosts = {"localhost", "127.0.0.1"}
    external_url = os.getenv("SLM_EXTERNAL_URL", "")
    if external_url:
        try:
            parsed = urlsplit(external_url)
            hostname = (parsed.hostname or "").lower().rstrip(".")
            if hostname:
                hosts.add(hostname)
        except Exception as e:
            logger.warning("Failed to parse SLM_EXTERNAL_URL: %s", e)
    return frozenset(hosts)


_ALLOWED_CALLBACK_HOSTS = _get_allowed_callback_hosts()


async def get_slm_db():
    """Dependency for SLM database session."""
    async with get_slm_session() as session:
        yield session


def _build_callback_url(request: Request) -> str:
    """Build OAuth2 callback URL with security validation (MVA-3542)."""
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    raw_host = request.headers.get("x-forwarded-host", request.url.netloc) or ""

    # Block malicious characters (MVA-3542: SSRF/CRLF prevention)
    if any(c in raw_host for c in "@/\\#?"):
        logger.error("OAuth callback rejected: malicious characters", extra={"host": raw_host})
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid callback host")

    # Parse with urlsplit to prevent parser differential attacks
    try:
        parsed = urlsplit(f"//{raw_host}")
        hostname = (parsed.hostname or "").lower().rstrip(".")
    except Exception as e:
        logger.error("OAuth callback rejected: parse failed", extra={"host": raw_host, "error": str(e)})
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid callback host") from e

    # Validate hostname against allowlist
    if not hostname or hostname not in _ALLOWED_CALLBACK_HOSTS:
        logger.error("OAuth callback rejected: not in allowlist", extra={"hostname": hostname})
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid callback host")

    # Reconstruct netloc from validated components
    netloc = hostname + (f":{parsed.port}" if parsed.port else "")
    return f"{scheme}://{netloc}/api/auth/sso/callback"


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
    response: Response,
    db: AsyncSession = Depends(get_slm_db),
) -> SSOLoginInitResponse:
    """Initiate SSO login flow (OAuth2/SAML)."""
    # Rate limiting (MVA-3397 M-1): prevent provider enumeration and state exhaustion
    client_ip = get_client_ip(request, trusted_proxies=settings.trusted_proxies) or "unknown"
    rate_key = f"ip:{client_ip}"

    if not await _sso_login_limiter.acquire(rate_key):
        retry_after = await _sso_login_limiter.get_retry_after_seconds(rate_key)
        response.headers["Retry-After"] = str(retry_after)
        logger.warning(
            "SSO login rate limit exceeded for IP: %s",
            client_ip,
            extra={"ip": client_ip, "retry_after": retry_after},
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please try again later.",
        )

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
    response: Response,
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_slm_db),
) -> RedirectResponse:
    """Handle OAuth2 callback."""
    # Rate limiting (MVA-3397 M-1): prevent callback replay attacks
    client_ip = get_client_ip(request, trusted_proxies=settings.trusted_proxies) or "unknown"
    rate_key = f"ip:{client_ip}"

    if not await _sso_callback_limiter.acquire(rate_key):
        retry_after = await _sso_callback_limiter.get_retry_after_seconds(rate_key)
        response.headers["Retry-After"] = str(retry_after)
        logger.warning(
            "SSO callback rate limit exceeded for IP: %s",
            client_ip,
            extra={"ip": client_ip, "retry_after": retry_after},
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please try again later.",
        )

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
    response: Response,
    db: AsyncSession = Depends(get_slm_db),
) -> dict:
    """Authenticate via LDAP/Active Directory."""
    # Rate limiting (MVA-3397 M-1): prevent LDAP bruteforce attacks
    rate_key = f"username:{login_data.username}"

    if not await _ldap_login_limiter.acquire(rate_key):
        retry_after = await _ldap_login_limiter.get_retry_after_seconds(rate_key)
        response.headers["Retry-After"] = str(retry_after)
        logger.warning(
            "LDAP login rate limit exceeded for username: %s",
            login_data.username,
            extra={"username": login_data.username, "retry_after": retry_after},
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please try again later.",
        )

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
