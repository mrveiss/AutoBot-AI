# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Provider auth abstraction for the multi-provider LLM layer (#10551).

Defines auth strategies that decouple credential acquisition from provider
usage.  ``BaseProvider`` resolves credentials THROUGH the active strategy
instead of assuming a bare ``api_key`` in settings.

Strategies
----------
- ``StaticApiKeyAuth``      — wraps today's api_key behaviour (backward-compatible).
- ``OAuthAuth``       — authorization-code + PKCE; tokens kept in the vault.
- ``DeviceCodeAuth``  — RFC 8628 device-authorization grant (CLI/headless).
- ``SessionAuth``     — bearer token from an existing session/subscription.

Token storage
-------------
All OAuth / device / session tokens (access + refresh) are stored in the
unified secrets vault (``EnvelopeSecretsService``).  The vault key for a
provider auth token uses the canonical form:

    system:provider_auth:<provider_name>:<user_id_or_global>

Resolution path
---------------
``resolve_token(session)`` is the single entry-point called by
``BaseProvider._get_auth_token()``.  It returns a bearer token string (or
raises ``ProviderAuthError`` on unrecoverable failure so callers can fallback).
Automatic token refresh happens transparently here — the vault is updated with
the new token pair before the access token is returned to the caller.

OAuth machinery
---------------
OAuth token exchange / refresh is reused from
``knowledge.connectors.oauth_flow`` (``_post_token``, ``refresh_access_token``)
rather than duplicating the HTTP machinery.  The SSO PKCE helper
``knowledge.connectors.oauth_flow.generate_pkce`` is reused for the device-code
path as well (same S256 derivation).
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any

from autobot_shared.logging_manager import get_logger

from .provider_token_response import (  # noqa: F401  # re-exported (#19241 split)
    LEGACY_FALLBACK_STOP_KEY,
    NEEDS_REAUTH_KEY,
    ProviderAuthError,
    TokenExpiredError,
    TokenRevokedError,
    _decode_jwt_claims,
    _merge_token_response,
    build_token_data,
    validate_token_response,
)

logger = get_logger(__name__)

# Vault secret type tag for all provider-auth tokens stored via EnvelopeSecretsService.
PROVIDER_AUTH_SECRET_TYPE = "provider_auth_token"  # nosec B105  # vault type tag, not a credential

# Grace window before expiry at which a refresh is proactively triggered (seconds).
_REFRESH_GRACE_SECONDS = 300

# Legacy pre-#11497 vault subject: a single system-wide token shared by every
# authenticated user. Retained as the dual-read fallback so existing connections
# keep working with zero reconnect while new persists move to a per-org subject.
LEGACY_SUBJECT = "global"


def org_vault_subject(org_id: Any | None) -> str:
    """Return the per-org vault subject for a token, or the legacy shared subject.

    Finding #1 (#11497): provider tokens are keyed to the caller's org/tenant so
    an admin connects once and only that org shares the connection — isolated
    between orgs. When no org is available (single-tenant deployment, or a code
    path without an org principal) we keep the legacy ``"global"`` subject so
    behaviour is byte-identical to the pre-#11497 shared model.
    """
    if org_id is None:
        return LEGACY_SUBJECT
    org_id = str(org_id).strip()
    return f"org:{org_id}" if org_id else LEGACY_SUBJECT


#: Prefix of a per-user subject (#19241): a user's own provider account.
USER_SUBJECT_PREFIX = "user:"


def user_vault_subject(user_id: Any) -> str:
    """Return the per-user vault subject for *user_id* (#19241). Raises ValueError when empty.

    A user subject never falls back to the org or legacy subject on read, so one
    user's lookup can never return another principal's token.
    """
    uid = str(user_id or "").strip()
    if not uid:
        raise ValueError("a per-user provider token needs a user id")
    return f"{USER_SUBJECT_PREFIX}{uid}"


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class ProviderAuthStrategy(ABC):
    """Abstract auth strategy.  Subclasses implement ``resolve_token``."""

    @abstractmethod
    async def resolve_token(self, session: Any | None = None) -> str:
        """Return a valid bearer / API token for the provider.

        Args:
            session: Optional SQLAlchemy ``AsyncSession`` required by vault-backed
                     strategies.  ``StaticApiKeyAuth`` ignores it.

        Returns:
            Token string (never empty).

        Raises:
            ProviderAuthError: When no valid token can be obtained.
        """

    def is_vault_backed(self) -> bool:
        """Return True when this strategy stores tokens in the secrets vault."""
        return False


