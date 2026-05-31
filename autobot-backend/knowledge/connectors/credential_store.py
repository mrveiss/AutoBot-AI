# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""
ConnectorCredentialStore — ADR-007 credential isolation shim.

Bridges ConnectorConfig ↔ SecretsService so that sensitive auth fields
(tokens, keys, passwords) are encrypted at rest and never written to Redis.
"""

import asyncio
import json
from autobot_shared.logging_manager import get_logger
from autobot_shared.singleton_factory import lazy_singleton

logger = get_logger(__name__)

_AUTH_TYPE_TO_SECRET_TYPE: dict = {
    "OAuthRefreshAuth": "connector_oauth_token",
    "BearerAuth": "connector_api_key",
    "ApiKeyAuth": "connector_api_key",
    "BasicAuth": "connector_password",
}


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
        """
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

    async def revoke(self, secret_id: str, owner_id: str) -> None:
        """Delete the secret. Called on connector delete."""
        await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: self._svc.delete_secret(
                secret_id=secret_id,
                deleted_by=owner_id,
            ),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

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
