# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Provider-key capture + vault-backed runtime resolution (#10088 Task 7).

First-time-setup flow: an admin captures a provider key (OpenAI, Anthropic,
HuggingFace, ...) through the API-key setup wizard
(``autobot-frontend/src/components/settings/ApiKeySetupWizard.vue``), which
posts to the legacy ``POST /api/secrets/`` endpoint (``api/secrets.py``) --
today's *only* write path for these values, since ``SecretUpdateRequest`` has
no ``value`` field (rotation is delete+recreate). This module adds two halves
that endpoint never had:

1. **Capture** (:func:`mirror_provider_key_best_effort`) -- mirrors a
   provider-key value into the System vault at the moment it's created,
   idempotently (create once, rotate on a later re-capture of the same
   name). Scoped strictly to :data:`VAULT_RESOLVED_CREDENTIAL_NAMES` -- the
   generic ``secrets.json`` -> envelope migration is Task 3's importer
   (`#13052` notes nothing invokes it yet); this hook does not duplicate
   that work, it only guarantees these specific credentials are never
   vault-blind.

2. **Runtime resolution** (:func:`hydrate_provider_keys_from_vault` +
   :func:`resolve_provider_key`) -- the actual runtime readers,
   ``llm_shared.provider_registry._populate_default_providers`` (LLM
   providers, :data:`LLM_PROVIDER_KEY_NAMES`) and
   ``agent_loop.search.registry._populate_default_providers`` (web-search
   providers, :data:`SEARCH_PROVIDER_KEY_NAMES`, #15267), used to read only
   ``ssot_config`` (env vars) and never consulted the legacy secrets store
   *or* the vault -- a value captured via the wizard was, until this change,
   write-only (unreachable at runtime; the same class of defect Task 5 hit
   for connector credentials). :func:`hydrate_provider_keys_from_vault` runs
   once at startup (``initialization/lifespan.py``, Phase 1, after the DB is
   initialised) and populates a process-lifetime cache consulted *only* when
   the env var itself is unset, so an Ansible-provisioned deployment's env
   vars remain authoritative and unaffected (dual-read, env-first -- no
   provider key becomes unreachable mid-cutover). It also records a
   ``secret_dependencies`` edge (#10088 Task 8.2) for every name whose
   System-vault secret exists, regardless of whether the value currently
   resolves from the vault or from the env, so rotation-impact analysis
   sees the consumer.

Never logs a secret value.
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.secrets_vault import VaultKind, VaultRef
from models.secret import Secret

if TYPE_CHECKING:  # pragma: no cover -- annotation-only; zero runtime import cost
    from services.envelope_secrets_service import EnvelopeSecretsService

logger = logging.getLogger(__name__)

#: LLM provider API-key env-var names eligible for System-vault capture +
#: resolution. Each name has a real runtime reader in
#: ``llm_shared.provider_registry._populate_default_providers`` -- the actual
#: LLM-call routing path (not the adapter-listing-only AdapterRegistry).
#: HF_TOKEN / HUGGINGFACE_API_TOKEN are the HuggingFace-hosted-model tokens
#: read by that same registry (#15268) -- distinct from the SLM setup
#: wizard's unrelated ``tts_hf_token`` (TTS-worker model download, migrated
#: by Task 6a), which this module has never covered.
LLM_PROVIDER_KEY_NAMES: frozenset[str] = frozenset(
    {
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GROQ_API_KEY",
        "MISTRAL_API_KEY",
        "OPENROUTER_API_KEY",
        "NOUS_API_KEY",
        "CUSTOM_OPENAI_API_KEY",
        "HF_TOKEN",
        "HUGGINGFACE_API_TOKEN",
    }
)

#: Web-search provider credential names, the same treatment one module over
#: (#15267): ``agent_loop.search.registry._populate_default_providers`` is
#: the real runtime reader.
SEARCH_PROVIDER_KEY_NAMES: frozenset[str] = frozenset(
    {
        "SEARXNG_INSTANCE_URL",
        "SEARXNG_BASIC_AUTH_USER",
        "SEARXNG_BASIC_AUTH_PASS",
        "SEARXNG_TOKEN",
        "BRAVE_SEARCH_API_KEY",
    }
)

#: Third-party/service credential names outside the LLM and web-search
#: domains (#15276, tail of the #15267/#15268 sweep): the messaging bot
#: tokens ``integrations.capability_registry`` gates its Slack/Discord
#: adapters on -- the third ``CredentialGatedRegistry`` sibling named in
#: ``autobot_shared/credential_gated_registry.py``'s own docstring, never
#: migrated to this seam at all -- and the Google/VirusTotal/URLVoid health
#: and threat-intel probe keys ``services.provider_health.providers`` and
#: ``security.threat_intelligence`` read directly. SLACK_BOT_TOKEN has a
#: second, independent reader, ``agent_loop.slack_hook`` (the Slack
#: notification bot itself, distinct from the capability registry's
#: messaging adapter) -- both route through this same name.
#:
#: ``services.notification_service``'s SMTP password is deliberately not
#: here: routing it through this seam needs a new module-level import in a
#: ``KNOWN_LARGE`` file at its frozen line-count ceiling
#: (``scripts/python_file_size_known_large.py``), and that ceiling may not
#: grow to make room for it (#14236). Left as a TRACKED_GAP entry in
#: ``repo_tests/credential_vault_resolution_allowlist.py`` for a change that
#: can also address the file-size constraint, rather than bending the ratchet
#: here.
SERVICE_CREDENTIAL_KEY_NAMES: frozenset[str] = frozenset(
    {
        "SLACK_BOT_TOKEN",
        "DISCORD_BOT_TOKEN",
        "GOOGLE_API_KEY",
        "VIRUSTOTAL_API_KEY",
        "URLVOID_API_KEY",
    }
)

#: The full set of names eligible for capture-time mirroring and startup
#: hydration -- provider-agnostic per #15267's suggestion, since this module
#: is no longer LLM-only once search joins it.
VAULT_RESOLVED_CREDENTIAL_NAMES: frozenset[str] = (
    LLM_PROVIDER_KEY_NAMES | SEARCH_PROVIDER_KEY_NAMES | SERVICE_CREDENTIAL_KEY_NAMES
)

#: Which module resolves each name -- the ``secret_dependencies`` edge
#: (#10088 Task 8.2) recorded during hydration below.
_CREDENTIAL_CONSUMERS: dict[str, str] = {
    **{name: "llm_shared.provider_registry" for name in LLM_PROVIDER_KEY_NAMES},
    **{name: "agent_loop.search.registry" for name in SEARCH_PROVIDER_KEY_NAMES},
    "SLACK_BOT_TOKEN": "integrations.capability_registry",  # nosec B105  # module path, not a credential
    "DISCORD_BOT_TOKEN": "integrations.capability_registry",  # nosec B105  # module path, not a credential
    "GOOGLE_API_KEY": "services.provider_health.providers",
    "VIRUSTOTAL_API_KEY": "security.threat_intelligence",
    "URLVOID_API_KEY": "security.threat_intelligence",
}

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
    """Mirror a provider-key value into the System vault (idempotent).

    Creates a new System-vault secret the first time *name* is captured;
    rotates the value on a later re-capture (an admin legitimately changing a
    key). No-op for any name outside :data:`VAULT_RESOLVED_CREDENTIAL_NAMES`
    -- this hook is intentionally scoped to known provider keys, not a
    generic secrets mirror. Raises on a genuine vault error; callers use
    :func:`mirror_provider_key_best_effort` for the best-effort wrapper.
    ``root_key`` defaults to loading ``AUTOBOT_SECRETS_ROOT_KEY`` (production
    behaviour); tests pass an explicit key.
    """
    if name not in VAULT_RESOLVED_CREDENTIAL_NAMES:
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
    if name not in VAULT_RESOLVED_CREDENTIAL_NAMES:
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


async def _register_credential_dependency(session: AsyncSession, *, name: str, secret_id: uuid.UUID) -> None:
    """Record that :data:`_CREDENTIAL_CONSUMERS`\\ [*name*] depends on *secret_id* (#10088 Task 8.2).

    Best-effort and idempotent (``SecretDependencyService.register`` is an
    ``ON CONFLICT DO NOTHING`` upsert): a rotation-impact-list write must
    never fail startup hydration.
    """
    consumer = _CREDENTIAL_CONSUMERS.get(name)
    if consumer is None:
        return
    from services.secret_dependency_service import SecretDependencyService

    try:
        await SecretDependencyService().register(
            session, secret_id=secret_id, dependent_kind="service", dependent_id=consumer
        )
    except Exception as exc:  # noqa: BLE001 - metadata only; never blocks hydration
        logger.warning("provider-key-vault: dependency registration failed name=%s: %s", name, type(exc).__name__)


async def _hydrate_one_key(
    session: AsyncSession, service: EnvelopeSecretsService, *, name: str, secret_id: uuid.UUID
) -> bool:
    """Decrypt *secret_id* into ``_hydrated_keys[name]``. Returns whether it hydrated."""
    try:
        value = await service.read(session, secret_id=secret_id, accessible_vaults={_SYSTEM_VAULT})
    except Exception as exc:  # noqa: BLE001 - defensive, one bad row must not break the rest
        logger.warning("provider-key-vault: hydrate failed name=%s: %s", name, type(exc).__name__)
        return False
    _hydrated_keys[name] = value.decode("utf-8")
    return True


async def hydrate_provider_keys_from_vault(session: AsyncSession, *, root_key: bytes | None = None) -> list[str]:
    """Populate the process cache from the System vault for any unset env var.

    Called once at FastAPI startup, after the DB is initialised. Env vars
    always win (the cache is skipped entirely when already set) -- an
    Ansible-provisioned deployment is byte-identical to before this change.
    A ``secret_dependencies`` edge is recorded for every name whose vault
    secret exists, independent of the env-var check, so rotation-impact
    analysis sees a consumer even while its env var currently wins. Returns
    the list of names actually hydrated into the cache (for startup logging
    -- never the values). ``root_key`` defaults to loading
    ``AUTOBOT_SECRETS_ROOT_KEY`` (production behaviour); tests pass an
    explicit key.
    """
    from services.envelope_secrets_service import EnvelopeSecretsService

    service = EnvelopeSecretsService(root_key=root_key)
    hydrated: list[str] = []
    any_dependency_registered = False
    for name in VAULT_RESOLVED_CREDENTIAL_NAMES:
        secret_id = await _find_system_secret_id(session, name)
        if secret_id is not None:
            await _register_credential_dependency(session, name=name, secret_id=secret_id)
            any_dependency_registered = True
        if os.environ.get(name) or secret_id is None:
            continue  # env wins -- irreducible/authoritative today
        if await _hydrate_one_key(session, service, name=name, secret_id=secret_id):
            hydrated.append(name)
    if any_dependency_registered:
        await session.commit()
    return hydrated
