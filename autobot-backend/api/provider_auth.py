# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Provider auth connect/disconnect endpoints (#10551, #19241).

Provides backend API surface for the "Sign in with {provider}" flow and
device-code grant. Provider endpoints, scopes and the OAuth client come from
the server-side registry (``llm_shared.llm_oauth_registry``) — never from the
client. The OAuth HTTP exchange is delegated to
``knowledge.connectors.oauth_flow``; token storage uses the unified secrets
vault (``services.envelope_secrets_service``).

Every flow runs at a scope (#19241): ``system`` (the org-shared credential,
admin only) or ``user`` (the caller's own provider account).

Routes
------
GET  /api/llm-auth/providers               — sign-in providers + whether each is configured
POST /api/llm-auth/oauth/initiate          — mint PKCE+state, return provider authorize URL
POST /api/llm-auth/oauth/callback          — state-bound single-use code exchange + persist tokens
POST /api/llm-auth/device/initiate         — begin device-code flow
POST /api/llm-auth/device/poll             — poll for device-code approval + persist
GET  /api/llm-auth/status/{provider_name}  — check whether a provider has a stored token
DELETE /api/llm-auth/{provider_name}       — revoke / delete stored tokens
"""

from __future__ import annotations

import time
from typing import Any, Awaitable, Callable, List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from api import provider_auth_flow_state as flow_state
from api.provider_auth_poll_limit import device_poll_key, load_and_check_poll_state, record_poll
from api.provider_auth_scope import (
    current_user_id,
    provider_caller_is_admin,
    resolve_provider_auth_scope,
    subject_for,
    validate_redirect_uri,
)
from api.schemas_llm_auth import (
    AuthScope,
    DeviceInitiateRequest,
    DeviceInitiateResponse,
    DevicePollRequest,
    OAuthAuthorizeResponse,
    OAuthCallbackRequest,
    OAuthInitiateRequest,
    OAuthInitiateResponse,
    ProviderAuthStatus,
    ProviderListing,
    ProviderRevokeResult,
)
from api.user_management.dependencies import get_db_session
from auth_middleware import get_current_user
from auth_rbac import require_role
from autobot_shared.auth.permissions import Role
from autobot_shared.http_egress_guard import assert_public_egress
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_redis_client
from autobot_shared.secret_redaction import redact_text
from autobot_shared.url_safety import get_oauth_allowed_hosts, require_allowlisted_https
from llm_shared.llm_oauth_registry import (
    FLOW_DEVICE,
    FLOW_REDIRECT,
    LLM_OAUTH_PROVIDER_LABELS,
    LlmOAuthClient,
    ProviderNotConfiguredError,
    UnknownProviderError,
    describe_providers,
    resolve_client,
)
from llm_shared.provider_auth import (
    NEEDS_REAUTH_KEY,
    _vault_read_dual,
    _vault_write,
    build_token_data,
    validate_token_response,
)

logger = get_logger(__name__)

# Kept as module names: callers and tests address the state key / principal id here (#11297, #11849).
_state_key = flow_state.state_key
_current_user_id = current_user_id

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
    redirecting us to an internal host; a 3xx is never a valid answer here.
    """
    if not 300 <= resp.status < 400:
        return
    location = resp.headers.get("Location", "")
    logger.warning("%s returned HTTP %s; redirects are disabled (SSRF guard)", what, resp.status)
    target = f" -> {location[:100]}" if location else ""
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=f"{what} redirected (HTTP {resp.status}){target}; redirects are disabled to prevent SSRF",
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
# router carries only "/llm-auth" → resolves to /api/llm-auth (#11092).
router = APIRouter(prefix="/llm-auth", tags=["llm-auth"])

# System vault string — provider-level tokens live in the system vault. Within it,
# each token's SUBJECT is keyed to the org (system scope, #11497) or to the user
# (user scope, #19241), so connections never cross orgs or users.
_SYSTEM_VAULT = "system"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_client(provider_name: str, flow: str | None) -> LlmOAuthClient:
    """Registry lookup → 404 unknown / 400 unconfigured / 503 unreadable secret; SSRF-checks its URLs."""
    from services.provider_key_vault import VaultKeyUnavailableError  # noqa: PLC0415  # heavy import

    try:
        client = resolve_client(provider_name, flow)
    except UnknownProviderError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.args[0]) from exc
    except ProviderNotConfiguredError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except VaultKeyUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    provider = client.provider
    for url in (provider.authorize_url, provider.token_url, provider.device_authorization_url, provider.revocation_url):
        if url:
            _validate_outbound_url(url)
    return client


