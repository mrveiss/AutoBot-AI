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
POST /api/llm-auth/oauth/initiate          — mint PKCE+state, return provider authorize URL
POST /api/llm-auth/oauth/callback          — state-bound single-use code exchange + persist tokens
POST /api/llm-auth/device/initiate         — begin device-code flow
POST /api/llm-auth/device/poll             — poll for device-code approval + persist
GET  /api/llm-auth/status/{provider_name}  — check whether a provider has a stored token
DELETE /api/llm-auth/{provider_name}       — revoke / delete stored tokens
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.user_management.dependencies import get_db_session
from auth_middleware import check_admin_permission, get_current_user
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import client_get, client_getdel, client_setex, get_redis_client
from autobot_shared.url_safety import get_oauth_allowed_hosts, require_allowlisted_https
from llm_shared.provider_auth import (
    _vault_read_dual,
    _vault_write,
    build_token_data,
    org_vault_subject,
    validate_token_response,
)

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# SSRF allowlist — hosts that provider OAuth/token endpoints may live on.
# The list lives in autobot_shared.url_safety (single source of truth).
# Override at runtime via AUTOBOT_PROVIDER_OAUTH_ALLOWED_HOSTS (comma-separated).
# ---------------------------------------------------------------------------


def _validate_outbound_url(url: str) -> None:
    """Reject URLs that could cause SSRF (any violation → HTTP 400).

    Delegates the https / IP-literal / allowlist / port-pinning rules to the shared
    ``require_allowlisted_https`` guard in ``autobot_shared.url_safety`` so there is
    a single SSRF module (#11091 item 3), translating its ``ValueError`` into an
    HTTP 400. The allowlist is evaluated at call time via ``get_oauth_allowed_hosts()``
    so AUTOBOT_PROVIDER_OAUTH_ALLOWED_HOSTS env-var overrides are always respected.
    """
    try:
        require_allowlisted_https(url, get_oauth_allowed_hosts())
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


async def _reject_redirect(resp, what: str) -> None:
    """Turn an un-followed 3xx into a clean 502 (#13311).

    ``allow_redirects=False`` stops a compromised-but-allowlisted provider
    redirecting us to an internal host, but neither caller handled what comes
    back: ``device_initiate`` only rejected ``>= 400`` and then indexed the
    absent ``device_code``, and ``device_poll`` called ``resp.json()`` on an
    HTML redirect body. Both raised an unhandled 500. A 3xx is never a valid
    answer here, so say so.
    """
    if not 300 <= resp.status < 400:
        return
    location = resp.headers.get("Location", "") if hasattr(resp, "headers") else ""
    logger.warning("%s returned HTTP %s; redirects are disabled (SSRF guard)", what, resp.status)
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=f"{what} redirected (HTTP {resp.status}); redirects are disabled to prevent SSRF{location and ' -> ' + location[:100]}",
    )


async def _pinned_connector(url: str):
    """Resolve *url* once, assert it is public, and return an IP-pinned connector.

    Finding #2 (#11497): the outbound token/device POST connects to the
    pre-resolved public IP so DNS cannot be rebound to a private address between
    the allowlist check and the socket connect. Translates an SSRF failure into
    HTTP 400. Callers must pass the returned connector to their ClientSession /
    ``exchange_code`` so the session owns and closes it.
    """
    from autobot_shared.security.ssrf_guard import SSRFError, pinned_connector  # noqa: PLC0415

    try:
        return await pinned_connector(url)
    except SSRFError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


# The registry/app-factory prepends "/api" (see feature_routers.py), so this
# router carries only "/llm-auth" → resolves to /api/llm-auth. A "/api/llm-auth"
# prefix here would wrongly yield /api/api/llm-auth and 404 every OAuth call
# (matches the #9864 budget-policies fix; the frontend calls /api/llm-auth/*). #11092
router = APIRouter(prefix="/llm-auth", tags=["llm-auth"])

