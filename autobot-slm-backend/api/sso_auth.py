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
from fastapi.responses import RedirectResponse, Response as RawResponse
from sqlalchemy.ext.asyncio import AsyncSession

from api.security import create_audit_log
from autobot_shared.proxy_utils import get_client_ip
from autobot_shared.rate_limiter import RateLimiter
from config import settings
from services.auth import auth_service
from services.database import get_db
from user_management.database import get_slm_session
from user_management.models.sso import SSOProviderType
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


async def get_audit_db():
    """Dependency for the audit (main SLM security) database session."""
    async for session in get_db():
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
    audit_db: AsyncSession = Depends(get_audit_db),
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

    # provider_id_str starts empty; populated from the service tuple on success.
    # On failure the state is already consumed by complete_oauth_login so it is
    # unavailable — that is acceptable (resource_id="" for failure audit rows).
    provider_id_str = ""

    try:
        callback_url = _build_callback_url(request)
        user, resolved_provider_id = await sso_service.complete_oauth_login(code, state, callback_url)
        provider_id_str = str(resolved_provider_id)

        try:
            await create_audit_log(
                audit_db,
                category="sso",
                action="login",
                user_id=str(user.id),
                username=user.username,
                ip_address=client_ip,
                resource_type="sso_provider",
                resource_id=provider_id_str,
                success=True,
            )
            await audit_db.commit()
        except Exception as audit_err:
            logger.warning("SSO audit write failed: %s", audit_err)

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
        try:
            await create_audit_log(
                audit_db,
                category="sso",
                action="login",
                ip_address=client_ip,
                resource_type="sso_provider",
                resource_id=provider_id_str,
                success=False,
                error_message=str(e),
            )
            await audit_db.commit()
        except Exception as audit_err:
            logger.warning("SSO audit write failed: %s", audit_err)
        return RedirectResponse(
            url="/login?error=sso_failed",
            status_code=status.HTTP_302_FOUND,
        )


@router.post("/ldap/login")
async def ldap_login(
    login_data: LDAPLoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_slm_db),
    audit_db: AsyncSession = Depends(get_audit_db),
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
    provider_id_str = str(login_data.provider_id)

    try:
        user = await sso_service.authenticate_ldap(
            login_data.provider_id,
            login_data.username,
            login_data.password,
        )

        try:
            await create_audit_log(
                audit_db,
                category="sso",
                action="login",
                user_id=str(user.id),
                username=user.username,
                resource_type="sso_provider",
                resource_id=provider_id_str,
                success=True,
            )
            await audit_db.commit()
        except Exception as audit_err:
            logger.warning("SSO audit write failed: %s", audit_err)

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
        try:
            await create_audit_log(
                audit_db,
                category="sso",
                action="login",
                username=login_data.username,
                resource_type="sso_provider",
                resource_id=provider_id_str,
                success=False,
                error_message=str(e),
            )
            await audit_db.commit()
        except Exception as audit_err:
            logger.warning("SSO audit write failed: %s", audit_err)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Internal server error",
        ) from e
    except SSOProviderNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Internal server error",
        ) from e


