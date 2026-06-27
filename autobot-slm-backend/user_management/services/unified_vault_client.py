# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""HTTP client for the autobot-backend unified-secrets System vault (#10153).

The SLM Manager is a *client* of the unified-secrets API.  It uses its
registered service identity (``SLM_SERVICE_ID`` / ``SLM_SERVICE_KEY``) and the
HMAC ``sign_request`` helper from ``autobot_shared.http_client`` to reach the
System-vault endpoints at ``/api/v2/secrets/system`` on autobot-backend.

Integration shape: option (a) — HTTP client with X-Service-* HMAC auth.
The SLM and autobot-backend may run on separate machines (distributed topology),
so sharing the DB session directly is not guaranteed; the HTTP boundary is the
safe canonical choice.

Configuration (read from env at module import):
    SLM_SERVICE_ID      — service identifier registered in the backend's Redis
                          key registry (default: "slm-backend").
    SLM_SERVICE_KEY     — 256-bit hex-encoded HMAC secret (must match the key
                          the backend stored under service:key:{service_id}).
    SLM_AUTHORITY_BASE_URL — base URL of autobot-backend (e.g. http://127.0.0.1:8001).

Never log the service key or any secret value.
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from typing import Any

import aiohttp

from autobot_shared.http_client import sign_request

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level configuration — read once from env, never hard-coded.
# ---------------------------------------------------------------------------
_SERVICE_ID: str = os.getenv("SLM_SERVICE_ID", "slm-backend")
_SERVICE_KEY: str = os.getenv("SLM_SERVICE_KEY", "")
_BACKEND_BASE_URL: str = os.getenv("SLM_AUTHORITY_BASE_URL", "http://127.0.0.1:8001").rstrip("/")
_SYSTEM_VAULT_PATH = "/api/v2/secrets/system"
_REQUEST_TIMEOUT_SECONDS: float = float(os.getenv("SLM_VAULT_CLIENT_TIMEOUT", "10"))


class UnifiedVaultClientError(Exception):
    """Raised when the vault API call fails (HTTP error, config missing, …)."""


class UnifiedVaultSecretNotFound(UnifiedVaultClientError):
    """404 from the vault API — secret does not exist."""


def is_configured() -> bool:
    """Return True when a service key is present so the client can authenticate.

    Callers use this to decide whether the unified vault is the active store
    (configured) or whether to fall back to the legacy SLM-local store during
    the rollout window (not yet configured).
    """
    return bool(_SERVICE_KEY)


def _check_configured() -> None:
    """Raise early with a clear message when the service key is absent."""
    if not _SERVICE_KEY:
        raise UnifiedVaultClientError(
            "SLM_SERVICE_KEY is not set; unified-vault client cannot authenticate. "
            "Set SLM_SERVICE_KEY (hex-encoded 256-bit) and SLM_SERVICE_ID in slm-secrets.env."
        )


def _auth_headers(method: str, path: str) -> dict[str, str]:
    """Build HMAC auth headers for a single request."""
    return sign_request(_SERVICE_ID, _SERVICE_KEY, method, path, int(time.time()))


async def _request(method: str, path: str, **kwargs: Any) -> Any:
    """Issue one authenticated HTTP request; map status codes to exceptions."""
    _check_configured()
    url = f"{_BACKEND_BASE_URL}{path}"
    headers = _auth_headers(method, path)
    timeout = aiohttp.ClientTimeout(total=_REQUEST_TIMEOUT_SECONDS)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.request(method, url, headers=headers, **kwargs) as resp:
            if resp.status == 404:
                raise UnifiedVaultSecretNotFound(f"secret not found at {path}")
            if resp.status == 204:
                return None
            if not resp.ok:
                body = await resp.text()
                raise UnifiedVaultClientError(f"vault API {method} {path} returned {resp.status}: {body[:200]}")
            return await resp.json()


async def vault_create(name: str, secret_type: str, value: str) -> dict[str, Any]:
    """Create a secret in the system vault; returns the metadata dict."""
    payload = {"owner_vault": "system", "name": name, "secret_type": secret_type, "value": value}
    # Log only the (non-sensitive) type label — CodeQL taints `name` because this
    # function also receives the secret `value`; the name is an identifier, not a value.
    logger.info("unified-vault: creating system secret type=%s", secret_type)
    return await _request("POST", _SYSTEM_VAULT_PATH, json=payload)


async def vault_read(secret_id: uuid.UUID) -> str:
    """Read and return the plaintext value of a system-vault secret."""
    path = f"{_SYSTEM_VAULT_PATH}/{secret_id}"
    data = await _request("GET", path)
    if not isinstance(data, dict) or "value" not in data:
        raise UnifiedVaultClientError(f"vault read for {secret_id} returned no 'value' field")
    return data["value"]


async def vault_rotate(secret_id: uuid.UUID, new_value: str) -> dict[str, Any]:
    """Re-seal a system-vault secret with a new plaintext value (rotate_value)."""
    path = f"{_SYSTEM_VAULT_PATH}/{secret_id}"
    logger.info("unified-vault: rotating system secret id=%s", secret_id)
    return await _request("PUT", path, json={"value": new_value})


async def vault_delete(secret_id: uuid.UUID) -> None:
    """Delete a system-vault secret."""
    path = f"{_SYSTEM_VAULT_PATH}/{secret_id}"
    logger.info("unified-vault: deleting system secret id=%s", secret_id)
    await _request("DELETE", path)


async def vault_list() -> list[dict[str, Any]]:
    """List system-vault secret metadata accessible to this service identity."""
    return await _request("GET", _SYSTEM_VAULT_PATH)


async def vault_rewrap_kek(secret_id: uuid.UUID, new_root_key_b64: str) -> dict[str, Any]:
    """Rewrap DEKs under a new root key (KEK rotation, plaintext unchanged).

    ``new_root_key_b64`` must be URL-safe base64 encoding of 32 bytes — the
    same format the ``/api/v2/secrets/system/{id}/rewrap`` endpoint expects.

    Uses the **service-auth** system-vault rewrap route (not the user-auth
    ``/{id}/rewrap``) so the SLM service identity can perform KEK rotation.
    """
    path = f"{_SYSTEM_VAULT_PATH}/{secret_id}/rewrap"
    logger.info("unified-vault: rewrapping KEK for secret id=%s", secret_id)
    return await _request("POST", path, json={"new_root_key": new_root_key_b64})
