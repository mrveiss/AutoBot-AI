# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LLM provider-key capture + vault-backed runtime resolution (#10088 Task 7).

First-time-setup flow: an admin captures an LLM provider key (OpenAI,
Anthropic, ...) through the API-key setup wizard
(``autobot-frontend/src/components/settings/ApiKeySetupWizard.vue``), which
posts to the legacy ``POST /api/secrets/`` endpoint (``api/secrets.py``) --
today's *only* write path for these values, since ``SecretUpdateRequest`` has
no ``value`` field (rotation is delete+recreate). This module adds two halves
that endpoint never had:

1. **Capture** (:func:`mirror_provider_key_best_effort`) -- mirrors a
   provider-key value into the System vault at the moment it's created,
   idempotently (create once, rotate on a later re-capture of the same
   name). Scoped strictly to :data:`LLM_PROVIDER_KEY_NAMES` -- the generic
   ``secrets.json`` -> envelope migration is Task 3's importer (`#13052`
   notes nothing invokes it yet); this hook does not duplicate that work,
   it only guarantees LLM provider keys specifically are never vault-blind.

2. **Runtime resolution** (:func:`hydrate_provider_keys_from_vault` +
   :func:`resolve_provider_key`) -- the actual runtime reader,
   ``llm_shared.provider_registry._populate_default_providers``, only ever
   read ``ssot_config`` (env vars) and never consulted the legacy secrets
   store *or* the vault -- a value captured via the wizard was, until this
   change, write-only (unreachable at runtime; the same class of defect
   Task 5 hit for connector credentials). :func:`hydrate_provider_keys_from_vault`
   runs once at startup (``initialization/lifespan.py``, Phase 1, after the
   DB is initialised) and populates a process-lifetime cache consulted
   *only* when the env var itself is unset, so an Ansible-provisioned
   deployment's env vars remain authoritative and unaffected (dual-read,
   env-first -- no provider key becomes unreachable mid-cutover).