# ---------------------------------------------------------------------------
# StaticApiKeyAuth — backward-compatible default
# ---------------------------------------------------------------------------


class StaticApiKeyAuth(ProviderAuthStrategy):
    """Wraps a static API key from provider settings.

    This is the default strategy for all existing providers — no behaviour
    change, fully backward-compatible.
    """

    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise ProviderAuthError("StaticApiKeyAuth requires a non-empty api_key")
        self._key = api_key

    async def resolve_token(self, session: Any | None = None) -> str:
        return self._key

    def __repr__(self) -> str:
        return "<StaticApiKeyAuth key=***>"


# ---------------------------------------------------------------------------
# Vault helpers (shared by OAuthAuth / DeviceCodeAuth / SessionAuth)
# ---------------------------------------------------------------------------


def _vault_secret_name(provider_name: str, subject: str = "global") -> str:
    """Canonical secret name for a provider auth token in the vault."""
    return f"provider_auth:{provider_name}:{subject}"


async def _vault_read(
    session: Any,
    *,
    provider_name: str,
    subject: str,
    owner_vault_str: str,
) -> dict[str, Any] | None:
    """Read a stored token dict from the vault.  Returns None on miss."""
    import json

    from sqlalchemy import select  # noqa: PLC0415 — conditional import inside helper

    from autobot_shared.secrets_vault import VaultRef
    from models.secret import Secret  # noqa: PLC0415
    from services.envelope_secrets_service import EnvelopeSecretsService, SecretAccessError, SecretNotFoundError

    name = _vault_secret_name(provider_name, subject)
    # Look up the secret row by name + owner_vault to find the secret_id.
    result = await session.execute(select(Secret).where(Secret.name == name, Secret.owner_vault == owner_vault_str))
    secret_row = result.scalar_one_or_none()
    if secret_row is None:
        return None

    svc = EnvelopeSecretsService()
    owner_ref = VaultRef.parse(owner_vault_str)
    try:
        raw = await svc.read(session, secret_id=secret_row.id, accessible_vaults=[owner_ref])
    except (SecretNotFoundError, SecretAccessError):
        return None

    try:
        return json.loads(raw.decode("utf-8"))
    except Exception as exc:
        logger.warning("provider_auth vault decode failed for %s: %s", name, exc)
        return None


async def _vault_read_dual(
    session: Any,
    *,
    provider_name: str,
    subject: str,
    owner_vault_str: str,
) -> dict[str, Any] | None:
    """Read a token, trying the org-scoped *subject* then the legacy subject.

    Backward-compatible dual-read for finding #1 (#11497): tokens written under
    the pre-#11497 ``"global"`` subject stay readable after callers move to a
    per-org subject. The org-scoped entry wins when present; the legacy
    ``"global"`` entry is the fallback so existing connections keep working with
    zero reconnect. When *subject* already IS the legacy subject this is a single
    read (no redundant lookup).
    """
    token_data = await _vault_read(
        session,
        provider_name=provider_name,
        subject=subject,
        owner_vault_str=owner_vault_str,
    )
    # An org that disconnected its system sign-in no longer falls back to "global" (#19241).
    if token_data is not None and token_data.get(LEGACY_FALLBACK_STOP_KEY):
        return None
    # A user subject (#19241) is single-read: falling back to "global" would hand
    # a user the shared credential under their own name.
    if token_data is not None or subject == LEGACY_SUBJECT or subject.startswith(USER_SUBJECT_PREFIX):
        return token_data
    return await _vault_read(
        session,
        provider_name=provider_name,
        subject=LEGACY_SUBJECT,
        owner_vault_str=owner_vault_str,
    )


