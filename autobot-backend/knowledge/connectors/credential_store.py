# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
ConnectorCredentialStore — ADR-007 credential isolation shim.

Bridges ConnectorConfig ↔ SecretsService so that sensitive auth fields
(tokens, keys, passwords) are encrypted at rest and never written to Redis.
"""

import asyncio
import json
import os
from datetime import timedelta

from autobot_shared.logging_manager import get_logger
from autobot_shared.singleton_factory import lazy_singleton
from autobot_shared.time_utils import now_utc, parse_utc_iso
from services.unified_credential_read import load_imported_credential
from services.unified_credential_write import delete_credential_from_unified, mirror_credential_to_unified

logger = get_logger(__name__)

# Feature flags (expand/contract cutover — #10088 Task 3c-2), both default off → behaviour
# is byte-identical to before. READ: reads try the unified envelope store first (matching the
# legacy id via the ``imported_from_sqlite`` marker) and fall back to SQLite. WRITE: every
# write also best-effort mirrors into the unified store (SQLite stays canonical). The two are
# independent so dual-write can be enabled first to populate the unified store, then read.
UNIFIED_READ_ENV = "AUTOBOT_SECRETS_UNIFIED_READ"
UNIFIED_WRITE_ENV = "AUTOBOT_SECRETS_UNIFIED_WRITE"


def _unified_read_enabled() -> bool:
    return os.environ.get(UNIFIED_READ_ENV, "false").strip().lower() in ("1", "true", "yes")


def _unified_write_enabled() -> bool:
    return os.environ.get(UNIFIED_WRITE_ENV, "false").strip().lower() in ("1", "true", "yes")


_AUTH_TYPE_TO_SECRET_TYPE: dict = {
    "OAuthRefreshAuth": "connector_oauth_token",
    "BearerAuth": "connector_api_key",
    "ApiKeyAuth": "connector_api_key",
    "BasicAuth": "connector_password",
}

# Refresh an OAuth access token this many seconds before its stated expiry, so
# in-flight requests never race a hard expiry. Not a cache TTL — a safety skew.
ACCESS_TOKEN_REFRESH_SKEW_SECONDS = 60


class ConnectorCredentialStore:
    """Bridges ConnectorConfig ↔ SecretsService for credential isolation (ADR-007).

    All methods are async-safe; the underlying SecretsService calls are
    synchronous and are dispatched via run_in_executor to avoid blocking the
    event loop.
    """

    def __init__(self, secrets_service) -> None:
        self._svc = secrets_service

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def store(
        self,
        connector_id: str,
        owner_id: str,
        auth_cls: type,
        config: dict,
    ) -> tuple[str, dict]:
        """Extract sensitive fields from config, store them encrypted.

        Returns (secret_id, sanitized_config) where sanitized_config has
        sensitive fields removed.  Raises ValueError when auth_cls has no
        __sensitive_fields__.
        """
        sensitive = self._sensitive_fields(auth_cls)
        creds = {k: v for k, v in config.items() if k in sensitive}
        sanitized = {k: v for k, v in config.items() if k not in sensitive}

        name = f"connector:{connector_id}:auth"
        secret_type = _AUTH_TYPE_TO_SECRET_TYPE.get(auth_cls.__name__, "connector_api_key")

        result = await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: self._svc.create_secret(
                name=name,
                secret_type=secret_type,
                value=json.dumps(creds, ensure_ascii=False),
                scope="user",
                created_by=owner_id,
            ),
        )
        if _unified_write_enabled():
            await mirror_credential_to_unified(
                result["id"], owner_id, json.dumps(creds, ensure_ascii=False), name=name, secret_type=secret_type
            )
        return result["id"], sanitized

    async def load(
        self,
        secret_id: str,
        sanitized_config: dict,
        auth_cls: type,
        owner_id: str,
    ) -> dict:
        """Reconstruct full config by merging decrypted credentials back in.

        Raises PermissionError when owner_id does not match the stored secret.
        Raises LookupError when secret_id is not found or has expired.

        When the unified-read flag is on, the unified envelope store is tried first
        (by the legacy-id marker) and the SQLite store is the fallback.
        """
        secret = None
        if _unified_read_enabled():
            secret = await load_imported_credential(secret_id, owner_id)
        if secret is None:
            secret = await asyncio.get_running_loop().run_in_executor(
                None,
                lambda: self._svc.get_secret(
                    secret_id=secret_id,
                    include_value=True,
                    accessed_by=owner_id,
                ),
            )
        if secret is None:
            raise LookupError(f"Credential secret {secret_id!r} not found or expired")

        stored_owner = secret.get("created_by") or ""
        if stored_owner and stored_owner != owner_id:
            raise PermissionError(f"owner_id mismatch for secret {secret_id!r}: expected {stored_owner!r}")

        creds = json.loads(secret["value"])
        return {**sanitized_config, **creds}

    async def rotate(
        self,
        secret_id: str,
        new_credentials: dict,
        owner_id: str,
    ) -> None:
        """Replace the stored secret value with new_credentials in-place."""
        existing = await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: self._svc.get_secret(secret_id=secret_id, include_value=True),
        )
        if existing is None:
            raise LookupError(f"Credential secret {secret_id!r} not found or expired")
        stored_owner = existing.get("created_by") or ""
        if stored_owner and stored_owner != owner_id:
            raise PermissionError(f"owner_id mismatch for secret {secret_id!r}: expected {stored_owner!r}")

        current_creds = json.loads(existing["value"])
        current_creds.update(new_credentials)
        new_value = json.dumps(current_creds, ensure_ascii=False)

        await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: self._svc.update_secret(
                secret_id=secret_id,
                value=new_value,
                updated_by=owner_id,
            ),
        )
        if _unified_write_enabled():
            await mirror_credential_to_unified(secret_id, owner_id, new_value)

    async def revoke(self, secret_id: str, owner_id: str) -> None:
        """Delete the secret. Called on connector delete."""
        await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: self._svc.delete_secret(
                secret_id=secret_id,
                deleted_by=owner_id,
            ),
        )
        if _unified_write_enabled():
            await delete_credential_from_unified(secret_id, owner_id)

    # ------------------------------------------------------------------
    # OAuth 2.0 authorization-code tokens (ADR-007 §7 / GH#9019)
    # ------------------------------------------------------------------

    async def store_oauth(
        self,
        connector_id: str,
        owner_id: str,
        provider: str,
        token_response: dict,
        client_id: str,
        client_secret: str,
        token_url: str,
        scopes: list,
    ) -> str:
        """Persist a token set obtained via the OAuth auth-code flow.

        Stores a self-contained credential bundle (access + refresh token,
        client app creds, token endpoint) so :meth:`get_access_token` can
        refresh later without re-reading provider config.  Returns the secret id.
        """
        creds = self._oauth_bundle(token_response, client_id, client_secret, token_url, scopes, provider)
        name = f"connector:{connector_id}:auth"
        result = await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: self._svc.create_secret(
                name=name,
                secret_type="connector_oauth_token",  # nosec B106 - SecretType label, not a credential
                value=json.dumps(creds, ensure_ascii=False),
                scope="user",
                created_by=owner_id,
                metadata={"provider": provider, "connector_id": connector_id},
            ),
        )
        if _unified_write_enabled():
            await mirror_credential_to_unified(
                result["id"],
                owner_id,
                json.dumps(creds, ensure_ascii=False),
                name=name,
                secret_type="connector_oauth_token",  # nosec B106 - SecretType label, not a credential
            )
        return result["id"]

    async def get_access_token(self, secret_id: str, owner_id: str) -> str:
        """Return a valid access token, refreshing + rotating the secret in place.

        Raises PermissionError on owner mismatch, LookupError when the secret is
        missing or holds no refresh token while the access token is expired.
        Propagates RuntimeError from the token endpoint on a failed refresh.
        """
        secret = await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: self._svc.get_secret(secret_id=secret_id, include_value=True, accessed_by=owner_id),
        )
        if secret is None:
            raise LookupError(f"OAuth secret {secret_id!r} not found or expired")
        stored_owner = secret.get("created_by") or ""
        if stored_owner and stored_owner != owner_id:
            raise PermissionError(f"owner_id mismatch for secret {secret_id!r}: expected {stored_owner!r}")

        creds = json.loads(secret["value"])
        access_token = creds.get("access_token")
        if access_token and not self._access_token_expired(creds.get("access_token_expires_at")):
            return access_token

        refresh_token = creds.get("refresh_token")
        if not refresh_token:
            raise LookupError(
                f"OAuth secret {secret_id!r} access token expired and no refresh token — re-auth required"
            )

        from knowledge.connectors import oauth_flow

        token_response = await oauth_flow.refresh_access_token(
            creds["token_url"], creds["client_id"], creds["client_secret"], refresh_token
        )
        creds["access_token"] = token_response["access_token"]
        creds["access_token_expires_at"] = self._expiry_iso(token_response.get("expires_in"))
        if token_response.get("refresh_token"):
            # Providers like GitLab rotate the refresh token on each use.
            creds["refresh_token"] = token_response["refresh_token"]

        await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: self._svc.update_secret(
                secret_id=secret_id,
                value=json.dumps(creds, ensure_ascii=False),
                updated_by=owner_id,
            ),
        )
        if _unified_write_enabled():
            await mirror_credential_to_unified(secret_id, owner_id, json.dumps(creds, ensure_ascii=False))
        return creds["access_token"]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @classmethod
    def _oauth_bundle(
        cls,
        token_response: dict,
        client_id: str,
        client_secret: str,
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
            "token_type": token_response.get("token_type", "Bearer"),
            "scope": token_response.get("scope", " ".join(scopes)),
            "client_id": client_id,
            "client_secret": client_secret,
            "token_url": token_url,
        }

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

    @staticmethod
    def _access_token_expired(expires_at_iso: str | None) -> bool:
        """True when the access token is unusable within the refresh skew window.

        A missing expiry is treated as non-expiring (some providers omit it).
        """
        if not expires_at_iso:
            return False
        try:
            expires_at = parse_utc_iso(expires_at_iso)
        except (ValueError, TypeError):
            return True
        return now_utc() + timedelta(seconds=ACCESS_TOKEN_REFRESH_SKEW_SECONDS) >= expires_at

    @staticmethod
    def _sensitive_fields(auth_cls: type) -> frozenset:
        fields = getattr(auth_cls, "__sensitive_fields__", None)
        if fields is None:
            raise ValueError(f"{auth_cls.__name__} has no __sensitive_fields__ — cannot separate credentials")
        return fields


# ---------------------------------------------------------------------------
# Module-level singleton factory (ADR-007, GH#9099)
# ---------------------------------------------------------------------------


def _build_credential_store() -> "ConnectorCredentialStore":
    from services.secrets_service import get_secrets_service

    return ConnectorCredentialStore(get_secrets_service())


get_credential_store = lazy_singleton(_build_credential_store)


def reset_credential_store() -> None:
    """Reset the singleton (test isolation / key rotation).

    Creates a fresh lazy_singleton closure so the next get_credential_store()
    call rebuilds with the current SecretsService instance.
    """
    global get_credential_store
    get_credential_store = lazy_singleton(_build_credential_store)
