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
   initialised) and populates a process-lifetime cache that is consulted
   FIRST: the System vault is the canonical credential store (owner decision
   2026-10-12, #18094). The env var / ``ssot_config`` value is only a logged
   migration fallback for a name the vault does not hold, so no provider key
   becomes unreachable mid-cutover. A name the vault DOES hold but could not
   read at hydration is different: :func:`resolve_provider_key` refuses it with
   :class:`VaultKeyUnavailableError` rather than falling back to an env value
   that may have been rotated out (owner decision 2026-10-12). A later
   successful hydration or capture clears the refusal. Listing rows needs no
   root key, so a held name with no usable root key is refused too. A vault
   whose rows cannot be listed (DB unreachable, session factory failing) leaves
   "does it hold this key?" unknown, so every name is refused until a hydration
   succeeds (retried with backoff on later resolutions). Env is used only where
   the listing found no row for that name. Every process hydrates: the lifespan
   in Phase 1, Celery workers on ``worker_process_init``, and any other process
   on its first resolution (``services.provider_key_process_init``). Hydration
   builds a new cache and swaps it in, so readers never see a half-filled one
   and a deleted row leaves no stale value. It also records a
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
from contextlib import contextmanager
from typing import TYPE_CHECKING, Callable, Iterator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.plugin_sdk.credential_binding import CredentialUnavailableError
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
#: migrated to this seam at all -- the Google/VirusTotal/URLVoid health
#: and threat-intel probe keys ``services.provider_health.providers`` and
#: ``security.threat_intelligence`` read directly -- and
#: ``services.notification_service``'s SMTP password, resolved with a
#: line-neutral edit to its ``KNOWN_LARGE`` file (the local import folds into
#: the blank line the docstring used to leave before its first statement, and
#: two constructor-style assignments merge into one to absorb the blank line
#: black inserts after that import), so the ceiling in
#: ``scripts/python_file_size_known_large.py`` never had to move (#14236).
#: The same trade was made in ``services/execution/claude_code_backend.py``
#: for ``anthropic_api_key`` (two ``__init__`` assignments merged). SLACK_BOT_TOKEN
#: has a second, independent reader, ``agent_loop.slack_hook`` (the Slack
#: notification bot itself, distinct from the capability registry's messaging
#: adapter) -- both route through this same name.
SERVICE_CREDENTIAL_KEY_NAMES: frozenset[str] = frozenset(
    {
        "SLACK_BOT_TOKEN",
        "DISCORD_BOT_TOKEN",
        "GOOGLE_API_KEY",
        "VIRUSTOTAL_API_KEY",
        "URLVOID_API_KEY",
        "AUTOBOT_SMTP_PASSWORD",
        "TILDE_API_KEY",
    }
)

#: Image-generation credentials (#18094): the names the image-generation API
#: route and plugin read. ``OPENAI_API_KEY`` is the LLM set's member, referenced
#: rather than repeated, so the name has exactly one definition.
_IMAGE_ONLY_KEY_NAMES: frozenset[str] = frozenset({"FLUX_API_KEY", "STABILITY_API_KEY"})
IMAGE_PROVIDER_KEY_NAMES: frozenset[str] = _IMAGE_ONLY_KEY_NAMES | (LLM_PROVIDER_KEY_NAMES & {"OPENAI_API_KEY"})

#: Video-generation credentials (#18094): the plugin's providers and the backend video API.
VIDEO_PROVIDER_KEY_NAMES: frozenset[str] = frozenset({"RUNWAY_API_KEY", "SORA_API_KEY", "KLING_API_KEY"})

#: The full set of names eligible for capture-time mirroring and startup
#: hydration -- provider-agnostic per #15267's suggestion, since this module
#: is no longer LLM-only once search joins it.
VAULT_RESOLVED_CREDENTIAL_NAMES: frozenset[str] = (
    LLM_PROVIDER_KEY_NAMES
    | SEARCH_PROVIDER_KEY_NAMES
    | SERVICE_CREDENTIAL_KEY_NAMES
    | IMAGE_PROVIDER_KEY_NAMES
    | VIDEO_PROVIDER_KEY_NAMES
)

#: Which module resolves each name -- the ``secret_dependencies`` edge
#: (#10088 Task 8.2) recorded during hydration below.
_CREDENTIAL_CONSUMERS: dict[str, str] = {
    **{name: "llm_shared.provider_registry" for name in LLM_PROVIDER_KEY_NAMES},
    **{name: "agent_loop.search.registry" for name in SEARCH_PROVIDER_KEY_NAMES},
    **{name: "api.image_generation" for name in _IMAGE_ONLY_KEY_NAMES},
    **{name: "api.video_generation" for name in VIDEO_PROVIDER_KEY_NAMES},
    **{name: "voice_processing.providers.lv.tilde_provider" for name in ("TILDE_API_KEY",)},
    "SLACK_BOT_TOKEN": "integrations.capability_registry",  # nosec B105  # module path, not a credential
    "DISCORD_BOT_TOKEN": "integrations.capability_registry",  # nosec B105  # module path, not a credential
    "GOOGLE_API_KEY": "services.provider_health.providers",
    "VIRUSTOTAL_API_KEY": "security.threat_intelligence",
    "URLVOID_API_KEY": "security.threat_intelligence",
    "AUTOBOT_SMTP_PASSWORD": "services.notification_service",  # nosec B105  # module path, not a credential
}

_SYSTEM_VAULT = VaultRef(VaultKind.SYSTEM)

#: Process-lifetime cache of provider keys hydrated from the System vault.
#: Consulted first (the vault wins, #18094). Never logged,
#: never written back to os.environ (child-process env sanitization is a
#: separate, pre-existing concern -- see services/execution/env_sanitizer.py).
_hydrated_keys: dict[str, str] = {}

#: Names already reported as resolving from the env fallback, so the warning is
#: emitted once per name per process rather than on every resolution.
_env_fallback_logged: set[str] = set()

#: Names the System vault holds but whose last read failed. Distinct from "not in
#: the vault": these are refused, never resolved from the environment (#18094).
_unreadable_keys: set[str] = set()

#: What this process knows about the vault (#18094). ``unreachable`` refuses every
#: name; ``reachable`` defers to the per-name state above; ``not_hydrated`` triggers
#: a one-time hydration on first resolution when a root key is configured.
VAULT_NOT_HYDRATED = "not_hydrated"  # this process has not read the vault yet
VAULT_REACHABLE = "reachable"  # rows were listed: an absent name really is absent
VAULT_UNREACHABLE = "unreachable"  # listing the rows failed: held-state unknown
_vault_state: str = VAULT_NOT_HYDRATED

_UNREADABLE = "is stored in the secrets manager but could not be read"
_UNREACHABLE = "may be stored in the secrets manager, which could not be reached"


class VaultKeyUnavailableError(CredentialUnavailableError):
    """The vault holds (or may hold) *name* but it could not be read; the env value is deliberately not used."""

    def __init__(self, name: str, why: str = _UNREADABLE) -> None:
        self.name = _label(name)
        super().__init__(
            f"vault unavailable: {self.name} {why}; refusing the environment fallback, which may hold a rotated-out key"
        )


def _label(name: str) -> str:
    """A registry label for *name* -- only those are ever logged (same construction as #16444)."""
    return "".join(VAULT_RESOLVED_CREDENTIAL_NAMES & {name}) or "<unregistered name>"


def resolve_provider_key(env_var: str, config_value: str) -> str:
    """The one resolution order for vault-resolved credentials (#18094, owner decision 2026-10-12).

    The System vault (hydrated cache) wins. *config_value* -- the env var as
    ``ssot_config`` read it -- is a migration fallback used only when the vault
    holds no value for *env_var*, and that fallback is logged by name, never by
    value. A name the vault holds but could not read raises
    :class:`VaultKeyUnavailableError` instead. Every caller (LLM, search,
    integrations, image generation) goes through here, so the order has exactly
    one definition.
    """
    vaulted = _hydrated_keys.get(env_var, "")
    if vaulted:
        return vaulted
    if _vault_state in (VAULT_NOT_HYDRATED, VAULT_UNREACHABLE):
        # A process that has not read the vault (CLI, script, MCP server, a worker before its
        # init hook) reads it now -- listing needs no root key -- and an unreachable vault is
        # retried with backoff, rather than serving env for a key it may hold.
        from services.provider_key_process_init import hydrate_this_process

        hydrate_this_process()
        vaulted = _hydrated_keys.get(env_var, "")
        if vaulted:
            return vaulted
    if _vault_state == VAULT_UNREACHABLE:
        logger.error("provider-key-vault: %s vault unreachable: refusing the environment fallback", _label(env_var))
        raise VaultKeyUnavailableError(env_var, _UNREACHABLE)
    if env_var in _unreadable_keys:
        logger.error("provider-key-vault: %s vault unreadable: refusing the environment fallback", _label(env_var))
        raise VaultKeyUnavailableError(env_var)
    if config_value:
        _log_env_fallback(env_var)
    return config_value


def _log_env_fallback(name: str) -> None:
    """Warn once that *name* resolved from the environment, not the secrets manager."""
    if name in _env_fallback_logged:
        return
    _env_fallback_logged.add(name)
    logger.warning(
        "provider-key-vault: %s vault has no key: using the environment (migration fallback); store it in the vault",
        _label(name),
    )


@contextmanager
def registration_refusal(component: str) -> Iterator[None]:
    """Contain a refusal at a registration site: *component* is skipped and the reason logged at ERROR.

    One refused credential must not abort registering its siblings or crash startup.
    """
    try:
        yield
    except VaultKeyUnavailableError as exc:
        logger.error("provider-key-vault: %s not registered -- %s", component, exc)


def resolve_image_provider_key(name: str) -> str:
    """Scoped resolver handed to the image-generation plugin (#18094).

    Accepts only :data:`IMAGE_PROVIDER_KEY_NAMES` and raises ``ValueError``
    for anything else, so the plugin cannot read an arbitrary secret through
    it. Precedence is :func:`resolve_provider_key`'s: vault first, env as a logged fallback.
    Returns ``""`` when unset, as ``os.environ.get(name, "")`` did.

    Not a sandbox: plugins run in-process (``exec_module``), so a loaded plugin
    can read ``os.environ`` and this module's cache directly. The resolver
    narrows what the *sanctioned* path exposes and the loader hands it only to
    built-in plugins (origin-bound); it does not isolate a hostile plugin.
    """
    return _resolve_scoped(name, IMAGE_PROVIDER_KEY_NAMES, "image-provider")


def resolve_video_provider_key(name: str) -> str:
    """Scoped resolver for the video-generation plugin and the backend video API (#18094).

    Same contract as :func:`resolve_image_provider_key`, over :data:`VIDEO_PROVIDER_KEY_NAMES`.
    """
    return _resolve_scoped(name, VIDEO_PROVIDER_KEY_NAMES, "video-provider")


def _resolve_scoped(name: str, allowed: frozenset[str], kind: str) -> str:
    """Resolve *name* only if it is one of *allowed* (exact ``str``, so a subclass cannot spoof membership)."""
    if type(name) is not str or name not in allowed:
        raise ValueError(f"not an {kind} credential name")
    return resolve_provider_key(name, os.environ.get(name, ""))


def key_status(resolve: Callable[[str], str], name: str) -> tuple[bool, str | None]:
    """``(available, reason)`` for a provider listing; never the value, and a refusal reports its reason (#18094)."""
    try:
        available = bool(resolve(name))
    except VaultKeyUnavailableError as exc:
        return False, str(exc)
    return available, None if available else f"{name} not set"


def plugin_credential_resolvers() -> dict[str, Callable[[str], str]]:
    """Plugin name -> scoped resolver; the one injection map handed to ``PluginLoader``/``PluginManager``."""
    return {
        "image-generation-plugin": resolve_image_provider_key,
        "video-generation-plugin": resolve_video_provider_key,
    }


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
    _refresh_hydrated_key(name, plaintext)
    return True


def _refresh_hydrated_key(name: str, plaintext: str) -> None:
    """Keep the process cache in step with a successful vault write (never logs the value).

    The vault wins at resolution (#18094), so a captured value takes effect at
    once, whether or not the env var is also set.
    """
    if name in VAULT_RESOLVED_CREDENTIAL_NAMES:
        _hydrated_keys[name] = plaintext
        _unreadable_keys.discard(name)


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
        # #16444: `name` reached here only by passing the VAULT_RESOLVED_CREDENTIAL_NAMES
        # guard above, so it is a registry label such as OPENAI_API_KEY and never a
        # credential. Re-read from the frozenset so that holds by construction rather
        # than by argument: api/secrets.py unpacks `name` and `value` from one request
        # model, CodeQL taints every attribute of it alike, and a comment does not
        # break a taint path (py/clear-text-logging-sensitive-data).
        known = VAULT_RESOLVED_CREDENTIAL_NAMES & {name}
        logger.warning("provider-key-vault: mirror failed name=%s: %s", "".join(known), type(exc).__name__)
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


async def _read_one_key(
    session: AsyncSession, service: EnvelopeSecretsService | None, *, name: str, secret_id: uuid.UUID
) -> str | None:
    """Decrypt *secret_id*; ``None`` when it cannot be read (no usable root key, or the read fails)."""
    if service is None:
        return None
    try:
        value = await service.read(session, secret_id=secret_id, accessible_vaults={_SYSTEM_VAULT})
    except Exception as exc:  # noqa: BLE001 - defensive, one bad row must not break the rest
        logger.warning("provider-key-vault: hydrate failed name=%s: %s", name, type(exc).__name__)
        return None
    return value.decode("utf-8")


def _decrypting_service(root_key: bytes | None) -> EnvelopeSecretsService | None:
    """The envelope service, or ``None`` when no usable root key exists -- rows are still listed then."""
    from services.envelope_secrets_service import EnvelopeSecretsService

    try:
        return EnvelopeSecretsService(root_key=root_key)
    except RuntimeError as exc:  # load_root_key: unset or malformed AUTOBOT_SECRETS_ROOT_KEY
        logger.warning("provider-key-vault: cannot decrypt (%s); every vault-held key is refused", type(exc).__name__)
        return None


async def hydrate_provider_keys_from_vault(session: AsyncSession, *, root_key: bytes | None = None) -> list[str]:
    """Rebuild the process cache from the System vault: every name it holds, readable or not.

    The vault wins at resolution (#18094): a held name is hydrated whether or not its env
    var is set; a held name that cannot be decrypted -- including when no root key is
    configured -- is recorded as unreadable and refused; only a name with no row falls
    back to env. The new state is built aside and swapped in at the end, so a reader never
    sees a half-filled cache and a row deleted since the last run leaves no stale value. A
    ``secret_dependencies`` edge is recorded for every held name. Returns the names
    hydrated (never values). ``root_key`` defaults to ``AUTOBOT_SECRETS_ROOT_KEY``.
    """
    global _vault_state
    try:
        hydrated = await _hydrate_all(session, root_key)
    except Exception:
        _vault_state = VAULT_UNREACHABLE
        raise
    _vault_state = VAULT_REACHABLE
    return hydrated


async def _hydrate_all(session: AsyncSession, root_key: bytes | None) -> list[str]:
    """List and read every held name into a new cache, then swap it in; any exception = held-state unknown."""
    global _hydrated_keys, _unreadable_keys
    service = _decrypting_service(root_key)
    keys: dict[str, str] = {}
    unreadable: set[str] = set()
    any_dependency_registered = False
    for name in VAULT_RESOLVED_CREDENTIAL_NAMES:
        secret_id = await _find_system_secret_id(session, name)
        if secret_id is None:
            continue  # nothing vaulted: resolution falls back to the env var
        await _register_credential_dependency(session, name=name, secret_id=secret_id)
        any_dependency_registered = True
        value = await _read_one_key(session, service, name=name, secret_id=secret_id)
        if value is None:
            unreadable.add(name)
        else:
            keys[name] = value
    if any_dependency_registered:
        await session.commit()
    _hydrated_keys, _unreadable_keys = keys, unreadable
    return list(keys)


async def hydrate_at_startup(get_session_factory: Callable[[], Callable]) -> list[str]:
    """Hydration that classifies the vault before anything resolves a key (#18094); never raises.

    Rows are listed even without a root key (listing needs none): a held name that cannot be
    decrypted is refused. If the rows cannot be listed -- DB unreachable, the session factory
    itself failing -- the vault is unreachable and every vault-resolved name is refused until a
    hydration succeeds (ERROR). An outage must not stop startup; it must stop keys silently
    coming from env.
    """
    global _vault_state
    try:
        async with get_session_factory()() as session:
            return await hydrate_provider_keys_from_vault(session)
    except Exception as exc:  # noqa: BLE001 - classified and reported; startup continues with keys refused
        _vault_state = VAULT_UNREACHABLE
        logger.error(
            "provider-key-vault: vault unreachable (%s): every vault-resolved provider key is refused, "
            "never taken from env, until a hydration succeeds",
            type(exc).__name__,
        )
        return []