async def _vault_write(
    session: Any,
    *,
    provider_name: str,
    subject: str,
    owner_vault_str: str,
    token_data: dict[str, Any],
    created_by_id: Any,
) -> None:
    """Upsert a token dict into the vault (delete-then-create for simplicity)."""
    import json
    import uuid

    from sqlalchemy import delete  # noqa: PLC0415

    from autobot_shared.secrets_vault import VaultRef
    from models.secret import Secret  # noqa: PLC0415
    from services.envelope_secrets_service import EnvelopeSecretsService

    name = _vault_secret_name(provider_name, subject)
    # Remove old entry (if any) before re-sealing — avoids DEK sprawl.
    await session.execute(delete(Secret).where(Secret.name == name, Secret.owner_vault == owner_vault_str))
    await session.flush()

    owner_ref = VaultRef.parse(owner_vault_str)
    plaintext = json.dumps(token_data, separators=(",", ":")).encode("utf-8")

    if isinstance(created_by_id, str):
        # The JWT ``user_id`` claim is NOT guaranteed to be a UUID (e.g. the
        # auth-disabled "admin" principal, or an empty device-JWT claim), so a
        # malformed id must never break token persistence (#11849). Fall back to
        # the zero-UUID audit sentinel rather than raising on the write path.
        try:
            created_by_id = uuid.UUID(created_by_id)
        except ValueError:
            created_by_id = uuid.UUID("00000000-0000-0000-0000-000000000000")

    svc = EnvelopeSecretsService()
    await svc.create(
        session,
        owner_vault=owner_ref,
        name=name,
        secret_type=PROVIDER_AUTH_SECRET_TYPE,
        plaintext=plaintext,
        created_by=created_by_id,
    )
    await session.flush()


# ---------------------------------------------------------------------------
# OAuthAuth
# ---------------------------------------------------------------------------


