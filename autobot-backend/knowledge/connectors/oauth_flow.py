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


# ---------------------------------------------------------------------------
# Provider registry
# ---------------------------------------------------------------------------

OAUTH_PROVIDERS: dict = {
    "google": OAuthProvider(
        name="google",
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",  # nosec B106 - OAuth token endpoint URL, not a credential
        client_id_setting="google_oauth_client_id",
        client_secret_setting="google_oauth_client_secret",
        default_scopes=("https://www.googleapis.com/auth/drive.readonly",),
        # access_type=offline + prompt=consent → Google always returns a refresh_token.
        extra_authorize_params={"access_type": "offline", "prompt": "consent"},
    ),
    "microsoft": OAuthProvider(
        name="microsoft",
        authorize_url="https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        token_url="https://login.microsoftonline.com/common/oauth2/v2.0/token",  # nosec B106 - token endpoint URL
        client_id_setting="microsoft_oauth_client_id",
        client_secret_setting="microsoft_oauth_client_secret",
        # offline_access is required for Microsoft to issue a refresh token.
        default_scopes=("offline_access", "Files.Read.All", "Sites.Read.All"),
    ),
    "gitlab": OAuthProvider(
        name="gitlab",
        authorize_url="https://gitlab.com/oauth/authorize",
        token_url="https://gitlab.com/oauth/token",  # nosec B106 - OAuth token endpoint URL, not a credential
        client_id_setting="gitlab_oauth_client_id",
        client_secret_setting="gitlab_oauth_client_secret",
        default_scopes=("read_api", "read_repository"),
    ),
}


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
    return client_id, client_secret


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
        "scope": " ".join(chosen_scopes),
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    params.update(provider.extra_authorize_params)
    return "%s?%s" % (provider.authorize_url, urlencode(params))


# ---------------------------------------------------------------------------
# Token exchange + refresh
# ---------------------------------------------------------------------------


async def _post_token(token_url: str, payload: dict) -> dict:
    """POST form-encoded *payload* to *token_url*; return the parsed token dict.

    Raises RuntimeError on a non-2xx response or transport error.
    """
    timeout = aiohttp.ClientTimeout(total=_TOKEN_REQUEST_TIMEOUT)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                token_url,
                data=payload,
                headers={"Accept": "application/json"},
                allow_redirects=False,
            ) as resp:
                body = await resp.json(content_type=None)
                if resp.status >= 400:
                    # Token endpoints return {"error": "...", "error_description": "..."}.
                    detail = body.get("error_description") or body.get("error") or "unknown error"
                    raise RuntimeError("token endpoint returned HTTP %d: %s" % (resp.status, detail))
                return body
    except aiohttp.ClientError as exc:
        raise RuntimeError("token endpoint request failed: %s" % exc) from exc


async def exchange_code(
    provider: OAuthProvider,
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
    code_verifier: str,
) -> dict:
    """Exchange an authorization *code* for tokens.

    Returns the raw token response (access_token, refresh_token, expires_in, ...).
    """
    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "client_secret": client_secret,
        "code_verifier": code_verifier,
    }
    return await _post_token(provider.token_url, payload)


async def refresh_access_token(
    token_url: str,
    client_id: str,
    client_secret: str,
    refresh_token: str,
) -> dict:
    """Exchange a *refresh_token* for a fresh access token.

    Returns the raw token response. Some providers (e.g. GitLab) rotate the
    refresh token and return a new one; callers must persist it when present.
    """
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
    }
    return await _post_token(token_url, payload)