def _require_known_provider(provider_name: str) -> None:
    """404 unless *provider_name* is a registry provider -- which also keeps ``:`` out of the vault name."""
    if provider_name not in LLM_OAUTH_PROVIDER_LABELS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown sign-in provider")


def _main_redis():
    redis = get_redis_client(database="main")
    flow_state.require_redis(redis)
    return redis


def _client_auth(client: LlmOAuthClient) -> dict:
    """The client-identifying form fields for a device-flow POST."""
    fields = {"client_id": client.client_id}
    if client.client_secret:
        fields["client_secret"] = client.client_secret
    return fields


async def _post_form(url: str, payload: dict, what: str, handle: Callable[[Any], Awaitable[Any]]) -> Any:
    """POST *payload* to a registry endpoint (SSRF-pinned, no redirects) and return ``handle(response)``.

    A transport error, an egress refusal or an unparseable body is a 502 with a redacted detail.
    """
    import aiohttp  # noqa: PLC0415

    try:
        await assert_public_egress(url)  # public-only (#17576)
        connector = await _pinned_connector(url)  # finding #2: resolve-once + IP pin
        timeout = aiohttp.ClientTimeout(total=30.0)
        async with aiohttp.ClientSession(timeout=timeout, connector=connector) as http:
            # SSRF: url passed _validate_outbound_url() in _resolve_client + assert_public_egress();
            # the connector pins the pre-resolved public IP; redirects disabled. (#12278, #17576)
            async with http.post(url, data=payload, headers={"Accept": "application/json"}, allow_redirects=False) as r:
                await _reject_redirect(r, what)
                return await handle(r)
    except (aiohttp.ClientError, ValueError) as exc:  # ValueError: a non-JSON body (#19241)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=redact_text(str(exc))) from exc


async def _error_detail(r, what: str) -> HTTPException:
    body = redact_text((await r.text())[:200])
    logger.warning("%s answered HTTP %s: %s", what, r.status, body)
    return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"{what} failed: {body}")


async def _post_provider(url: str, payload: dict, what: str, *, reject_errors: bool) -> dict:
    """POST to a registry endpoint and return its JSON body; with *reject_errors*, a 4xx/5xx is a 502."""

    async def _json(r) -> dict:
        if reject_errors and r.status >= 400:
            raise await _error_detail(r, what)
        body = await r.json(content_type=None)
        if not isinstance(body, dict):
            raise ValueError(f"{what} answered with a non-object JSON body")
        return body

    return await _post_form(url, payload, what, _json)


async def _persist(session, user: Any, ctx: dict, resp: dict, client_id: str) -> OAuthInitiateResponse:
    """Validate a token response and store it under the flow's own scope/subject."""
    provider_name = ctx["provider_name"]
    try:  # finding #3: reject a mismatched token_type / issuer / audience before persist
        validate_token_response(resp, provider_name=provider_name, client_id=client_id)
    except Exception as exc:
        logger.warning("Token validation failed for provider %s", provider_name)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    token_data = build_token_data(resp, created_by=_current_user_id(user))
    await _vault_write(
        session,
        provider_name=provider_name,
        subject=ctx["subject"],
        owner_vault_str=_SYSTEM_VAULT,
        token_data=token_data,
        created_by_id=_current_user_id(user),
    )
    await session.commit()
    logger.info("Provider token stored for %s (scope=%s)", provider_name, ctx["scope"])
    return OAuthInitiateResponse(
        provider_name=provider_name, stored=True, expires_at=token_data.get("expires_at"), scope=ctx["scope"]
    )


