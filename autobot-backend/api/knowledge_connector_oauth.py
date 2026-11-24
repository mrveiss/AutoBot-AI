# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Connector OAuth 2.0 endpoints (ADR-007 / GH#9019).

Generic, provider-agnostic authorization-code + PKCE flow that lets a user
"Connect <provider>" from the knowledge-base UI.  The resulting refresh/access
tokens are persisted through SecretsService (never custom storage) and returned
by reference (``secret_id``) for attachment to a connector.

- ``authorize`` mints CSRF state + PKCE, stashes them server-side, and returns
  the provider authorization URL.  Requires an authenticated user.
- ``callback`` is reached by the provider's browser redirect; it is authorized
  by the single-use ``state`` token (server-minted), exchanges the code for
  tokens, stores them, and returns an HTML page that hands the ``secret_id``
  back to the opener window.
"""

import html
import json
import uuid
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from auth_middleware import check_admin_permission, get_current_user
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import client_getdel, client_setex, get_redis_client
from autobot_shared.security.constant_time import secure_compare
from autobot_shared.ssot_config import config
from knowledge.connectors import oauth_flow
from knowledge.connectors.credential_store import get_credential_store
from services.credential_read import assert_attachable_secret, find_connector_secret_ids

logger = get_logger(__name__)

router = APIRouter(tags=["knowledge-connectors-oauth"])

# OAuth state is single-use and short-lived; this is a security window, not a cache.
_OAUTH_STATE_TTL_SECONDS = 600
_OAUTH_STATE_PREFIX = "connector:oauth:state:"
# Double-submit cookie binding the completing browser to the initiating one (CSRF).
_OAUTH_STATE_COOKIE = "connector_oauth_state"
# Fixed, non-secret notice for a re-authorization whose replaced credential could not be removed (#13710).
_STALE_CREDENTIAL_WARNING = "A previous credential could not be removed; it will be retried on the next authorization."
_OAUTH_CALLBACK_PATH = "/api/knowledge_base/connectors/oauth/callback"


class AuthorizeRequest(BaseModel):
    """Body for starting a connector OAuth flow."""

    redirect_uri: str
    scopes: list[str] | None = None


class AuthorizeResponse(BaseModel):
    authorize_url: str
    state: str
    connector_id: str


def _state_key(state: str) -> str:
    return "%s%s" % (_OAUTH_STATE_PREFIX, state)


def _validate_redirect_uri(redirect_uri: str) -> None:
    """Reject redirect URIs whose host is not allow-listed (anti-phishing).

    Reuses the SSO callback-host allowlist and HTTPS-enforcement settings.
    """
    parsed = urlparse(redirect_uri)
    if not parsed.scheme or not parsed.hostname:
        raise HTTPException(status_code=422, detail="redirect_uri must be an absolute URL")
    allowed = {h.strip().lower() for h in config.auth.sso_callback_hosts.split(",") if h.strip()}
    if parsed.hostname.lower() not in allowed:
        raise HTTPException(status_code=400, detail="redirect_uri host is not allow-listed")
    if config.auth.enforce_https_callbacks and parsed.scheme != "https":
        raise HTTPException(status_code=400, detail="redirect_uri must use HTTPS")


async def _resolve_flow_owner(prov, user: dict, http_request: Request) -> str:
    """The owner a flow's credential is filed under: the caller, or a service provider's declared owner.

    A service-owned provider (#13710) is connected by an admin only and files ONE shared credential under
    its declared owner; that is the provider's config, not the silent "system" fallback #13628 removed.
    """
    if prov.service_owner_id:
        await check_admin_permission(http_request)
    # #13628: no silent ``or "system"`` fallback. ``get_current_user`` does NOT guarantee ``user_id``: the
    # internal-API-key path returns only ``username`` and SLM-minted JWTs carry ``sub`` (api/voice.py:73).
    owner_id = str(user.get("user_id") or user.get("sub") or user.get("username") or "")
    if not owner_id:
        raise HTTPException(status_code=401, detail="Authenticated caller has no resolvable identity")
    return prov.service_owner_id or owner_id


@router.post("/knowledge_base/connectors/oauth/{provider}/authorize", response_model=AuthorizeResponse)
async def start_oauth(
    provider: str,
    request: AuthorizeRequest,
    response: Response,
    http_request: Request,
    user: dict = Depends(get_current_user),
) -> AuthorizeResponse:
    """Begin a connector OAuth flow; return the provider authorization URL."""
    try:
        prov = oauth_flow.get_provider(provider)
        client_id, _ = oauth_flow.resolve_client_credentials(prov)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    _validate_redirect_uri(request.redirect_uri)
    owner_id = await _resolve_flow_owner(prov, user, http_request)
    state = oauth_flow.generate_state()
    verifier, challenge = oauth_flow.generate_pkce()
    connector_id = prov.service_connector_id or str(uuid.uuid4())
    # #13710: a service-owned provider's consent is pinned to its declared scopes; client scopes are ignored.
    scopes = tuple(request.scopes) if request.scopes and not prov.service_owner_id else None

    payload = {
        "provider": provider,
        "owner_id": owner_id,
        "connector_id": connector_id,
        "code_verifier": verifier,
        "redirect_uri": request.redirect_uri,
        "scopes": list(scopes) if scopes else [],
    }
    redis = get_redis_client(database="knowledge")
    await client_setex(redis, _state_key(state), _OAUTH_STATE_TTL_SECONDS, json.dumps(payload, ensure_ascii=False))

    # Bind the completing browser to this one: the callback requires this cookie
    # to match the returned state (defends against OAuth CSRF / token attachment).
    # SameSite=lax so the cookie rides the top-level provider→callback redirect.
    response.set_cookie(
        _OAUTH_STATE_COOKIE,
        state,
        max_age=_OAUTH_STATE_TTL_SECONDS,
        httponly=True,
        secure=config.auth.enforce_https_callbacks,
        samesite="lax",
        path=_OAUTH_CALLBACK_PATH,
    )

    authorize_url = oauth_flow.build_authorize_url(prov, client_id, request.redirect_uri, state, challenge, scopes)
    return AuthorizeResponse(authorize_url=authorize_url, state=state, connector_id=connector_id)


@router.get("/knowledge_base/connectors/oauth/callback", response_class=HTMLResponse)
async def oauth_callback(
    request: Request,
    state: str = Query(...),
    code: str | None = Query(default=None),
    error: str | None = Query(default=None),
) -> HTMLResponse:
    """Handle the provider redirect: exchange code → store tokens → hand back secret_id."""
    # CSRF binding: the browser completing the flow must be the one that started
    # it (carries the state cookie). Reject before consuming the state token.
    cookie_state = request.cookies.get(_OAUTH_STATE_COOKIE)
    if not cookie_state or not secure_compare(cookie_state, state):
        return _clear_cookie(_result_page(error="state_binding_mismatch"))

    redis = get_redis_client(database="knowledge")
    raw = await client_getdel(redis, _state_key(state))
    if raw is None:
        return _clear_cookie(_result_page(error="invalid_or_expired_state"))
    payload = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)

    if error:
        return _clear_cookie(_result_page(error=error, provider=payload.get("provider")))
    if not code:
        return _clear_cookie(_result_page(error="missing_authorization_code", provider=payload.get("provider")))

    try:
        secret_id, stale_left = await _exchange_and_store(payload, code)
    except (ValueError, KeyError) as exc:
        logger.error("OAuth callback config error: %s", exc)
        return _clear_cookie(_result_page(error="provider_not_configured", provider=payload.get("provider")))
    except RuntimeError as exc:
        logger.error("OAuth token exchange failed: %s", exc)
        return _clear_cookie(_result_page(error="token_exchange_failed", provider=payload.get("provider")))

    return _clear_cookie(
        _result_page(
            secret_id=secret_id,
            provider=payload.get("provider"),
            connector_id=payload.get("connector_id"),
            warning=_STALE_CREDENTIAL_WARNING if stale_left else None,
        )
    )


async def _exchange_and_store(payload: dict, code: str) -> tuple[str, bool]:
    """Exchange the auth code and persist tokens; return ``(secret_id, a_replaced_credential_is_still_active)``."""
    prov = oauth_flow.get_provider(payload["provider"])
    client_id, client_secret = oauth_flow.resolve_client_credentials(prov)
    token_response = await oauth_flow.exchange_code(
        prov, client_id, client_secret, code, payload["redirect_uri"], payload["code_verifier"]
    )
    previous = await find_connector_secret_ids(payload["connector_id"]) if prov.service_owner_id else []
    secret_id = await get_credential_store().store_oauth(
        connector_id=payload["connector_id"],
        owner_id=payload["owner_id"],
        provider=payload["provider"],
        token_response=token_response,
        token_url=prov.token_url,
        scopes=payload.get("scopes") or list(prov.default_scopes),
    )
    stale_left = await _revoke_replaced_credentials([i for i in previous if i != secret_id], prov.service_owner_id)
    return secret_id, stale_left


def _result_page(
    secret_id: str | None = None,
    provider: str | None = None,
    connector_id: str | None = None,
    error: str | None = None,
    warning: str | None = None,
) -> HTMLResponse:
    """Render the popup result page that messages the opener and self-closes."""
    message = {
        "warning": warning,
        "type": "connector-oauth",
        "ok": error is None,
        "secret_id": secret_id,
        "provider": provider,
        "connector_id": connector_id,
        "error": error,
    }
    status = "Connected — you can close this window." if error is None else ("Connection failed: %s" % error)
    if warning:
        status = "%s %s" % (status, warning)
    # Every attacker-influenced value (error is a provider query param) reaches the
    # response only through html.escape, a recognized XSS sanitizer. The visible
    # status is escaped as HTML text; the postMessage payload is serialized to JSON,
    # html-escaped, and stored in a data-* attribute that the inline script reads
    # back via JSON.parse(). No user-influenced value is interpolated into the
    # <script> body itself, so a value cannot break out of the HTML or script context.
    safe_status = html.escape(status)
    safe_payload = html.escape(json.dumps(message))
    body = (
        "<!doctype html><html><head><meta charset='utf-8'><title>Connector OAuth</title></head>"
        "<body style='font-family:sans-serif;padding:2rem'>"
        "<p>%s</p>"
        "<div id='connector-oauth-data' data-message=\"%s\"></div>"
        "<script>(function(){"
        "var el=document.getElementById('connector-oauth-data');"
        "var m=JSON.parse(el.getAttribute('data-message'));"
        "try{if(window.opener){window.opener.postMessage(m,window.location.origin);}}catch(e){}"
        "setTimeout(function(){window.close();},500);"
        "})();</script>"
        "</body></html>"
    ) % (safe_status, safe_payload)
    return HTMLResponse(content=body, status_code=200)


def _clear_cookie(response: HTMLResponse) -> HTMLResponse:
    """Delete the single-use state-binding cookie on the result response."""
    response.delete_cookie(_OAUTH_STATE_COOKIE, path=_OAUTH_CALLBACK_PATH)
    return response


async def attachable_secret_id(secret_id: str, owner_id: str) -> str:
    """*secret_id*, once it is one *owner_id* may attach to a connector; never a service-owned one (#13710)."""
    try:
        await assert_attachable_secret(secret_id, owner_id)
    except (LookupError, PermissionError) as exc:
        logger.warning("Refused to attach a secret to a new connector: %s", type(exc).__name__)
        raise HTTPException(status_code=400, detail="secret cannot be attached to this connector") from exc
    return secret_id


async def _revoke_replaced_credentials(previous_ids: list[str], owner_id: str) -> bool:
    """Revoke every credential a service-owned re-authorization replaced, AFTER the new one is stored (#13710).

    Never the new id, and never before the store: a failed store must leave the old credential intact. Every
    older row is attempted, so an earlier failed revoke is retried here. A failure is logged with the old id (never
    a value) and reported, not raised: the new credential is stored and is the newest, so it is the one used.
    Returns True when any replaced credential is still active.
    """
    stale_left = False
    for previous_id in previous_ids:
        try:
            await get_credential_store().revoke(previous_id, owner_id)
        except Exception as exc:  # noqa: BLE001 - the new credential is already stored
            stale_left = True
            logger.warning("Could not revoke replaced service credential %s: %s", previous_id, type(exc).__name__)
    return stale_left


# Redis single-use-state helpers now live in autobot_shared.redis_client
# (client_setex / client_getdel / client_get) — see Issue #11699.