# System vault string — provider-level tokens live in the system vault. Within it,
# each token's SUBJECT is keyed to the caller's org/tenant (finding #1, #11497) so
# an admin connects once and only that org shares the connection; orgs are isolated
# from one another. A single-tenant deployment (no org_id) keeps the legacy
# "global" subject, so its behaviour is unchanged.
_SYSTEM_VAULT = "system"

# OAuth authorize state is single-use and short-lived — a security window, not a
# cache (#11297). Overridable via env; keyed to the initiating admin in Redis.
_OAUTH_STATE_TTL_SECONDS = int(os.getenv("AUTOBOT_PROVIDER_OAUTH_STATE_TTL_SECONDS", "600"))
_OAUTH_STATE_PREFIX = "llm-auth:oauth:state:"


def _state_key(state: str) -> str:
    return "%s%s" % (_OAUTH_STATE_PREFIX, state)


# Device-code poll limiter (#11061): honor RFC-8628 server-side — reject polls
# faster than the current interval, back off +5s on ``slow_down``, and cap total
# attempts per device_code. All overridable via env.
_DEVICE_POLL_MIN_INTERVAL = int(os.getenv("AUTOBOT_DEVICE_POLL_MIN_INTERVAL_SECONDS", "5"))
_DEVICE_POLL_BACKOFF = int(os.getenv("AUTOBOT_DEVICE_POLL_BACKOFF_SECONDS", "5"))
_DEVICE_POLL_MAX_ATTEMPTS = int(os.getenv("AUTOBOT_DEVICE_POLL_MAX_ATTEMPTS", "360"))
_DEVICE_POLL_WINDOW = int(os.getenv("AUTOBOT_DEVICE_POLL_WINDOW_SECONDS", "1800"))
_DEVICE_POLL_PREFIX = "llm-auth:device:poll:"


def _device_poll_key(device_code: str) -> str:
    # Hash the device_code so the raw grant secret never becomes a Redis key.
    return "%s%s" % (_DEVICE_POLL_PREFIX, hashlib.sha256(device_code.encode("utf-8")).hexdigest())


# Redis single-use-state helpers (client_setex / client_getdel / client_get)
# now live in autobot_shared.redis_client — see Issue #11699.


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class OAuthInitiateRequest(BaseModel):
    """Body for POST /oauth/initiate — starts a server-driven PKCE auth-code flow."""

    provider_name: str
    authorize_url: str
    token_url: str
    client_id: str
    redirect_uri: str
    scopes: Optional[List[str]] = None


class OAuthAuthorizeResponse(BaseModel):
    """Return of /oauth/initiate — the provider URL to redirect to + the CSRF state."""

    authorize_url: str
    state: str


class OAuthCallbackRequest(BaseModel):
    """Body for POST /oauth/callback — bound to a server-minted, single-use state.

    The verifier / token_url / client_id are taken from the stored state, never
    from the client, so a lured admin cannot inject an attacker's credentials.
    """

    state: str
    code: str
    redirect_uri: str


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
    """Return the calling principal's id as a string, or the zero-UUID when absent.

    ``get_current_user`` yields a **dict** principal in every production branch
    (``user_id`` is the canonical claim key, #11849), so read dict keys first;
    an object principal (tests / other callers) still resolves via ``getattr``.
    The zero-UUID is returned only for a genuinely id-less principal — otherwise
    the #11297 admin-binding would collapse every real admin to the same id and
    let a lured admin B complete admin A's minted OAuth state.
    """
    if isinstance(user, dict):
        uid = user.get("user_id") or user.get("id")
    else:
        uid = getattr(user, "user_id", None) or getattr(user, "id", None)
    if uid is None:
        return "00000000-0000-0000-0000-000000000000"
    return str(uid)


def _current_org_id(user: Any) -> str | None:
    """Return the caller's org/tenant id, or None when not multi-tenant.

    ``get_current_user`` yields a dict principal carrying ``org_id`` when the JWT
    was minted with an org claim (#11497 finding #1). Objects are supported too
    so tests/other principals work. None → the token stays on the legacy
    ``"global"`` subject (single-tenant: byte-identical to pre-#11497 behaviour).
    """
    if isinstance(user, dict):
        org = user.get("org_id")
    else:
        org = getattr(user, "org_id", None) or getattr(user, "organization_id", None)
    return str(org) if org is not None else None