def _flow_context(user: Any, provider_name: str, scope: str) -> dict:
    """What a completing request is bound to: initiator, provider, scope and vault subject."""
    return {
        "initiator_id": _current_user_id(user),
        "provider_name": provider_name,
        "scope": scope,
        "subject": subject_for(scope, user),
    }


def _require_completion_allowed(ctx: dict, user: Any, is_admin: bool) -> None:
    """The completing caller must be the initiator; a system flow also still needs admin."""
    flow_state.require_initiator(ctx, _current_user_id(user))
    resolve_provider_auth_scope(ctx.get("scope"), is_admin)


# ---------------------------------------------------------------------------
# Provider listing
# ---------------------------------------------------------------------------


@router.get("/providers", response_model=List[ProviderListing])
async def list_providers(user: Any = Depends(get_current_user)) -> List[ProviderListing]:
    """List the sign-in providers, their configured flows and missing setting NAMES — never a value."""
    return [ProviderListing(**row) for row in describe_providers()]


# ---------------------------------------------------------------------------
# OAuth authorization-code flow (server-side code exchange)
# ---------------------------------------------------------------------------


@router.post("/oauth/initiate", response_model=OAuthAuthorizeResponse)
async def oauth_initiate(
    req: OAuthInitiateRequest,
    user: Any = Depends(get_current_user),
    is_admin: bool = Depends(provider_caller_is_admin),
) -> OAuthAuthorizeResponse:
    """Begin a provider auth-code + PKCE flow; return the authorize URL + state.

    The provider and client come from the registry; ``redirect_uri`` must be on
    the SSOT frontend origin. The server mints the PKCE verifier and a single-use
    ``state`` bound to the caller, scope and subject (#11297, #19241).
    """
    from knowledge.connectors.oauth_flow import build_authorize_url, generate_pkce, generate_state  # noqa: PLC0415

    ctx = _flow_context(user, req.provider_name, resolve_provider_auth_scope(req.scope, is_admin))
    client = _resolve_client(req.provider_name, FLOW_REDIRECT)
    validate_redirect_uri(req.redirect_uri)
    redis = _main_redis()
    verifier, challenge = generate_pkce()
    state = generate_state()
    payload = {**ctx, "verifier": verifier, "redirect_uri": req.redirect_uri}
    await flow_state.save(redis, _state_key(state), flow_state.OAUTH_STATE_TTL_SECONDS, payload)
    authorize_url = build_authorize_url(client.provider, client.client_id, req.redirect_uri, state, challenge)
    logger.info("OAuth authorize initiated for provider %s (scope=%s)", req.provider_name, ctx["scope"])
    return OAuthAuthorizeResponse(authorize_url=authorize_url, state=state)


async def _exchange(client: LlmOAuthClient, code: str, redirect_uri: str, verifier: str) -> dict:
    """Exchange *code* at the registry token endpoint (SSRF-pinned; secret sent only if configured)."""
    from knowledge.connectors.oauth_flow import exchange_code  # noqa: PLC0415

    try:
        await assert_public_egress(client.provider.token_url)  # public-only, like the device flow (#17576)
    except ValueError as exc:  # EgressBlockedError
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=redact_text(str(exc))) from exc
    connector = await _pinned_connector(client.provider.token_url)  # finding #2: resolve-once + IP pin
    try:
        # SSRF mitigated: token_url passed _validate_outbound_url() in _resolve_client and
        # _pinned_connector() pins the public IP; redirects disabled in exchange_code. (#12278)
        return await exchange_code(
            client.provider, client.client_id, client.client_secret, code, redirect_uri, verifier, connector=connector
        )
    except RuntimeError as exc:
        # Log provider name only — never log code or token values.
        logger.warning("OAuth code exchange failed for provider %s", client.provider.name)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=redact_text(str(exc))) from exc


