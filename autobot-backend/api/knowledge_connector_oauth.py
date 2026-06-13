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

from auth_middleware import get_current_user
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_redis_client
from autobot_shared.ssot_config import config
from knowledge.connectors import oauth_flow
from knowledge.connectors.credential_store import get_credential_store

logger = get_logger(__name__)

router = APIRouter(tags=["knowledge-connectors-oauth"])

# OAuth state is single-use and short-lived; this is a security window, not a cache.
_OAUTH_STATE_TTL_SECONDS = 600
_OAUTH_STATE_PREFIX = "connector:oauth:state:"
# Double-submit cookie binding the completing browser to the initiating one (CSRF).
_OAUTH_STATE_COOKIE = "connector_oauth_state"
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


@router.post("/knowledge_base/connectors/oauth/{provider}/authorize", response_model=AuthorizeResponse)
async def start_oauth(
    provider: str,
    request: AuthorizeRequest,
    response: Response,
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

    state = oauth_flow.generate_state()
    verifier, challenge = oauth_flow.generate_pkce()
    connector_id = str(uuid.uuid4())
    scopes = tuple(request.scopes) if request.scopes else None

    payload = {
        "provider": provider,
        "owner_id": str(user.get("user_id") or "system"),
        "connector_id": connector_id,
        "code_verifier": verifier,
        "redirect_uri": request.redirect_uri,
        "scopes": list(scopes) if scopes else [],
    }
    redis = get_redis_client(database="knowledge")
    await _redis_setex(redis, _state_key(state), _OAUTH_STATE_TTL_SECONDS, json.dumps(payload, ensure_ascii=False))

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
    if not cookie_state or cookie_state != state:
        return _clear_cookie(_result_page(error="state_binding_mismatch"))

    redis = get_redis_client(database="knowledge")
    raw = await _redis_getdel(redis, _state_key(state))
    if raw is None:
        return _clear_cookie(_result_page(error="invalid_or_expired_state"))
    payload = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)

    if error:
        return _clear_cookie(_result_page(error=error, provider=payload.get("provider")))
    if not code:
        return _clear_cookie(_result_page(error="missing_authorization_code", provider=payload.get("provider")))

    try:
        secret_id = await _exchange_and_store(payload, code)
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
        )
    )


async def _exchange_and_store(payload: dict, code: str) -> str:
    """Exchange the auth code and persist tokens; return the secret id."""
    prov = oauth_flow.get_provider(payload["provider"])
    client_id, client_secret = oauth_flow.resolve_client_credentials(prov)
    token_response = await oauth_flow.exchange_code(
        prov, client_id, client_secret, code, payload["redirect_uri"], payload["code_verifier"]
    )
    return await get_credential_store().store_oauth(
        connector_id=payload["connector_id"],
        owner_id=payload["owner_id"],
        provider=payload["provider"],
        token_response=token_response,
        client_id=client_id,
        client_secret=client_secret,
        token_url=prov.token_url,
        scopes=payload.get("scopes") or list(prov.default_scopes),
    )


def _result_page(
    secret_id: str | None = None,
    provider: str | None = None,
    connector_id: str | None = None,
    error: str | None = None,
) -> HTMLResponse:
    """Render the popup result page that messages the opener and self-closes."""
    message = {
        "type": "connector-oauth",
        "ok": error is None,
        "secret_id": secret_id,
        "provider": provider,
        "connector_id": connector_id,
        "error": error,
    }
    status = "Connected — you can close this window." if error is None else ("Connection failed: %s" % error)
    # Both reflected values are attacker-influenced (error is a provider query
    # param): HTML-escape the visible text, and JS-escape the embedded JSON so a
    # value can never break out of the <script> or the string context.
    safe_status = html.escape(status)
    safe_json = _js_safe_json(message)
    body = (
        "<!doctype html><html><head><meta charset='utf-8'><title>Connector OAuth</title></head>"
        "<body style='font-family:sans-serif;padding:2rem'>"
        "<p>%s</p>"
        "<script>(function(){var m=%s;try{if(window.opener){window.opener.postMessage(m,window.location.origin);}}"
        "catch(e){}setTimeout(function(){window.close();},500);})();</script>"
        "</body></html>"
    ) % (safe_status, safe_json)
    return HTMLResponse(content=body, status_code=200)


def _js_safe_json(obj: dict) -> str:
    """json.dumps with HTML/JS-sensitive chars escaped so it is safe inside <script>."""
    out = json.dumps(obj)
    for ch, esc in (
        ("<", "\\u003c"),
        (">", "\\u003e"),
        ("&", "\\u0026"),
        (chr(0x2028), "\\u2028"),  # JS line separator — breaks string literals
        (chr(0x2029), "\\u2029"),  # JS paragraph separator
    ):
        out = out.replace(ch, esc)
    return out


def _clear_cookie(response: HTMLResponse) -> HTMLResponse:
    """Delete the single-use state-binding cookie on the result response."""
    response.delete_cookie(_OAUTH_STATE_COOKIE, path=_OAUTH_CALLBACK_PATH)
    return response


# ---------------------------------------------------------------------------
# Redis helpers (sync client → thread; tolerate async client too)
# ---------------------------------------------------------------------------


async def _redis_setex(redis, key: str, ttl: int, value: str) -> None:
    result = redis.set(key, value, ex=ttl)
    if hasattr(result, "__await__"):
        await result


async def _redis_getdel(redis, key: str):
    """Atomically fetch and delete a key (single-use state)."""
    getdel = getattr(redis, "getdel", None)
    if getdel is not None:
        result = getdel(key)
        if hasattr(result, "__await__"):
            result = await result
        return result
    # Fallback for clients without GETDEL.
    value = redis.get(key)
    if hasattr(value, "__await__"):
        value = await value
    deleted = redis.delete(key)
    if hasattr(deleted, "__await__"):
        await deleted
    return value