def _vault_subject(user: Any) -> str:
    """Per-org vault subject for the calling principal (finding #1, #11497)."""
    return org_vault_subject(_current_org_id(user))


# ---------------------------------------------------------------------------
# OAuth authorization-code callback (server-side code exchange)
# ---------------------------------------------------------------------------


@router.post("/oauth/initiate", response_model=OAuthAuthorizeResponse)
async def oauth_initiate(
    req: OAuthInitiateRequest,
    user: Any = Depends(get_current_user),
    _admin: bool = Depends(check_admin_permission),
) -> OAuthAuthorizeResponse:
    """Begin a provider auth-code + PKCE flow; return the authorize URL + state.

    The server mints the PKCE verifier/challenge and an unguessable ``state``,
    stashes them in Redis (short TTL, keyed to the initiating admin), and returns
    the provider authorize URL. The client never supplies the verifier — the
    callback takes it from the stored state (#11297). Requires admin: the stored
    credential is shared by the admin's org (per-org scoped, #11497).
    """
    from knowledge.connectors.oauth_flow import (  # noqa: PLC0415
        OAuthProvider,
        build_authorize_url,
        generate_pkce,
        generate_state,
    )

    # SSRF-validate BOTH outbound URLs before we store or return them.
    _validate_outbound_url(req.authorize_url)
    _validate_outbound_url(req.token_url)

    redis = get_redis_client(database="main")
    if redis is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="OAuth state store unavailable")

    verifier, challenge = generate_pkce()
    state = generate_state()
    scopes = tuple(req.scopes) if req.scopes else None
    provider_cfg = OAuthProvider(
        name=req.provider_name,
        authorize_url=req.authorize_url,
        token_url=req.token_url,
        client_id_setting="",
        client_secret_setting="",  # nosec B106 - setting NAME (empty), not a secret value
        default_scopes=scopes or (),
    )

    payload = {
        "verifier": verifier,
        "admin_id": _current_user_id(user),
        "provider_name": req.provider_name,
        "token_url": req.token_url,
        "client_id": req.client_id,
    }
    await client_setex(redis, _state_key(state), _OAUTH_STATE_TTL_SECONDS, json.dumps(payload, ensure_ascii=False))

    authorize_url = build_authorize_url(provider_cfg, req.client_id, req.redirect_uri, state, challenge, scopes)
    logger.info("OAuth authorize initiated for provider %s", req.provider_name)
    return OAuthAuthorizeResponse(authorize_url=authorize_url, state=state)