@router.post("/oauth/callback", response_model=OAuthInitiateResponse)
async def oauth_callback(
    req: OAuthCallbackRequest,
    session: AsyncSession = Depends(get_db_session),
    user: Any = Depends(get_current_user),
    is_admin: bool = Depends(provider_caller_is_admin),
) -> OAuthInitiateResponse:
    """Exchange an OAuth authorization code for tokens and persist to the vault.

    Authorized by a server-minted, **single-use** ``state``: atomically consumed
    (GETDEL), it must belong to the caller and supplies the verifier, provider,
    scope and subject — none of which the client provides (#11297). The token is
    written to the scope the flow started with (#19241).
    """
    redis = _main_redis()
    stored = await flow_state.consume_oauth_state(redis, req.state, _current_user_id(user))
    _require_completion_allowed(stored, user, is_admin)
    if req.redirect_uri != stored.get("redirect_uri"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="redirect_uri does not match the flow")
    client = _resolve_client(stored["provider_name"], FLOW_REDIRECT)
    resp = await _exchange(client, req.code, req.redirect_uri, stored["verifier"])
    return await _persist(session, user, stored, resp, client.client_id)


# ---------------------------------------------------------------------------
# Device-code flow
# ---------------------------------------------------------------------------


def _device_instructions(data: dict) -> DeviceInitiateResponse:
    """The provider's device-authorization answer, or 502 when it is unusable.

    ``verification_uri`` is shown to the user as a link, so only an https URL is accepted (#19241).
    """
    uri = str(data.get("verification_uri") or data.get("verification_url") or "")
    if not data.get("device_code") or not data.get("user_code") or not uri.lower().startswith("https://"):
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="device authorization answer is unusable")
    try:
        expires_in, interval = int(data.get("expires_in", 1800)), int(data.get("interval", 5))
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="device authorization answer is unusable"
        ) from exc
    return DeviceInitiateResponse(
        device_code=data["device_code"],
        user_code=data["user_code"],
        verification_uri=uri,
        expires_in=expires_in,
        interval=interval,
    )


@router.post("/device/initiate", response_model=DeviceInitiateResponse)
async def device_initiate(
    req: DeviceInitiateRequest,
    user: Any = Depends(get_current_user),
    is_admin: bool = Depends(provider_caller_is_admin),
) -> DeviceInitiateResponse:
    """Start a device-code flow at the registry's device endpoint (RFC 8628).

    Returns the ``user_code`` + ``verification_uri``; the context (caller, scope,
    subject) is held server-side so /device/poll stores to the right place.
    """
    ctx = _flow_context(user, req.provider_name, resolve_provider_auth_scope(req.scope, is_admin))
    client = _resolve_client(req.provider_name, FLOW_DEVICE)
    redis = _main_redis()
    payload = {**_client_auth(client), "scope": " ".join(client.provider.default_scopes)}
    url = client.provider.device_authorization_url
    data = await _post_provider(url, payload, "Device authorization endpoint", reject_errors=True)
    resp = _device_instructions(data)
    await flow_state.save(redis, flow_state.device_context_key(resp.device_code), resp.expires_in, ctx)
    return resp


@router.post("/device/poll", response_model=OAuthInitiateResponse)
async def device_poll(
    req: DevicePollRequest,
    session: AsyncSession = Depends(get_db_session),
    user: Any = Depends(get_current_user),
    is_admin: bool = Depends(provider_caller_is_admin),
) -> OAuthInitiateResponse:
    """Poll the token endpoint for a device-code grant and persist on approval.

    Returns ``stored=False`` while the grant is pending. Only the initiator may
    poll, and the token goes to the scope the flow started with (#19241).
    """
    redis = _main_redis()
    ctx = await flow_state.load_device_context(redis, req.device_code, req.provider_name)
    _require_completion_allowed(ctx, user, is_admin)
    client = _resolve_client(req.provider_name, FLOW_DEVICE)
    # RFC-8628 server-side poll limiter (#11061): reject too-fast polls and cap
    # total attempts BEFORE hitting the provider.
    poll_key, now = device_poll_key(req.device_code), time.time()
    poll_state = await load_and_check_poll_state(redis, poll_key, now)
    grant = {"grant_type": "urn:ietf:params:oauth:grant-type:device_code", "device_code": req.device_code}
    # A 400 is normal here (RFC 8628 carries `authorization_pending` in it).
    data = await _post_provider(
        client.provider.token_url, {**grant, **_client_auth(client)}, "Token endpoint", reject_errors=False
    )
    error = data.get("error")
    await record_poll(redis, poll_key, poll_state, now, error)
    if error in ("authorization_pending", "slow_down"):
        return OAuthInitiateResponse(provider_name=req.provider_name, stored=False, scope=ctx["scope"])
    if error:
        detail = redact_text(str(data.get("error_description") or error))
        logger.warning("Device-code token endpoint refused %s: %s", req.provider_name, detail)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)
    result = await _persist(session, user, ctx, data, client.client_id)
    await flow_state.drop_device_context(redis, req.device_code)
    return result


