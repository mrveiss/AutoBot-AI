# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Provider-auth errors and token-response helpers (#10551, #11497).

Split out of ``llm_shared.provider_auth`` so that module stays under its size
ceiling (#19241). ``llm_shared.provider_auth`` re-exports every public name
here, so existing imports keep working.
"""

from __future__ import annotations

import time
from typing import Any

from autobot_shared.auth.jwt_core import decode_jwt_claims_unverified


class ProviderAuthError(Exception):
    """Unrecoverable auth failure — the provider cannot be used."""


class TokenExpiredError(ProviderAuthError):
    """Access token expired and no refresh token is available."""


class TokenRevokedError(TokenExpiredError):
    """The provider rejected the refresh token (``invalid_grant``): only a new sign-in helps (#19241)."""


#: Stored-token flag set when the provider answered ``invalid_grant`` (#19241). The
#: token is skipped until a new sign-in overwrites it, and /status reports it.
NEEDS_REAUTH_KEY = "needs_reauth"  # pragma: allowlist secret  # a dict key name, not a credential

#: Record stored at an ORG subject by that org's system disconnect (#19241, owner
#: decision): the org stops falling back to the legacy shared ``"global"`` token,
#: which other orgs may still use. It lives in the vault beside the tokens, so
#: every worker sees it, and a new system sign-in for the org overwrites it.
LEGACY_FALLBACK_STOP_KEY = "legacy_fallback_stopped"


# ---------------------------------------------------------------------------
# Token dict helpers
# ---------------------------------------------------------------------------


def _merge_token_response(old: dict, resp: dict) -> dict:
    """Merge a token response into an existing token dict.

    Preserves ``created_by`` and falls back to the old refresh_token when the
    provider does not rotate it (some providers omit ``refresh_token`` on
    refresh — RFC 6749 §6 allows this).
    """
    new: dict = dict(old)
    new["access_token"] = resp["access_token"]
    if "refresh_token" in resp:
        new["refresh_token"] = resp["refresh_token"]
    expires_in = resp.get("expires_in")
    if expires_in:
        new["expires_at"] = time.time() + int(expires_in)
    return new


# ---------------------------------------------------------------------------
# Token audience / issuer / type validation (finding #3, #11497)
# ---------------------------------------------------------------------------


def _decode_jwt_claims(id_token: str) -> dict[str, Any]:
    """Decode (WITHOUT signature verification) the payload of a compact JWS.

    Used only to cross-check the ``iss`` / ``aud`` claims of an OIDC id_token
    against the expected provider + client_id. The access token's authenticity
    still rests on the TLS-authenticated token endpoint; this is defence-in-depth
    against a swapped-audience / wrong-issuer token, not a trust anchor.
    """
    try:
        return decode_jwt_claims_unverified(id_token)
    except ValueError as exc:
        raise ProviderAuthError(f"id_token {exc}") from exc


def validate_token_response(resp: dict, *, provider_name: str, client_id: str) -> None:
    """Validate ``token_type`` / ``iss`` / ``aud`` before a token is persisted.

    Finding #3 (#11497). Lenient-but-strict: a field is only rejected when it is
    PRESENT and wrong, so providers that legitimately omit ``token_type`` or an
    ``id_token`` (RFC 6749 token responses) keep working with zero regression.

    - ``token_type``: must be ``bearer`` (case-insensitive) when present.
    - ``id_token`` (OIDC): when present, its ``aud`` must contain *client_id*
      and its ``iss`` must be an https URL on an allowlisted OAuth host — and,
      for a known OIDC provider, match that provider's issuer prefix.

    Raises ``ProviderAuthError`` on any mismatch.
    """
    token_type = resp.get("token_type")
    if token_type is not None and str(token_type).lower() != "bearer":
        raise ProviderAuthError(f"unexpected token_type {token_type!r} for provider {provider_name!r}")

    id_token = resp.get("id_token")
    if not id_token:
        return

    claims = _decode_jwt_claims(id_token)

    aud = claims.get("aud")
    if aud is not None:
        audiences = {aud} if isinstance(aud, str) else set(aud or [])
        azp = claims.get("azp")
        if client_id and client_id not in audiences and client_id != azp:
            raise ProviderAuthError(f"id_token audience does not include client_id for provider {provider_name!r}")

    iss = claims.get("iss")
    if iss is not None:
        _validate_issuer(str(iss), provider_name)


def _validate_issuer(iss: str, provider_name: str) -> None:
    """Reject an id_token issuer that is not an allowlisted / expected host."""
    from urllib.parse import urlparse  # noqa: PLC0415

    from autobot_shared.url_safety import get_oauth_allowed_hosts  # noqa: PLC0415

    from .provider_auth import _EXPECTED_ISSUER_PREFIXES  # noqa: PLC0415  # provider data stays there

    parsed = urlparse(iss)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ProviderAuthError(f"id_token issuer {iss!r} is not an https URL for provider {provider_name!r}")
    if parsed.hostname.lower() not in get_oauth_allowed_hosts():
        raise ProviderAuthError(f"id_token issuer host {parsed.hostname!r} is not allowlisted")

    expected = _EXPECTED_ISSUER_PREFIXES.get(provider_name.lower())
    if expected and not any(iss.startswith(prefix) for prefix in expected):
        raise ProviderAuthError(f"id_token issuer {iss!r} is not valid for provider {provider_name!r}")


def build_token_data(
    resp: dict,
    *,
    created_by: str,
) -> dict[str, Any]:
    """Build the canonical token dict from a raw token endpoint response."""
    data: dict[str, Any] = {
        "access_token": resp["access_token"],
        "created_by": created_by,
    }
    if "refresh_token" in resp:
        data["refresh_token"] = resp["refresh_token"]
    expires_in = resp.get("expires_in")
    if expires_in:
        data["expires_at"] = time.time() + int(expires_in)
    return data
