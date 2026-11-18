# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Generic OAuth 2.0 authorization-code flow for connectors (ADR-007 / GH#9019).

Provider-agnostic helpers used by the connector OAuth endpoints and the
credential resolver:

- A small registry of supported providers (Google, Microsoft, GitLab).
- PKCE (S256) generation.
- Authorization-URL construction.
- Authorization-code → token exchange.
- Refresh-token → access-token refresh (used by the auto-refresh resolver).

Operator-registered OAuth *application* credentials (client_id/client_secret)
come from ``config.auth.*`` — see ssot_config AuthConfig. The per-user tokens
this module obtains are persisted via SecretsService by the caller, never here.
"""

import base64
import hashlib
import secrets
from dataclasses import dataclass, field
from typing import Tuple

import aiohttp

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config

logger = get_logger(__name__)

_TOKEN_REQUEST_TIMEOUT = 30.0


@dataclass(frozen=True)
class OAuthProvider:
    """Static OAuth endpoint + scope configuration for one provider."""

    name: str
    authorize_url: str
    token_url: str
    client_id_setting: str
    client_secret_setting: str
    default_scopes: Tuple[str, ...] = ()
    # Extra query params required on the authorize request (provider-specific,
    # e.g. Google's offline access + consent prompt to guarantee a refresh token).
    extra_authorize_params: dict = field(default_factory=dict)
    # --- Deviation fields (#13630). All optional; the defaults reproduce the
    # behaviour every registered provider had before they existed. ---
    # Separate refresh endpoint; empty means "refresh at token_url".
    refresh_url: str = ""
    # "client_secret_post" (credentials in the body), "client_secret_basic"
    # (HTTP Basic header) or "none" (public client: client_id only, no secret).
    token_endpoint_auth_method: str = "client_secret_post"
    # "form" (application/x-www-form-urlencoded) or "json".
    token_request_encoding: str = "form"
    # Per-grant renames of the standard parameter names, e.g. {"code": "auth_code"}.
    exchange_param_names: dict = field(default_factory=dict)
    refresh_param_names: dict = field(default_factory=dict)
    # Key under which a non-standard response envelope ({code, data: {...}}) holds
    # the token object; empty means the response body IS the token object.
    token_response_envelope_key: str = ""
    scope_separator: str = " "
    # ssot_config.auth setting names of extra operator-supplied client config
    # (e.g. a tenant or region) that must be set before authorization can start.
    extra_client_config_settings: Tuple[str, ...] = ()
    # RFC 8628 device-authorization endpoint; empty means no device-code flow (#19241).
    device_authorization_url: str = ""
    # RFC 7009 revocation endpoint; empty means revoke is local-only (#19241).
    revocation_url: str = ""


# ---------------------------------------------------------------------------
# Provider registry
# ---------------------------------------------------------------------------

OAUTH_PROVIDERS: dict = {
    "google": OAuthProvider(
        name="google",
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",  # nosec B106  # OAuth token endpoint URL, not a credential
        client_id_setting="google_oauth_client_id",
        client_secret_setting="google_oauth_client_secret",
        default_scopes=("https://www.googleapis.com/auth/drive.readonly",),
        # access_type=offline + prompt=consent → Google always returns a refresh_token.
        extra_authorize_params={"access_type": "offline", "prompt": "consent"},
    ),
    "microsoft": OAuthProvider(
        name="microsoft",
        authorize_url="https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        token_url="https://login.microsoftonline.com/common/oauth2/v2.0/token",  # nosec B106  # token endpoint URL
        client_id_setting="microsoft_oauth_client_id",
        client_secret_setting="microsoft_oauth_client_secret",
        # offline_access is required for Microsoft to issue a refresh token.
        default_scopes=("offline_access", "Files.Read.All", "Sites.Read.All"),
    ),
    "gitlab": OAuthProvider(
        name="gitlab",
        authorize_url="https://gitlab.com/oauth/authorize",
        token_url="https://gitlab.com/oauth/token",  # nosec B106  # OAuth token endpoint URL, not a credential
        client_id_setting="gitlab_oauth_client_id",
        client_secret_setting="gitlab_oauth_client_secret",
        default_scopes=("read_api", "read_repository"),
    ),
}


def find_provider(name: str | None) -> OAuthProvider | None:
    """Return the registered OAuthProvider for *name*, or None when unknown."""
    return OAUTH_PROVIDERS.get(name or "")


def get_provider(name: str) -> OAuthProvider:
    """Return the OAuthProvider for *name*. Raises KeyError when unknown."""
    try:
        return OAUTH_PROVIDERS[name]
    except KeyError as exc:
        raise KeyError("unknown OAuth provider: %s" % name) from exc


def resolve_client_credentials(provider: OAuthProvider) -> Tuple[str, str]:
    """Return (client_id, client_secret) for *provider* from operator config.

    Raises ValueError when either is unset — the provider's Connect flow is
    disabled until the operator registers an OAuth application.
    """
    client_id = getattr(config.auth, provider.client_id_setting, "") or ""
    client_secret = getattr(config.auth, provider.client_secret_setting, "") or ""
    if not client_id or not client_secret:
        raise ValueError(
            "OAuth provider %r is not configured — set %s / %s"
            % (provider.name, provider.client_id_setting, provider.client_secret_setting)
        )
    resolve_extra_client_config(provider)
    return client_id, client_secret


def resolve_extra_client_config(provider: OAuthProvider) -> dict:
    """Return {setting: value} for the provider's extra client-config fields (#13630).

    Raises ValueError when any is unset; providers declaring none get ``{}``.
    """
    values = {name: getattr(config.auth, name, "") or "" for name in provider.extra_client_config_settings}
    missing = sorted(name for name, value in values.items() if not value)
    if missing:
        raise ValueError("OAuth provider %r is not configured — set %s" % (provider.name, ", ".join(missing)))
    return values


# ---------------------------------------------------------------------------
# PKCE
# ---------------------------------------------------------------------------


def generate_pkce() -> Tuple[str, str]:
    """Return (code_verifier, code_challenge) for a PKCE S256 exchange."""
    verifier = secrets.token_urlsafe(64)[:128]
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


def generate_state() -> str:
    """Return an unguessable CSRF state token for the authorize request."""
    return secrets.token_urlsafe(32)


# ---------------------------------------------------------------------------
# Authorization URL
# ---------------------------------------------------------------------------


def build_authorize_url(
    provider: OAuthProvider,
    client_id: str,
    redirect_uri: str,
    state: str,
    code_challenge: str,
    scopes: Tuple[str, ...] | None = None,
) -> str:
    """Construct the provider authorization URL for an auth-code + PKCE flow."""
    from urllib.parse import urlencode

    chosen_scopes = scopes if scopes else provider.default_scopes
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": provider.scope_separator.join(chosen_scopes),
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    params.update(provider.extra_authorize_params)
    return "%s?%s" % (provider.authorize_url, urlencode(params))


# ---------------------------------------------------------------------------
# Token exchange + refresh
# ---------------------------------------------------------------------------


class TokenEndpointError(RuntimeError):
    """A token endpoint answered with an error (RFC 6749 §5.2); ``error`` keeps its code (#19241).

    A RuntimeError subclass, so every existing ``except RuntimeError`` still applies.
    The description is redacted before it enters the message: these messages are logged.
    """

    def __init__(self, status: int, body: dict) -> None:
        from autobot_shared.secret_redaction import redact_text  # noqa: PLC0415

        self.status = status
        self.error = str(body.get("error") or "")
        detail = redact_text(str(body.get("error_description") or self.error or "unknown error"))
        super().__init__("token endpoint returned HTTP %d: %s" % (status, detail))


def _apply_client_auth(
    provider: OAuthProvider | None, payload: dict, client_id: str, client_secret: str
) -> Tuple[dict, dict]:
    """Return (payload, extra headers) for the provider's token_endpoint_auth_method (#13630)."""
    method = provider.token_endpoint_auth_method if provider else "client_secret_post"
    if method == "client_secret_post":
        return payload, {}
    payload = {k: v for k, v in payload.items() if k not in ("client_id", "client_secret")}
    if method == "client_secret_basic":
        raw = ("%s:%s" % (client_id, client_secret)).encode("utf-8")
        return payload, {"Authorization": "Basic " + base64.b64encode(raw).decode("ascii")}
    if method == "none":
        return {**payload, "client_id": client_id}, {}
    raise ValueError("unsupported token_endpoint_auth_method: %r" % method)


def _rename_params(payload: dict, names: dict | None) -> dict:
    return {(names or {}).get(key, key): value for key, value in payload.items()}


def _unwrap_envelope(body: dict, provider: OAuthProvider | None) -> dict:
    key = provider.token_response_envelope_key if provider else ""
    if not key:
        return body
    inner = body.get(key) if isinstance(body, dict) else None
    if not isinstance(inner, dict):
        raise RuntimeError("token endpoint response has no %r object" % key)
    return inner


def _request_body(provider: OAuthProvider | None, payload: dict) -> dict:
    """aiohttp body kwarg for the provider's token_request_encoding (default: form)."""
    is_json = bool(provider) and provider.token_request_encoding == "json"  # nosec B105  # encoding name
    return {"json": payload} if is_json else {"data": payload}


async def _post_token(
    token_url: str,
    payload: dict,
    *,
    connector: aiohttp.BaseConnector | None = None,
    provider: OAuthProvider | None = None,
    headers: dict | None = None,
) -> dict:
    """POST form-encoded *payload* to *token_url*; return the parsed token dict.

    Raises RuntimeError on a non-2xx response or transport error.

    When *connector* is provided (an SSRF-pinned :class:`aiohttp.TCPConnector`
    from ``ssrf_guard.pinned_connector``), the session connects to the
    pre-resolved public IP so the token POST cannot be DNS-rebound to a private
    address between validation and connect. The session owns and closes it.

    Issue #12979 — deliberately NOT the shared pooled client: a connector is
    session-level and the pool accepts no per-request override, so pooling would
    drop the pinned connector and reopen the DNS-rebinding hole closed in #12278.
    """
    timeout = aiohttp.ClientTimeout(total=_TOKEN_REQUEST_TIMEOUT)
    session_kwargs: dict = {"timeout": timeout, **({"connector": connector} if connector is not None else {})}
    try:
        async with aiohttp.ClientSession(**session_kwargs) as session:
            return await _send_token_request(session, token_url, payload, provider, headers)
    except aiohttp.ClientError as exc:
        raise RuntimeError("token endpoint request failed: %s" % exc) from exc


async def _send_token_request(session, token_url: str, payload: dict, provider, headers: dict | None) -> dict:
    """POST one token request on *session*; return the unwrapped token object."""
    async with session.post(
        token_url,
        **_request_body(provider, payload),
        headers={"Accept": "application/json", **(headers or {})},
        allow_redirects=False,
    ) as resp:
        body = await resp.json(content_type=None)
        if resp.status >= 400:
            raise TokenEndpointError(resp.status, body if isinstance(body, dict) else {})
        return _unwrap_envelope(body, provider)


async def exchange_code(
    provider: OAuthProvider,
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
    code_verifier: str,
    *,
    connector: aiohttp.BaseConnector | None = None,
) -> dict:
    """Exchange an authorization *code* for tokens.

    Returns the raw token response (access_token, refresh_token, expires_in, ...).
    Pass *connector* (an SSRF-pinned connector) to defeat DNS-rebinding on the
    outbound token POST.
    """
    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "client_secret": client_secret,
        "code_verifier": code_verifier,
    }
    payload, headers = _apply_client_auth(provider, payload, client_id, client_secret)
    payload = _rename_params(payload, provider.exchange_param_names)
    return await _post_token(provider.token_url, payload, connector=connector, provider=provider, headers=headers)


async def refresh_access_token(
    token_url: str,
    client_id: str,
    client_secret: str,
    refresh_token: str,
    *,
    connector: aiohttp.BaseConnector | None = None,
    provider: OAuthProvider | None = None,
) -> dict:
    """Exchange a *refresh_token* for a fresh access token.

    *provider*, when given, applies its deviation fields (#13630): refresh URL,
    client-auth method, request encoding, parameter renames and response
    envelope. Omitted, behaviour is the standard form POST to *token_url*.

    Returns the raw token response. Some providers (e.g. GitLab) rotate the
    refresh token and return a new one; callers must persist it when present.
    Pass *connector* (an SSRF-pinned connector) to defeat DNS-rebinding on the
    outbound token POST.
    """
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
    }
    payload, headers = _apply_client_auth(provider, payload, client_id, client_secret)
    payload = _rename_params(payload, provider.refresh_param_names if provider else None)
    url = (provider.refresh_url if provider else "") or token_url
    return await _post_token(url, payload, connector=connector, provider=provider, headers=headers)