Never logs a secret value.
"""

from __future__ import annotations

import logging
import os
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.secrets_vault import VaultKind, VaultRef
from models.secret import Secret

logger = logging.getLogger(__name__)

#: LLM provider API-key env-var names eligible for System-vault capture +
#: resolution. Each name has a real runtime reader in
#: ``llm_shared.provider_registry._populate_default_providers`` -- the actual
#: LLM-call routing path (not the adapter-listing-only AdapterRegistry).
#: HF_TOKEN is deliberately excluded: it is captured via a different flow
#: (the SLM setup wizard's ``system_secrets``, already migrated by Task 6a).
LLM_PROVIDER_KEY_NAMES: frozenset[str] = frozenset(
    {
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GROQ_API_KEY",
        "MISTRAL_API_KEY",
        "OPENROUTER_API_KEY",
        "NOUS_API_KEY",
        "CUSTOM_OPENAI_API_KEY",
    }
)

_SYSTEM_VAULT = VaultRef(VaultKind.SYSTEM)

#: Process-lifetime cache of provider keys hydrated from the System vault.
#: Consulted only when the env var itself is unset (env wins). Never logged,
#: never written back to os.environ (child-process env sanitization is a
#: separate, pre-existing concern -- see services/execution/env_sanitizer.py).
_hydrated_keys: dict[str, str] = {}


def resolve_provider_key(env_var: str, config_value: str) -> str:
    """Env var wins (today's authoritative source); else the vault-hydrated cache.

    Called from ``llm_shared.provider_registry._populate_default_providers`` in
    place of a bare ``config.<x>_api_key`` read, so a key captured only via the
    setup wizard (never set as an env var) still resolves at runtime.
    """
    return config_value or _hydrated_keys.get(env_var, "")


async def _find_system_secret_id(session: AsyncSession, name: str) -> uuid.UUID | None:
    """Return the id of the active System-vault secret named *name*, if any."""
    result = await session.execute(
        select(Secret.id).where(
            Secret.owner_vault == _SYSTEM_VAULT.to_str(),
            Secret.name == name,
            Secret.is_active.is_(True),
        )
    )
    return result.scalars().first()


async def capture_provider_key(
    session: AsyncSession, *, name: str, plaintext: str, created_by: uuid.UUID, root_key: bytes | None = None
) -> bool:
    """Mirror an LLM-provider-key value into the System vault (idempotent).

    Creates a new System-vault secret the first time *name* is captured;
    rotates the value on a later re-capture (an admin legitimately changing a
    key). No-op for any name outside :data:`LLM_PROVIDER_KEY_NAMES` -- this
    hook is intentionally scoped to LLM provider keys, not a generic secrets
    mirror. Raises on a genuine vault error; callers use
    :func:`mirror_provider_key_best_effort` for the best-effort wrapper.
    ``root_key`` defaults to loading ``AUTOBOT_SECRETS_ROOT_KEY`` (production
    behaviour); tests pass an explicit key.
    """
    if name not in LLM_PROVIDER_KEY_NAMES:
        return False
    from services.envelope_secrets_service import EnvelopeSecretsService

    service = EnvelopeSecretsService(root_key=root_key)
    existing_id = await _find_system_secret_id(session, name)
    if existing_id is not None:
        await service.rotate_value(
            session,
            secret_id=existing_id,
            new_plaintext=plaintext.encode("utf-8"),
            actor_vaults={_SYSTEM_VAULT},
        )
    else:
        await service.create(
            session,
            owner_vault=_SYSTEM_VAULT,
            name=name,
            secret_type="api_key",  # nosec B106  # SecretType label, not a credential
            plaintext=plaintext.encode("utf-8"),
            created_by=created_by,
        )
    return True


async def mirror_provider_key_best_effort(name: str, value: str, created_by: uuid.UUID) -> bool:
    """Best-effort System-vault mirror for one legacy ``/api/secrets/`` capture.

    Never raises: a dev/test environment with no root key configured, or any
    DB error, must not turn a successful legacy ``secrets.json`` write into a
    failed request. Returns True when the vault copy was written/updated.
    """
    if name not in LLM_PROVIDER_KEY_NAMES:
        return False
    try:
        from user_management.database import get_async_session_factory

        factory = get_async_session_factory()
        async with factory() as session:
            wrote = await capture_provider_key(session, name=name, plaintext=value, created_by=created_by)
            if wrote:
                await session.commit()
            return wrote
    except Exception as exc:  # noqa: BLE001 - vault is optional in dev/test; never break the caller
        logger.warning("provider-key-vault: mirror failed name=%s: %s", name, type(exc).__name__)
        return False


async def hydrate_provider_keys_from_vault(session: AsyncSession, *, root_key: bytes | None = None) -> list[str]:
    """Populate the process cache from the System vault for any unset env var.

    Called once at FastAPI startup, after the DB is initialised. Env vars
    always win (skipped entirely when already set) -- an Ansible-provisioned
    deployment is byte-identical to before this change. Returns the list of
    names actually hydrated (for startup logging -- never the values).
    ``root_key`` defaults to loading ``AUTOBOT_SECRETS_ROOT_KEY`` (production
    behaviour); tests pass an explicit key.
    """
    from services.envelope_secrets_service import EnvelopeSecretsService

    service = EnvelopeSecretsService(root_key=root_key)
    hydrated: list[str] = []
    for name in LLM_PROVIDER_KEY_NAMES:
        if os.environ.get(name):
            continue  # env wins -- irreducible/authoritative today
        secret_id = await _find_system_secret_id(session, name)
        if secret_id is None:
            continue
        try:
            value = await service.read(session, secret_id=secret_id, accessible_vaults={_SYSTEM_VAULT})
        except Exception as exc:  # noqa: BLE001 - defensive, one bad row must not break the rest
            logger.warning("provider-key-vault: hydrate failed name=%s: %s", name, type(exc).__name__)
            continue
        _hydrated_keys[name] = value.decode("utf-8")
        hydrated.append(name)
    return hydrated
