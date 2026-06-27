# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""HTTP client for the autobot-backend unified-secrets System vault (#10153, #10492).

The SLM Manager is a *client* of the unified-secrets API.  Auth priority:

1. ``AUTOBOT_INTERNAL_API_KEY`` (Option A — #10492): the shared internal-API key
   that the SLM already uses for voice/personality proxying.  Sent as
   ``X-Internal-API-Key`` header; the backend maps it to synthetic service_id
   ``"slm-backend"``.  This is the default and requires no extra provisioning.
2. HMAC ``X-Service-*`` (legacy / per-service key): used when ``SLM_SERVICE_KEY``
   is set but ``AUTOBOT_INTERNAL_API_KEY`` is absent.  Present for
   forward-compatibility with future per-service key deployments.

``is_configured()`` returns True when *either* credential is available, so the
unified-vault path activates on any standard deployment that sets
``AUTOBOT_INTERNAL_API_KEY`` (no ``SLM_SERVICE_KEY`` provisioning needed).

Configuration (read from env at module import):
    AUTOBOT_INTERNAL_API_KEY — shared internal API key (primary; set on both services).
    SLM_SERVICE_ID      — service identifier for HMAC path (default: "slm-backend").
    SLM_SERVICE_KEY     — 256-bit hex-encoded HMAC secret (HMAC path fallback).
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
_INTERNAL_API_KEY: str = os.getenv("AUTOBOT_INTERNAL_API_KEY", "")  # primary auth (#10492 Option A)
_SERVICE_ID: str = os.getenv("SLM_SERVICE_ID", "slm-backend")
_SERVICE_KEY: str = os.getenv("SLM_SERVICE_KEY", "")  # HMAC fallback
_BACKEND_BASE_URL: str = os.getenv("SLM_AUTHORITY_BASE_URL", "http://127.0.0.1:8001").rstrip("/")
_SYSTEM_VAULT_PATH = "/api/v2/secrets/system"
_REQUEST_TIMEOUT_SECONDS: float = float(os.getenv("SLM_VAULT_CLIENT_TIMEOUT", "10"))


class UnifiedVaultClientError(Exception):
    """Raised when the vault API call fails (HTTP error, config missing, …)."""


class UnifiedVaultSecretNotFound(UnifiedVaultClientError):
    """404 from the vault API — secret does not exist."""


def is_configured() -> bool:
    """Return True when either auth credential is available.

    Option A (#10492): ``AUTOBOT_INTERNAL_API_KEY`` (primary, no extra provisioning).
    HMAC fallback: ``SLM_SERVICE_KEY`` (per-service key stored in Redis).
    Callers use this to gate the unified-vault path vs the legacy local store.
    """
    return bool(_INTERNAL_API_KEY or _SERVICE_KEY)


def _check_configured() -> None:
    """Raise early with a clear message when no auth credential is configured."""
    if not (_INTERNAL_API_KEY or _SERVICE_KEY):
        raise UnifiedVaultClientError(
            "No vault auth credential configured; set AUTOBOT_INTERNAL_API_KEY (shared internal key) "
            "or SLM_SERVICE_KEY (hex-encoded 256-bit HMAC key) in slm-secrets.env."
        )


def _auth_headers(method: str, path: str) -> dict[str, str]:
    """Build auth headers for a single request.

    Preference order: X-Internal-API-Key (Option A, #10492) when available; fall
    back to HMAC X-Service-* headers when only SLM_SERVICE_KEY is set.
    """
    if _INTERNAL_API_KEY:
        return {"X-Internal-API-Key": _INTERNAL_API_KEY}
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