class OAuthAuth(ProviderAuthStrategy):
    """OAuth 2.0 authorization-code + PKCE strategy with automatic token refresh.

    Tokens are stored in the unified secrets vault.  On ``resolve_token``:
    1. Load the stored token dict from the vault.
    2. If the access token is within ``_REFRESH_GRACE_SECONDS`` of expiry,
       refresh it via the token endpoint and persist the updated pair.
    3. Return the (possibly refreshed) access token.

    OAuth token acquisition (the initial code exchange) is done separately via
    the ``/api/llm-auth/oauth/initiate`` + ``/api/llm-auth/oauth/callback``
    endpoints (``provider_auth_router.py``), which write the initial token pair
    to the vault.

    The HTTP token exchange is reused from
    ``knowledge.connectors.oauth_flow.refresh_access_token`` — no duplication.
    """

    def __init__(
        self,
        *,
        provider_name: str,
        token_url: str,
        client_id: str,
        client_secret: str,
        owner_vault_str: str = "system",
        subject: str = "global",
    ) -> None:
        self._provider_name = provider_name
        self._token_url = token_url
        self._client_id = client_id
        self._client_secret = client_secret
        self._owner_vault_str = owner_vault_str
        self._subject = subject

    def is_vault_backed(self) -> bool:
        return True

    async def resolve_token(self, session: Any | None = None) -> str:
        if session is None:
            raise ProviderAuthError("OAuthAuth.resolve_token requires a DB session")
        token_data = await _vault_read_dual(
            session,
            provider_name=self._provider_name,
            subject=self._subject,
            owner_vault_str=self._owner_vault_str,
        )
        if token_data is None:
            raise ProviderAuthError(
                f"No OAuth token stored for provider {self._provider_name!r}. "
                "Complete the 'Sign in with {provider}' flow first."
            )
        return await self._ensure_fresh(session, token_data)

    @staticmethod
    def needs_refresh(token_data: dict) -> bool:
        """True when the access token is inside the refresh grace window.

        No recorded expiry (the provider sent no expires_in) means valid until revoked,
        as /status reports it -- not "expired", which would force a refresh every call (#19241).
        """
        expires_at = token_data.get("expires_at")
        return expires_at is not None and time.time() >= expires_at - _REFRESH_GRACE_SECONDS

    async def _ensure_fresh(self, session: Any, token_data: dict) -> str:
        if not self.needs_refresh(token_data):
            return token_data["access_token"]
        refresh_token = token_data.get("refresh_token")
        if not refresh_token:
            raise TokenExpiredError(f"OAuth token for {self._provider_name!r} expired and no refresh token available.")
        return await self._refresh(session, token_data, refresh_token)

    async def _refresh(self, session: Any, old_data: dict, refresh_token: str) -> str:
        from autobot_shared.http_egress_guard import assert_public_egress  # noqa: PLC0415
        from autobot_shared.security.ssrf_guard import SSRFError, pinned_connector  # noqa: PLC0415
        from autobot_shared.url_safety import get_oauth_allowed_hosts, require_allowlisted_https  # noqa: PLC0415
        from knowledge.connectors.oauth_flow import refresh_access_token  # noqa: PLC0415

        try:
            require_allowlisted_https(self._token_url, get_oauth_allowed_hosts())
        except ValueError as exc:
            raise ProviderAuthError(
                f"OAuth refresh blocked: unsafe token_url for {self._provider_name!r}: {exc}"
            ) from exc

        # Finding #2 (#11497): resolve the token host once, assert it is public,
        # and pin the outbound POST to that IP so DNS cannot be rebound to a
        # private address between validation and connect (TOCTOU rebinding).
        try:
            await assert_public_egress(self._token_url)  # public-only, as the sign-in endpoints do (#17576)
            connector = await pinned_connector(self._token_url)
        except (SSRFError, ValueError) as exc:
            raise ProviderAuthError(
                f"OAuth refresh blocked: token_url for {self._provider_name!r} is not publicly routable: {exc}"
            ) from exc

        logger.info("Refreshing OAuth token for provider %s", self._provider_name)
        try:
            resp = await refresh_access_token(
                self._token_url,
                self._client_id,
                self._client_secret,
                refresh_token,
                connector=connector,
            )
        except RuntimeError as exc:
            if getattr(exc, "error", "") == "invalid_grant":
                raise TokenRevokedError(f"OAuth refresh token for {self._provider_name!r} was rejected") from exc
            raise ProviderAuthError(f"OAuth refresh failed for {self._provider_name!r}: {exc}") from exc

        # Finding #3 (#11497): reject a mismatched token_type / issuer / audience
        # before the refreshed pair is persisted.
        validate_token_response(resp, provider_name=self._provider_name, client_id=self._client_id)

        new_data = _merge_token_response(old_data, resp)
        await _vault_write(
            session,
            provider_name=self._provider_name,
            subject=self._subject,
            owner_vault_str=self._owner_vault_str,
            token_data=new_data,
            created_by_id=old_data.get("created_by", "00000000-0000-0000-0000-000000000000"),
        )
        logger.info("OAuth token refreshed for provider %s", self._provider_name)
        return new_data["access_token"]

    def __repr__(self) -> str:
        return f"<OAuthAuth provider={self._provider_name!r} vault={self._owner_vault_str!r}>"


# ---------------------------------------------------------------------------
# DeviceCodeAuth
# ---------------------------------------------------------------------------