@router.post("/oauth/callback", response_model=OAuthInitiateResponse)
async def oauth_callback(
    req: OAuthCallbackRequest,
    session: AsyncSession = Depends(get_db_session),
    user: Any = Depends(get_current_user),
    _admin: bool = Depends(check_admin_permission),
) -> OAuthInitiateResponse:
    """Exchange an OAuth authorization code for tokens and persist to vault.

    Authorized by a server-minted, **single-use** ``state`` (from /oauth/initiate):
    the state is atomically consumed (GETDEL), must belong to the current admin,
    and supplies the verifier / token_url / client_id — none of which the client
    provides. This closes the CSRF / code-injection hole where a lured admin could
    bind an attacker's account as the shared system credential (#11297).

    Requires admin — stored credential is per-org scoped (shared within the admin's org, #11497).
    """
    from knowledge.connectors.oauth_flow import OAuthProvider, exchange_code  # noqa: PLC0415

    redis = get_redis_client(database="main")
    if redis is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="OAuth state store unavailable")

    # Single-use: atomically fetch-and-delete. Missing/expired/replayed → 400.
    raw = await client_getdel(redis, _state_key(req.state))
    if raw is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid or expired OAuth state")
    stored = json.loads(raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else raw)

    # Bind the completing admin to the initiating admin (defends against a lured admin).
    if stored.get("admin_id") != _current_user_id(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="OAuth state does not belong to the current admin"
        )

    token_url = stored["token_url"]
    _validate_outbound_url(token_url)  # defensive re-check before the outbound call
    connector = await _pinned_connector(token_url)  # finding #2: resolve-once + IP pin

    provider_cfg = OAuthProvider(
        name=stored["provider_name"],
        authorize_url="",
        token_url=token_url,
        client_id_setting="",
        client_secret_setting="",  # nosec B106 - setting NAME (empty), not a secret value
    )

    try:
        # Public-client PKCE: the verifier (server-stored) replaces a client secret.
        # SSRF mitigated: token_url passed _validate_outbound_url() (https + host
        # allowlist + port pin) and _pinned_connector() pins the pre-resolved public
        # IP (defeats DNS-rebind); redirects disabled in exchange_code. (#12278)
        resp = await exchange_code(
            provider_cfg,
            stored["client_id"],
            "",  # nosec B106 - PKCE public client: no client_secret
            req.code,
            req.redirect_uri,
            stored["verifier"],
            connector=connector,
        )
    except RuntimeError as exc:
        # Log provider name only — never log code or token values.
        logger.warning("OAuth code exchange failed for provider %s", stored.get("provider_name"))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    # Finding #3: reject a mismatched token_type / issuer / audience before persist.
    try:
        validate_token_response(resp, provider_name=stored["provider_name"], client_id=stored["client_id"])
    except Exception as exc:
        logger.warning("OAuth token validation failed for provider %s", stored.get("provider_name"))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    token_data = build_token_data(resp, created_by=_current_user_id(user))
    await _vault_write(
        session,
        provider_name=stored["provider_name"],
        subject=_vault_subject(user),  # finding #1: per-org scoping
        owner_vault_str=_SYSTEM_VAULT,
        token_data=token_data,
        created_by_id=_current_user_id(user),
    )
    await session.commit()
    logger.info("OAuth token stored for provider %s", stored.get("provider_name"))
    return OAuthInitiateResponse(
        provider_name=stored["provider_name"],
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

    Requires admin — stored credential is per-org scoped (shared within the admin's org, #11497).
    """
    import aiohttp  # noqa: PLC0415

    # Validate outbound URL before any HTTP call — prevents SSRF via device_authorization_url.
    _validate_outbound_url(req.device_authorization_url)
    connector = await _pinned_connector(req.device_authorization_url)  # finding #2: resolve-once + IP pin

    timeout = aiohttp.ClientTimeout(total=30.0)
    payload = {"client_id": req.client_id, "scope": req.scope}
    try:
        async with aiohttp.ClientSession(timeout=timeout, connector=connector) as http:
            # SSRF mitigated: device_authorization_url passed _validate_outbound_url()
            # (https + host allowlist + port pin) and connector pins the pre-resolved
            # public IP (defeats DNS-rebind); redirects disabled. (#12278)
            async with http.post(
                req.device_authorization_url,
                data=payload,
                headers={"Accept": "application/json"},
                allow_redirects=False,
            ) as resp:
                await _reject_redirect(resp, "Device authorization endpoint")
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

    Requires admin — stored credential is per-org scoped (shared within the admin's org, #11497).
    """
    import aiohttp  # noqa: PLC0415

    # Validate outbound URL before any HTTP call — prevents SSRF via token_url.
    _validate_outbound_url(req.token_url)

    # RFC-8628 server-side poll limiter (#11061): reject too-fast polls and cap
    # total attempts BEFORE hitting the provider. Best-effort — skipped if Redis
    # is unavailable so the flow still works in degraded mode.
    redis = get_redis_client(database="main")
    poll_key = _device_poll_key(req.device_code)
    now = time.time()
    poll_state = {"interval": _DEVICE_POLL_MIN_INTERVAL, "count": 0, "last_ts": 0.0}
    if redis is not None:
        raw = await client_get(redis, poll_key)
        if raw:
            poll_state = json.loads(raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else raw)
        if poll_state["count"] >= _DEVICE_POLL_MAX_ATTEMPTS:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="device-code polling attempts exhausted"
            )
        if now - poll_state["last_ts"] < poll_state["interval"]:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="polling too fast; honor the device-code interval",
            )

    payload = {
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        "device_code": req.device_code,
        "client_id": req.client_id,
    }
    connector = await _pinned_connector(req.token_url)  # finding #2: resolve-once + IP pin
    timeout = aiohttp.ClientTimeout(total=30.0)
    try:
        async with aiohttp.ClientSession(timeout=timeout, connector=connector) as http:
            # SSRF mitigated: token_url passed _validate_outbound_url() (https + host
            # allowlist + port pin) and connector pins the pre-resolved public IP
            # (defeats DNS-rebind); redirects disabled. (#12278)
            async with http.post(
                req.token_url,
                data=payload,
                headers={"Accept": "application/json"},
                allow_redirects=False,
            ) as resp:
                # A 400 here is normal (RFC-8628 carries `authorization_pending`
                # in a 400 body), so only 3xx is rejected outright.
                await _reject_redirect(resp, "Token endpoint")
                data = await resp.json(content_type=None)
    except aiohttp.ClientError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    error = data.get("error")
    # Update the limiter: on slow_down, back off (+5s, RFC-8628); on a still-pending
    # grant persist the new state; on a terminal outcome clear it.
    if redis is not None:
        if error == "slow_down":
            poll_state["interval"] += _DEVICE_POLL_BACKOFF
        poll_state["count"] += 1
        poll_state["last_ts"] = now
        if error in ("authorization_pending", "slow_down"):
            await client_setex(redis, poll_key, _DEVICE_POLL_WINDOW, json.dumps(poll_state))
        else:
            await client_getdel(redis, poll_key)

    if error in ("authorization_pending", "slow_down"):
        return OAuthInitiateResponse(provider_name=req.provider_name, stored=False)
    if error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=data.get("error_description", error))

    # Finding #3: reject a mismatched token_type / issuer / audience before persist.
    try:
        validate_token_response(data, provider_name=req.provider_name, client_id=req.client_id)
    except Exception as exc:
        logger.warning("Device-code token validation failed for provider %s", req.provider_name)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    token_data = build_token_data(data, created_by=_current_user_id(user))
    await _vault_write(
        session,
        provider_name=req.provider_name,
        subject=_vault_subject(user),  # finding #1: per-org scoping
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
    user: Any = Depends(get_current_user),
    _admin: bool = Depends(check_admin_permission),
) -> ProviderAuthStatus:
    """Return the auth connection status for a provider.

    Dual-read (finding #1, #11497): reports the caller's org-scoped token when
    present, else the legacy ``"global"`` token — so orgs that connected before
    the change still show connected with zero reconnect.
    """
    token_data = await _vault_read_dual(
        session,
        provider_name=provider_name,
        subject=_vault_subject(user),
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

    Requires admin — credential is per-org scoped (shared within the admin's org, #11497).
    """
    from sqlalchemy import delete  # noqa: PLC0415

    from llm_shared.provider_auth import _vault_secret_name  # noqa: PLC0415
    from models.secret import Secret  # noqa: PLC0415

    # Finding #1 (#11497): revoke the caller's org-scoped token. In a single-tenant
    # deployment (no org_id) the subject is the legacy "global" — identical to the
    # pre-#11497 behaviour. Deleting only the org subject keeps other orgs' shared
    # legacy credential intact.
    name = _vault_secret_name(provider_name, _vault_subject(user))
    await session.execute(delete(Secret).where(Secret.name == name, Secret.owner_vault == _SYSTEM_VAULT))
    await session.commit()
    logger.info("Revoked provider auth tokens for %s (user=%s)", provider_name, _current_user_id(user))


__all__ = ["router"]