@router.get("/saml/slo")
@router.post("/saml/slo")
async def saml_slo_callback(
    request: Request,
    db: AsyncSession = Depends(get_slm_db),
    audit_db: AsyncSession = Depends(get_audit_db),
    SAMLRequest: str | None = Form(None),
    SAMLResponse: str | None = Form(None),
    RelayState: str | None = Form(None),
    SigAlg: str | None = Query(None),
    Signature: str | None = Query(None),
) -> RawResponse:
    """Handle SAML Single Logout (SLO) callback from the IdP (#10281).

    Accepts both HTTP-POST (form body) and HTTP-Redirect (query string) bindings.
    The IdP sends a LogoutRequest to initiate SLO or a LogoutResponse to complete
    an SP-initiated SLO.  We validate, terminate the local session, and return
    the appropriate SAML LogoutResponse or redirect.
    """
    from saml2 import BINDING_HTTP_POST, BINDING_HTTP_REDIRECT  # noqa: PLC0415

    client_ip = get_client_ip(request, trusted_proxies=settings.trusted_proxies) or "unknown"
    context = TenantContext(is_platform_admin=False)
    sso_service = SSOService(db, context)

    # Determine binding and payload
    if SAMLRequest or SAMLResponse:
        binding = BINDING_HTTP_POST
        xml_body = SAMLRequest or SAMLResponse
    else:
        # HTTP-Redirect: SAMLRequest/SAMLResponse arrive as query parameters
        binding = BINDING_HTTP_REDIRECT
        xml_body = request.query_params.get("SAMLRequest") or request.query_params.get("SAMLResponse")
        SigAlg = SigAlg or request.query_params.get("SigAlg")
        Signature = Signature or request.query_params.get("Signature")

    if not xml_body:
        logger.warning("SAML SLO callback received with no SAMLRequest or SAMLResponse (ip=%s)", client_ip)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing SAMLRequest or SAMLResponse")

    # Resolve the SAML provider — SLO does not carry a provider ID, look up by type
    providers, _ = await sso_service.list_providers(active_only=True)
    saml_providers = [p for p in providers if p.provider_type == SSOProviderType.SAML.value]
    if not saml_providers:
        logger.error("SAML SLO callback: no active SAML provider configured (ip=%s)", client_ip)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No active SAML provider")

    provider = saml_providers[0]

    try:
        success, redirect_url = sso_service.handle_saml_slo_callback(
            provider, xml_body, binding, sigalg=SigAlg, signature=Signature
        )
    except SSOAuthenticationError as exc:
        logger.warning("SAML SLO validation failed (ip=%s): %s", client_ip, exc)
        try:
            await create_audit_log(
                audit_db,
                category="sso",
                action="slo_callback_failed",
                ip_address=client_ip,
                resource_type="sso_provider",
                resource_id=str(provider.id),
                success=False,
                error_message=str(exc),
            )
            await audit_db.commit()
        except Exception:
            pass
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="SAML SLO validation failed") from exc

    try:
        await create_audit_log(
            audit_db,
            category="sso",
            action="slo_callback",
            ip_address=client_ip,
            resource_type="sso_provider",
            resource_id=str(provider.id),
            success=success,
        )
        await audit_db.commit()
    except Exception as audit_err:
        logger.warning("SAML SLO audit write failed: %s", audit_err)

    if redirect_url:
        return RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)
    return RawResponse(content="<p>Logged out</p>", status_code=status.HTTP_200_OK, media_type="text/html")


@router.post("/saml/callback")
async def saml_callback(
    SAMLResponse: str = Form(...),
    RelayState: str = Form(None),
    db: AsyncSession = Depends(get_slm_db),
    audit_db: AsyncSession = Depends(get_audit_db),
) -> RedirectResponse:
    """Handle SAML assertion callback."""
    logger.info("Processing SAML callback")
    context = TenantContext(is_platform_admin=False)
    sso_service = SSOService(db, context)

    # provider_id_str is populated once we validate the relay state via the
    # service.  On failure before that point it remains "".
    provider_id_str = ""

    try:
        provider_id, _ = await sso_service._validate_oauth_state(RelayState)
        provider_id_str = str(provider_id)
        user, _ = await sso_service.complete_saml_login(provider_id, SAMLResponse)

        try:
            await create_audit_log(
                audit_db,
                category="sso",
                action="login",
                user_id=str(user.id),
                username=user.username,
                resource_type="sso_provider",
                resource_id=provider_id_str,
                success=True,
            )
            await audit_db.commit()
        except Exception as audit_err:
            logger.warning("SSO audit write failed: %s", audit_err)

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
        try:
            await create_audit_log(
                audit_db,
                category="sso",
                action="login",
                resource_type="sso_provider",
                resource_id=provider_id_str,
                success=False,
                error_message=str(e),
            )
            await audit_db.commit()
        except Exception as audit_err:
            logger.warning("SSO audit write failed: %s", audit_err)
        return RedirectResponse(
            url="/login?error=sso_failed",
            status_code=status.HTTP_302_FOUND,
        )
