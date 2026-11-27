# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Pure OAuth credential-bundle construction for ConnectorCredentialStore (ADR-007).

Split out of ``credential_store.py`` so the one stored OAuth bundle shape is built
in one place for every write route: the auth-code flow (``store_oauth``) and the
Secrets-page bridge (``store_refreshable_oauth``, #22234). No I/O happens here.
"""

from datetime import timedelta
from urllib.parse import urlparse

from autobot_shared.security.ssrf_guard import SSRFError, pinned_connector, resolve_safe_ip
from autobot_shared.time_utils import now_utc

# Fields an OAuthRefreshAuth bundle must carry to be refreshable (#22234).
REFRESHABLE_REQUIRED_FIELDS = ("client_id", "client_secret", "refresh_token", "token_url")


async def require_public_https_url(url: str) -> None:
    """Refuse a token URL that is not HTTPS to a public host (#22234, THREAT_MODEL).

    Uses the guarded-fetch primitives (``ssrf_guard.resolve_safe_ip``) so the
    create-time check and the refresh-time pin agree. Raises ValueError
    (``SSRFError`` is one), which the Secrets route maps to 400.
    """
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise SSRFError("token_url must be an https URL")
    await resolve_safe_ip(parsed.hostname)


async def pinned_token_connector(token_url: str, provider):
    """SSRF-pinned connector for the URL a refresh will really POST to (#22234)."""
    return await pinned_connector((provider.refresh_url if provider else "") or token_url)


class OAuthBundleMixin:
    """Builds the stored OAuth bundle and its expiry fields."""

    @classmethod
    def _oauth_bundle(
        cls,
        token_response: dict,
        token_url: str,
        scopes: list,
        provider: str,
    ) -> dict:
        """Build the stored OAuth credential bundle from a token response."""
        return {
            "provider": provider,
            "access_token": token_response.get("access_token", ""),
            "refresh_token": token_response.get("refresh_token", ""),
            "access_token_expires_at": cls._expiry_iso(token_response.get("expires_in")),
            # The lifetime, kept alongside the derived timestamp so a refresh
            # response that omits ``expires_in`` can recompute one (#13626).
            "access_token_lifetime_seconds": cls._lifetime_seconds(token_response.get("expires_in")),
            "token_type": token_response.get("token_type", "Bearer"),
            "scope": token_response.get("scope", " ".join(scopes)),
            "token_url": token_url,
        }

    @staticmethod
    def _lifetime_seconds(expires_in) -> int | None:
        """Return *expires_in* as whole seconds, or None when not reported (#13626).

        Kept separate from :meth:`_expiry_iso` so the stored lifetime survives a
        refresh response that omits ``expires_in``. Parsing failures return None
        for the same reason ``_expiry_iso`` does — an unusable value is treated
        as "not reported" rather than guessed at.
        """
        if expires_in is None:
            return None
        try:
            return int(expires_in)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _expiry_iso(expires_in) -> str | None:
        """Return ISO expiry timestamp for *expires_in* seconds, or None.

        Only a missing value (None) means non-expiring; ``expires_in == 0`` is a
        real, immediate expiry.
        """
        if expires_in is None:
            return None
        try:
            seconds = int(expires_in)
        except (TypeError, ValueError):
            return None
        return (now_utc() + timedelta(seconds=seconds)).isoformat()

    @classmethod
    def _refreshable_bundle(cls, config: dict) -> dict:
        """Bundle for an OAuthRefreshAuth credential with no operator provider config (#22234).

        Carries ``client_id``/``client_secret``/``token_url`` itself -- the shape
        ``_resolve_app_credentials`` reads as its stored copy -- and no access
        token, so the first ``get_access_token`` refreshes. Raises ValueError for
        a missing, empty or mistyped field: refused at create, not at refresh.
        """
        missing = [f for f in REFRESHABLE_REQUIRED_FIELDS if not config.get(f)]
        if missing:
            raise ValueError("missing required auth field: %s" % ", ".join(missing))
        scopes = config.get("scopes") or []
        if not all(isinstance(config[f], str) for f in REFRESHABLE_REQUIRED_FIELDS):
            raise ValueError("auth fields must be strings")
        if not isinstance(scopes, list) or not all(isinstance(x, str) for x in scopes):
            raise ValueError("scopes must be a list of strings")
        bundle = cls._oauth_bundle({"refresh_token": config["refresh_token"]}, config["token_url"], scopes, "")
        bundle["client_id"] = config["client_id"]
        bundle["client_secret"] = config["client_secret"]
        return bundle