# ---------------------------------------------------------------------------
# Status + revoke
# ---------------------------------------------------------------------------


@router.get("/status/{provider_name}", response_model=ProviderAuthStatus)
async def provider_auth_status(
    provider_name: str,
    scope: AuthScope = Query(default="user"),
    session: AsyncSession = Depends(get_db_session),
    user: Any = Depends(get_current_user),
    is_admin: bool = Depends(provider_caller_is_admin),
) -> ProviderAuthStatus:
    """Return the caller's connection status for a provider at *scope* (default: the caller's own).

    System scope (admin only) dual-reads (finding #1, #11497): the org-scoped token, else the
    legacy ``"global"`` one. User scope reads only the caller's own token.
    """
    from api.provider_auth_revoke import refuses_shared_subject  # noqa: PLC0415

    _require_known_provider(provider_name)
    effective = resolve_provider_auth_scope(scope, is_admin)
    subject = subject_for(effective, user)
    shared = refuses_shared_subject(effective, subject)  # an org-less admin's system sign-in IS the shared token
    token_data = await _vault_read_dual(
        session, provider_name=provider_name, subject=subject, owner_vault_str=_SYSTEM_VAULT
    )
    if token_data is None:
        return ProviderAuthStatus(provider_name=provider_name, connected=False, scope=effective, shared=shared)
    expires_at = token_data.get("expires_at")
    needs_reauth = bool(token_data.get(NEEDS_REAUTH_KEY))
    return ProviderAuthStatus(
        provider_name=provider_name,
        connected=not needs_reauth and (expires_at is None or time.time() < expires_at),
        expires_at=expires_at,
        auth_kind=token_data.get("auth_kind", "oauth"),
        scope=effective,
        needs_reauth=needs_reauth,
        shared=shared,
    )


@router.delete("/{provider_name}", response_model=ProviderRevokeResult)
async def revoke_provider_auth(
    provider_name: str,
    scope: AuthScope = Query(...),
    session: AsyncSession = Depends(get_db_session),
    user: Any = Depends(get_current_user),
    is_admin: bool = Depends(provider_caller_is_admin),
) -> ProviderRevokeResult:
    """Disconnect the caller's provider sign-in at *scope* (system needs admin).

    *scope* is required (422 without it): a scope-less "disconnect" from an
    admin must never default to deleting the org-shared credential. A
    multi-tenant system disconnect leaves a per-org stop marker; see
    ``api.provider_auth_revoke``, which also revokes at the provider and audits.
    """
    from api.provider_auth_revoke import disconnect  # noqa: PLC0415

    _require_known_provider(provider_name)
    return await disconnect(session, user, provider_name, resolve_provider_auth_scope(scope, is_admin))


#: The existing RBAC gate, superadmin only: the shared token serves every org (owner decision, #19241).
_require_superadmin = require_role(Role.SUPERADMIN)


@router.delete("/{provider_name}/shared", response_model=ProviderRevokeResult)
async def revoke_shared_provider_auth(
    provider_name: str,
    session: AsyncSession = Depends(get_db_session),
    user: Any = Depends(get_current_user),
    _superadmin: bool = Depends(_require_superadmin),
) -> ProviderRevokeResult:
    """Superadmin: delete the shared legacy ``"global"`` token and revoke it at the provider.

    Every org still falling back to it loses it, which is the point (key
    compromise, account-owner offboarding). Audited like every disconnect.
    """
    from api.provider_auth_revoke import revoke_shared  # noqa: PLC0415

    _require_known_provider(provider_name)
    return await revoke_shared(session, user, provider_name)


__all__ = ["router"]
