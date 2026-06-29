# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""SSO client-secret rotation service (#10154).

Two rotation modes:
- **KEK rotation** (``rotate_kek``): rewrap the vault DEK under a new root key;
  the sealed plaintext is unchanged.  Use this for periodic key-hygiene cycles.
- **Value rotation** (``rotate_value``): operator supplies a new client secret;
  the vault re-seals with a fresh DEK.  Use this when the secret is changed at
  the IdP.

Warn-on-stale
-------------
Each SSO secret stores its last-rotation timestamp as ``{field}_rotated_at`` in
the provider's config JSONB.  When the age exceeds ``SSO_SECRET_MAX_AGE_DAYS``
(module-level constant derived from env var — never hard-coded) a warning is
surfaced in the log AND returned in the rotation-status response so the
``/health`` dashboard (#10156) can display it.

Audit
-----
Every rotation writes an ``AuditLog`` row (category="sso", action="rotate_kek"
or "rotate_value") so there is a durable rotation history per provider.

Never log secret values.
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level constant: max secret age before a staleness warning is emitted.
# Never hard-coded — reads from env; falls back to 90 days.
# Pattern mirrors autobot-backend/chat_history/cache.py.
# ---------------------------------------------------------------------------
_DEFAULT_MAX_AGE_DAYS = 90


def _resolve_max_age_days() -> int:
    raw = os.getenv("SSO_SECRET_MAX_AGE_DAYS", str(_DEFAULT_MAX_AGE_DAYS))
    try:
        value = int(raw)
    except ValueError:
        logger.warning(
            "SSO_SECRET_MAX_AGE_DAYS=%r is not an integer; falling back to %d days",
            raw,
            _DEFAULT_MAX_AGE_DAYS,
        )
        return _DEFAULT_MAX_AGE_DAYS
    if value <= 0:
        logger.warning(
            "SSO_SECRET_MAX_AGE_DAYS=%d must be positive; falling back to %d days",
            value,
            _DEFAULT_MAX_AGE_DAYS,
        )
        return _DEFAULT_MAX_AGE_DAYS
    return value


SSO_SECRET_MAX_AGE_DAYS: int = _resolve_max_age_days()


class SSORotationError(Exception):
    """Raised when a rotation operation fails."""


def _rotated_at_key(field: str) -> str:
    return f"{field}_rotated_at"


def _vault_id_key(field: str) -> str:
    return f"{field}_vault_id"


def _is_stale(rotated_at_iso: str | None) -> bool:
    """Return True when the secret has not been rotated within max-age window."""
    if rotated_at_iso is None:
        return True  # unknown age → treat as stale
    try:
        rotated_at = datetime.fromisoformat(rotated_at_iso)
    except ValueError:
        return True
    if rotated_at.tzinfo is None:
        rotated_at = rotated_at.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - rotated_at > timedelta(days=SSO_SECRET_MAX_AGE_DAYS)


async def _write_audit(
    session: AsyncSession,
    *,
    provider_id: uuid.UUID,
    action: str,
    actor_id: str | None,
    details: dict[str, Any],
) -> None:
    """Append an audit row for this rotation event (best-effort).

    Reuses the canonical ``create_audit_log`` helper so the row matches the
    ``audit_logs`` schema (``log_id``/``user_id``/``extra_data`` — there is no
    ``actor_id``/``details`` column). A failure here never aborts the rotation.
    """
    try:
        from api.security import create_audit_log

        await create_audit_log(
            session,
            category="security",
            action=action,
            user_id=actor_id,
            resource_type="sso_provider",
            resource_id=str(provider_id),
            description=f"SSO secret {action} for field {details.get('field')}",
            extra_data=details,
        )
    except Exception as exc:
        logger.warning("SSO rotation audit write failed: %s", type(exc).__name__)


async def _update_provider_config(session: AsyncSession, provider_id: uuid.UUID, updates: dict[str, Any]) -> None:
    """Merge *updates* into the provider's config JSONB and flush."""
    from user_management.models.sso import SSOProvider

    row = await session.execute(select(SSOProvider).where(SSOProvider.id == provider_id))
    provider = row.scalar_one_or_none()
    if provider is None:
        raise SSORotationError(f"SSO provider {provider_id} not found")
    provider.config = {**provider.config, **updates}
    await session.flush()


def check_staleness(provider_id: uuid.UUID, config: dict[str, Any], fields: list[str] | None = None) -> dict[str, Any]:
    """Return a staleness report for a provider's secrets.

    Returns a dict mapping each field to whether it is stale, plus its
    last-rotation timestamp.  Suitable for embedding in a health response.
    """
    fields = fields or ["client_secret", "bind_password"]
    report: dict[str, Any] = {}
    for field in fields:
        rotated_at = config.get(_rotated_at_key(field))
        stale = _is_stale(rotated_at)
        if stale:
            logger.warning(
                "SSO secret stale: provider=%s field=%s last_rotated=%s max_age_days=%d",
                provider_id,
                field,
                rotated_at,
                SSO_SECRET_MAX_AGE_DAYS,
            )
        report[field] = {
            "stale": stale,
            "last_rotated_at": rotated_at,
            "max_age_days": SSO_SECRET_MAX_AGE_DAYS,
        }
    return report


async def rotate_kek(
    session: AsyncSession,
    *,
    provider_id: uuid.UUID,
    field: str,
    new_root_key_b64: str,
    actor_id: str | None = None,
) -> dict[str, Any]:
    """Rewrap the vault DEK for one SSO secret field under a new root key.

    The sealed plaintext is unchanged (key-hygiene rotation only).
    Returns metadata from the vault response.
    """
    from user_management.models.sso import SSOProvider
    from user_management.services.vault_client import VaultClientError, vault_rewrap_kek

    row = await session.execute(select(SSOProvider).where(SSOProvider.id == provider_id))
    provider = row.scalar_one_or_none()
    if provider is None:
        raise SSORotationError(f"SSO provider {provider_id} not found")

    vault_id_str = provider.config.get(_vault_id_key(field))
    if not vault_id_str:
        raise SSORotationError(
            f"field {field!r} has no vault_id in config for provider {provider_id}; " "run migrate_to_vault first"
        )
    vault_id = uuid.UUID(vault_id_str)

    try:
        meta = await vault_rewrap_kek(vault_id, new_root_key_b64)
    except VaultClientError as exc:
        raise SSORotationError(f"KEK rotation failed for provider {provider_id} field {field}: {exc}") from exc

    now_iso = datetime.now(timezone.utc).isoformat()
    await _update_provider_config(session, provider_id, {_rotated_at_key(field): now_iso})
    await _write_audit(
        session,
        provider_id=provider_id,
        action="rotate_kek",
        actor_id=actor_id,
        details={"field": field, "vault_id": str(vault_id), "rotated_at": now_iso},
    )
    logger.info("SSO KEK rotation complete: provider=%s field=%s vault_id=%s", provider_id, field, vault_id)
    return {"vault_id": str(vault_id), "rotated_at": now_iso, "action": "rotate_kek", **meta}


async def rotate_value(
    session: AsyncSession,
    *,
    provider_id: uuid.UUID,
    field: str,
    new_value: str,
    actor_id: str | None = None,
) -> dict[str, Any]:
    """Re-seal a vault secret with a new plaintext value (operator-supplied rotation).

    Updates the vault entry and timestamps the rotation in the provider config.
    Returns metadata from the vault response.
    """
    from user_management.models.sso import SSOProvider
    from user_management.services.vault_client import VaultClientError, vault_rotate

    row = await session.execute(select(SSOProvider).where(SSOProvider.id == provider_id))
    provider = row.scalar_one_or_none()
    if provider is None:
        raise SSORotationError(f"SSO provider {provider_id} not found")

    vault_id_str = provider.config.get(_vault_id_key(field))
    if not vault_id_str:
        raise SSORotationError(
            f"field {field!r} has no vault_id in config for provider {provider_id}; " "run migrate_to_vault first"
        )
    vault_id = uuid.UUID(vault_id_str)

    try:
        meta = await vault_rotate(vault_id, new_value)
    except VaultClientError as exc:
        raise SSORotationError(f"value rotation failed for provider {provider_id} field {field}: {exc}") from exc

    now_iso = datetime.now(timezone.utc).isoformat()
    await _update_provider_config(session, provider_id, {_rotated_at_key(field): now_iso})
    await _write_audit(
        session,
        provider_id=provider_id,
        action="rotate_value",
        actor_id=actor_id,
        details={"field": field, "vault_id": str(vault_id), "rotated_at": now_iso},
    )
    logger.info("SSO value rotation complete: provider=%s field=%s vault_id=%s", provider_id, field, vault_id)
    return {"vault_id": str(vault_id), "rotated_at": now_iso, "action": "rotate_value", **meta}
