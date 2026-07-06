# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Provider auth connect/disconnect endpoints (#10551).

Provides backend API surface for the "Sign in with {provider}" flow and
device-code grant.  The actual OAuth HTTP exchange is delegated to
``knowledge.connectors.oauth_flow``; token storage uses the unified secrets
vault (``services.envelope_secrets_service``).

Routes
------
POST /api/llm-auth/oauth/initiate          — begin authorization-code flow
POST /api/llm-auth/oauth/callback          — exchange code + persist tokens
POST /api/llm-auth/device/initiate         — begin device-code flow
POST /api/llm-auth/device/poll             — poll for device-code approval + persist
GET  /api/llm-auth/status/{provider_name}  — check whether a provider has a stored token
DELETE /api/llm-auth/{provider_name}       — revoke / delete stored tokens
"""

from __future__ import annotations

import ipaddress
import os
import time
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.user_management.dependencies import get_db_session
from auth_middleware import check_admin_permission, get_current_user
from autobot_shared.logging_manager import get_logger
from llm_shared.provider_auth import (
    _vault_read,
    _vault_write,
    build_token_data,
)

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# SSRF allowlist — hosts that provider OAuth/token endpoints may live on.
# Override via AUTOBOT_PROVIDER_OAUTH_ALLOWED_HOSTS (comma-separated hostnames).
# ---------------------------------------------------------------------------

_DEFAULT_ALLOWED_HOSTS: frozenset[str] = frozenset(
    {
        "accounts.google.com",
        "oauth2.googleapis.com",
        "github.com",
        "api.github.com",
        "huggingface.co",
        "login.microsoftonline.com",
        "api.openai.com",
        "auth.openai.com",
        "api.anthropic.com",
        "api.mistral.ai",
    }
)

_ALLOWED_OAUTH_HOSTS: frozenset[str] = (
    frozenset(h.strip().lower() for h in os.environ["AUTOBOT_PROVIDER_OAUTH_ALLOWED_HOSTS"].split(",") if h.strip())
    if os.environ.get("AUTOBOT_PROVIDER_OAUTH_ALLOWED_HOSTS")
    else _DEFAULT_ALLOWED_HOSTS
)


def _validate_outbound_url(url: str) -> None:
    """Reject URLs that could cause SSRF.

    Rules enforced (any violation → HTTP 400):
    - Scheme must be ``https``.
    - Host must not parse as a valid IP address (blocks 127.0.0.1, 10.x,
      169.254.169.254, ::1, etc.).
    - Host must be present in the configured allowlist.
    """
    try:
        parsed = urlparse(url)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid URL")

    if parsed.scheme != "https":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only https URLs are permitted")

    host = parsed.hostname or ""
    if not host:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="URL has no host")

    try:
        ipaddress.ip_address(host)
        # If ip_address() succeeds the host is an IP literal — reject unconditionally.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="IP-literal hosts are not permitted")
    except ValueError:
        pass  # Not an IP address — continue to allowlist check.

    if host.lower() not in _ALLOWED_OAUTH_HOSTS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Host '{host}' is not in the provider OAuth allowlist",
        )

router = APIRouter(prefix="/api/llm-auth", tags=["llm-auth"])

# System vault string — provider-level tokens are scoped to the system vault so
# all authenticated users can use the shared provider connection.
_SYSTEM_VAULT = "system"


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class OAuthInitiateRequest(BaseModel):
    provider_name: str
    token_url: str
    client_id: str
    client_secret: str
    code: str
    redirect_uri: str
    code_verifier: str


class OAuthInitiateResponse(BaseModel):
    provider_name: str
    stored: bool
    expires_at: float | None = None


class DeviceInitiateRequest(BaseModel):
    provider_name: str
    device_authorization_url: str
    client_id: str
    scope: str = "openid"


class DeviceInitiateResponse(BaseModel):
    device_code: str
    user_code: str
    verification_uri: str
    expires_in: int
    interval: int


class DevicePollRequest(BaseModel):
    provider_name: str
    token_url: str
    client_id: str
    device_code: str


class ProviderAuthStatus(BaseModel):
    provider_name: str
    connected: bool
    expires_at: float | None = None
    auth_kind: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _current_user_id(user: Any) -> str:
    uid = getattr(user, "id", None) or getattr(user, "user_id", None)
    if uid is None:
        return "00000000-0000-0000-0000-000000000000"
    return str(uid)


# ---------------------------------------------------------------------------
# OAuth authorization-code callback (server-side code exchange)
# ---------------------------------------------------------------------------


@router.post("/oauth/callback", response_model=OAuthInitiateResponse)
async def oauth_callback(
    req: OAuthInitiateRequest,
    session: AsyncSession = Depends(get_db_session),
    user: Any = Depends(get_current_user),
    _admin: bool = Depends(check_admin_permission),
) -> OAuthInitiateResponse:
    """Exchange an OAuth authorization code for tokens and persist to vault.

    The frontend redirects to this endpoint after the user completes the
    provider sign-in page.  The backend performs the PKCE code exchange and
    stores the resulting token pair in the system vault.

    Requires admin — stored credential is system-wide (shared by all users).
    """
    from knowledge.connectors.oauth_flow import OAuthProvider, exchange_code  # noqa: PLC0415

    # Validate outbound URL before any HTTP call — prevents SSRF via token_url.
    _validate_outbound_url(req.token_url)

    # Build a minimal OAuthProvider for the exchange helper.
    provider_cfg = OAuthProvider(
        name=req.provider_name,
        authorize_url="",
        token_url=req.token_url,
        client_id_setting="",
        client_secret_setting="",
    )

    try:
        resp = await exchange_code(
            provider_cfg,
            req.client_id,
            req.client_secret,
            req.code,
            req.redirect_uri,
            req.code_verifier,
        )
    except RuntimeError as exc:
        # Log provider name only — never log code, client_secret, or token values.
        logger.warning("OAuth code exchange failed for provider %s", req.provider_name)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    token_data = build_token_data(resp, created_by=_current_user_id(user))
    await _vault_write(
        session,
        provider_name=req.provider_name,
        subject="global",
        owner_vault_str=_SYSTEM_VAULT,
        token_data=token_data,
        created_by_id=_current_user_id(user),
    )
    await session.commit()
    logger.info("OAuth token stored for provider %s", req.provider_name)
    return OAuthInitiateResponse(
        provider_name=req.provider_name,
        stored=True,
        expires_at=token_data.get("expires_at"),
    )


# ---------------------------------------------------------------------------
# Device-code flow
# ---------------------------------------------------------------------------


@router.post("/device/initiate", response_model=DeviceInitiateResponse)
async def device_initiate(
    req: DeviceInitiateRequest,
    user: Any = Depends(get_current_user),
    _admin: bool = Depends(check_admin_permission),
) -> DeviceInitiateResponse:
    """Start a device-code flow.

    Calls the provider's device authorization endpoint and returns the
    ``user_code`` + ``verification_uri`` for the user to complete on another device.
    The caller polls ``/device/poll`` until approval or expiry.

    Requires admin — stored credential is system-wide (shared by all users).
    """
    import aiohttp  # noqa: PLC0415

    # Validate outbound URL before any HTTP call — prevents SSRF via device_authorization_url.
    _validate_outbound_url(req.device_authorization_url)

    timeout = aiohttp.ClientTimeout(total=30.0)
    payload = {"client_id": req.client_id, "scope": req.scope}
    try:
        async with aiohttp.ClientSession(timeout=timeout) as http:
            async with http.post(
                req.device_authorization_url,
                data=payload,
                headers={"Accept": "application/json"},
                allow_redirects=False,
            ) as resp:
                if resp.status >= 400:
                    body = await resp.text()
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail=f"Device authorization failed: {body[:200]}",
                    )
                data = await resp.json(content_type=None)
    except aiohttp.ClientError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    return DeviceInitiateResponse(
        device_code=data["device_code"],
        user_code=data["user_code"],
        verification_uri=data.get("verification_uri") or data.get("verification_url", ""),
        expires_in=int(data.get("expires_in", 1800)),
        interval=int(data.get("interval", 5)),
    )


@router.post("/device/poll", response_model=OAuthInitiateResponse)
async def device_poll(
    req: DevicePollRequest,
    session: AsyncSession = Depends(get_db_session),
    user: Any = Depends(get_current_user),
    _admin: bool = Depends(check_admin_permission),
) -> OAuthInitiateResponse:
    """Poll the token endpoint for a device-code grant and persist on approval.

    Returns ``stored=False`` when the grant is still pending (caller should
    retry after the ``interval`` from ``/device/initiate``).

    Requires admin — stored credential is system-wide (shared by all users).
    """
    import aiohttp  # noqa: PLC0415

    # Validate outbound URL before any HTTP call — prevents SSRF via token_url.
    _validate_outbound_url(req.token_url)

    payload = {
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        "device_code": req.device_code,
        "client_id": req.client_id,
    }
    timeout = aiohttp.ClientTimeout(total=30.0)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as http:
            async with http.post(
                req.token_url,
                data=payload,
                headers={"Accept": "application/json"},
                allow_redirects=False,
            ) as resp:
                data = await resp.json(content_type=None)
    except aiohttp.ClientError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    error = data.get("error")
    if error in ("authorization_pending", "slow_down"):
        return OAuthInitiateResponse(provider_name=req.provider_name, stored=False)
    if error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=data.get("error_description", error))

    token_data = build_token_data(data, created_by=_current_user_id(user))
    await _vault_write(
        session,
        provider_name=req.provider_name,
        subject="global",
        owner_vault_str=_SYSTEM_VAULT,
        token_data=token_data,
        created_by_id=_current_user_id(user),
    )
    await session.commit()
    logger.info("Device-code token stored for provider %s", req.provider_name)
    return OAuthInitiateResponse(
        provider_name=req.provider_name,
        stored=True,
        expires_at=token_data.get("expires_at"),
    )


# ---------------------------------------------------------------------------
# Status + revoke
# ---------------------------------------------------------------------------


@router.get("/status/{provider_name}", response_model=ProviderAuthStatus)
async def provider_auth_status(
    provider_name: str,
    session: AsyncSession = Depends(get_db_session),
    _: Any = Depends(get_current_user),
) -> ProviderAuthStatus:
    """Return the auth connection status for a provider."""
    token_data = await _vault_read(
        session,
        provider_name=provider_name,
        subject="global",
        owner_vault_str=_SYSTEM_VAULT,
    )
    if token_data is None:
        return ProviderAuthStatus(provider_name=provider_name, connected=False)

    expires_at = token_data.get("expires_at")
    still_valid = expires_at is None or time.time() < expires_at
    return ProviderAuthStatus(
        provider_name=provider_name,
        connected=still_valid,
        expires_at=expires_at,
        auth_kind=token_data.get("auth_kind", "oauth"),
    )


@router.delete("/{provider_name}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_provider_auth(
    provider_name: str,
    session: AsyncSession = Depends(get_db_session),
    user: Any = Depends(get_current_user),
    _admin: bool = Depends(check_admin_permission),
) -> None:
    """Revoke stored OAuth / device-code / session tokens for a provider.

    Requires admin — credential is system-wide (shared by all users).
    """
    from sqlalchemy import delete  # noqa: PLC0415

    from llm_shared.provider_auth import _vault_secret_name  # noqa: PLC0415
    from models.secret import Secret  # noqa: PLC0415

    name = _vault_secret_name(provider_name, "global")
    await session.execute(delete(Secret).where(Secret.name == name, Secret.owner_vault == _SYSTEM_VAULT))
    await session.commit()
    logger.info("Revoked provider auth tokens for %s (user=%s)", provider_name, _current_user_id(user))


__all__ = ["router"]