class DeviceCodeAuth(ProviderAuthStrategy):
    """RFC 8628 device-authorization grant strategy.

    Device code flow is headless-friendly: the backend polls the token endpoint
    after the user approves the device on a separate screen.  Once tokens are
    obtained they are stored in the vault and refresh is identical to OAuthAuth.

    The flow is initiated via ``/api/llm-auth/device/initiate`` and polled via
    ``/api/llm-auth/device/poll`` (see ``provider_auth_router.py``).
    ``resolve_token`` reads the stored token exactly like OAuthAuth.
    """

    def __init__(
        self,
        *,
        provider_name: str,
        token_url: str,
        client_id: str,
        device_authorization_url: str,
        owner_vault_str: str = "system",
        subject: str = "global",
    ) -> None:
        self._provider_name = provider_name
        self._token_url = token_url
        self._client_id = client_id
        self._device_authorization_url = device_authorization_url
        self._owner_vault_str = owner_vault_str
        self._subject = subject

    def is_vault_backed(self) -> bool:
        return True

    async def resolve_token(self, session: Any | None = None) -> str:
        if session is None:
            raise ProviderAuthError("DeviceCodeAuth.resolve_token requires a DB session")
        token_data = await _vault_read_dual(
            session,
            provider_name=self._provider_name,
            subject=self._subject,
            owner_vault_str=self._owner_vault_str,
        )
        if token_data is None:
            raise ProviderAuthError(
                f"No device-code token stored for provider {self._provider_name!r}. "
                "Complete the device-code sign-in flow first."
            )
        # Reuse OAuthAuth refresh logic for the stored tokens.
        _oauth = OAuthAuth(
            provider_name=self._provider_name,
            token_url=self._token_url,
            client_id=self._client_id,
            client_secret="",  # nosec B106  # device-code token refresh is public (no secret)
            owner_vault_str=self._owner_vault_str,
            subject=self._subject,
        )
        return await _oauth._ensure_fresh(session, token_data)

    @property
    def device_authorization_url(self) -> str:
        return self._device_authorization_url

    @property
    def client_id(self) -> str:
        return self._client_id

    def __repr__(self) -> str:
        return f"<DeviceCodeAuth provider={self._provider_name!r} vault={self._owner_vault_str!r}>"


# ---------------------------------------------------------------------------
# SessionAuth
# ---------------------------------------------------------------------------


class SessionAuth(ProviderAuthStrategy):
    """Bearer token from an existing subscription session.

    Stores the session token in the vault so it benefits from the same
    access-control as OAuth tokens.  Unlike OAuthAuth there is no automatic
    refresh — when the session expires the user must reconnect.
    """

    def __init__(
        self,
        *,
        provider_name: str,
        owner_vault_str: str = "system",
        subject: str = "global",
    ) -> None:
        self._provider_name = provider_name
        self._owner_vault_str = owner_vault_str
        self._subject = subject

    def is_vault_backed(self) -> bool:
        return True

    async def resolve_token(self, session: Any | None = None) -> str:
        if session is None:
            raise ProviderAuthError("SessionAuth.resolve_token requires a DB session")
        token_data = await _vault_read_dual(
            session,
            provider_name=self._provider_name,
            subject=self._subject,
            owner_vault_str=self._owner_vault_str,
        )
        if token_data is None:
            raise ProviderAuthError(
                f"No session token stored for provider {self._provider_name!r}. "
                "Re-authenticate via the provider settings."
            )
        expires_at = token_data.get("expires_at", 0)
        if expires_at and time.time() > expires_at:
            raise TokenExpiredError(f"Session token for {self._provider_name!r} expired. Please reconnect.")
        return token_data["access_token"]

    def __repr__(self) -> str:
        return f"<SessionAuth provider={self._provider_name!r} vault={self._owner_vault_str!r}>"


# ---------------------------------------------------------------------------
# Token audience / issuer / type validation (finding #3, #11497) -- the checks
# live in ``llm_shared.provider_token_response``; this is their provider data.
# ---------------------------------------------------------------------------

# Known OIDC issuers per provider — the ``iss`` claim of an id_token is matched
# against these prefixes (tenant / path suffixes vary). Providers absent here
# (e.g. github, gitlab) rarely mint an id_token; when one is present we still
# require its issuer host to be an allowlisted OAuth host (defence-in-depth).
_EXPECTED_ISSUER_PREFIXES: dict[str, tuple[str, ...]] = {
    "google": ("https://accounts.google.com",),
    "microsoft": ("https://login.microsoftonline.com/",),
}


__all__ = [
    "ProviderAuthStrategy",
    "ProviderAuthError",
    "TokenExpiredError",
    "StaticApiKeyAuth",
    "OAuthAuth",
    "DeviceCodeAuth",
    "SessionAuth",
    "PROVIDER_AUTH_SECRET_TYPE",
    "LEGACY_SUBJECT",
    "org_vault_subject",
    "user_vault_subject",
    "NEEDS_REAUTH_KEY",
    "LEGACY_FALLBACK_STOP_KEY",
    "TokenRevokedError",
    "USER_SUBJECT_PREFIX",
    "validate_token_response",
    "build_token_data",
    "_vault_write",
    "_vault_read",
    "_vault_read_dual",
]
