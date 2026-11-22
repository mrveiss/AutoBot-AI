# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Which discovered plugins this backend may import at startup (#17421).

Bundled rule (owner, 2026-11-21): a plugin under the core-plugins root is enabled by default, recorded
with source ``bundled`` and audited, on every admit; only a missing row is filled in, so an admin's
disable stays. A fresh install works without an admin.

Upgrade rule (owner, 2026-11-21) for everything else: the first start after ``plugin_enable_state``
exists grandfathers the discovered third-party plugins as enabled, EXCEPT any whose files are newer than
the previous start (dropped in after the last run); those wait for an admin. Nothing recorded what the
previous version loaded, so this is the approved approximation. The previous start comes from
``plugin_previous_start`` (recorded start, updater marker, backend log); when none exists nothing is
grandfathered and the reason is audited. File times can be preserved or forged, so this is a heuristic,
not a trust boundary.

Failure rule: if the database or the audit trail cannot answer, no plugin loads, and the start is retried
in the background with backoff until it does -- no restart needed.
"""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import List, Mapping

from autobot_shared.async_compat import fire_and_forget
from autobot_shared.env_utils import env_int_clamped
from autobot_shared.logging_manager import get_logger
from autobot_shared.plugin_sdk import PluginManager, PluginManifest
from autobot_shared.plugin_sdk.credential_binding import is_under_trusted_root
from plugin_enable_state import (
    SOURCE_BUNDLED,
    SOURCE_GRANDFATHERED,
    SYSTEM_ACTOR,
    PluginEnableStore,
    audit_decision,
    clear_disabled_in_this_process,
    disabled_in_this_process,
)
from plugin_paths import plugin_search_dirs, trusted_plugin_roots
from plugin_previous_start import previous_start
from services.audit.taxonomy import AuditAction
from services.provider_key_vault import plugin_credential_resolvers

logger = get_logger(__name__)

#: First and longest wait between background start attempts after a gate failure (seconds).
RETRY_INITIAL_S = env_int_clamped("AUTOBOT_PLUGIN_GATE_RETRY_INITIAL_S", 5, min_v=1, max_v=3600)
RETRY_MAX_S = env_int_clamped("AUTOBOT_PLUGIN_GATE_RETRY_MAX_S", 300, min_v=1, max_v=86400)


def _newest_mtime(root: Path) -> float:
    """The latest modification time of any source file under *root* (bytecode caches ignored)."""
    newest = 0.0
    for path in root.rglob("*"):
        if "__pycache__" in path.parts:
            continue
        try:
            newest = max(newest, path.stat().st_mtime)
        except OSError:
            continue
    return newest


async def eligible_names(manifests: List[PluginManifest], locations: Mapping[str, Path], since: datetime) -> List[str]:
    """The manifests with no file newer than *since*; the rest wait for an admin."""
    kept = []
    for manifest in manifests:
        root = locations.get(manifest.name)
        if root is not None and await asyncio.to_thread(_newest_mtime, root) <= since.timestamp():
            kept.append(manifest.name)
        else:
            logger.info("Plugin gate: '%s' is newer than the previous start; it waits for an admin", manifest.name)
    return kept


async def grandfather(store: PluginEnableStore, manifests: List[PluginManifest], locations: Mapping[str, Path]) -> None:
    """Record the eligible plugins as enabled, once, with a durable audit entry each.

    A boot that fails after the audit rolls back the baseline, so its retry audits again; the duplicate
    entries are accepted (each is true: that attempt decided that).
    """
    manifests = [m for m in manifests if m.name not in await store.known_names()]  # an existing row is a decision
    since, source = await previous_start(store)
    if since is None:
        names: List[str] = []
        reason = "no previous start is known (no recorded start, updater marker or backend log): nothing grandfathered"
        logger.warning("Plugin gate: %s", reason)
    else:
        names = await eligible_names(manifests, locations, since)
        reason = f"running before the gate (previous start from the {source})"

    async def audit_all() -> None:
        if not names:
            await audit_decision(AuditAction.PLUGIN_GRANDFATHER, "*", SYSTEM_ACTOR, reason=reason, granted=0)
        for name in names:
            await audit_decision(AuditAction.PLUGIN_GRANDFATHER, name, SYSTEM_ACTOR, reason=reason)

    rows = [(name, True, SOURCE_GRANDFATHERED, SYSTEM_ACTOR) for name in names]
    if await store.write_baseline(rows, audit_all):
        logger.info("Plugin gate: grandfathered %d plugin(s): %s", len(names), sorted(names))
    else:
        logger.warning(
            "Plugin gate: baseline not written (a concurrent boot or admin decision won); retried next start"
        )


async def record_bundled(store: PluginEnableStore, names: List[str]) -> None:
    """Enable the bundled plugins that have no row yet, audited, one row at a time.

    A row an admin wrote (a disable) is kept. Each plugin is its own transaction, so a row a concurrent
    boot already wrote costs only that plugin, never the others.
    """
    for name in sorted(set(names) - await store.known_names()):

        async def audit_one(plugin: str = name) -> None:
            await audit_decision(AuditAction.PLUGIN_ENABLE, plugin, SYSTEM_ACTOR, reason="bundled core plugin")

        if await store.insert_once([(name, True, SOURCE_BUNDLED, SYSTEM_ACTOR)], audit_one):
            logger.info("Plugin gate: enabled bundled plugin %s", name)


class DatabaseEnableGate:
    """``EnableGate`` backed by ``plugin_enable_state``.

    A plugin whose resolved directory is under a core-plugins root (``plugin_paths.trusted_plugin_roots``)
    is bundled: enabled by default on every admit, unless an admin disabled it. Everything else needs the
    grandfather rule or an admin.
    """

    def __init__(self, store: PluginEnableStore | None = None, core_roots: List[Path] | None = None) -> None:
        self._store = store or PluginEnableStore()
        self._core_roots = core_roots

    async def admit(self, manifests: List[PluginManifest], locations: Mapping[str, Path]) -> List[PluginManifest]:
        clear_disabled_in_this_process()  # the table read below is the truth at boot start
        roots = self._core_roots if self._core_roots is not None else trusted_plugin_roots()
        bundled = [m for m in manifests if m.name in locations and is_under_trusted_root(locations[m.name], roots)]
        if not manifests:
            logger.warning(
                "Plugin gate: discovery found no plugins (directory missing or unmounted?); no baseline written"
            )
        else:
            if not await self._store.has_baseline():
                third_party = [m for m in manifests if m not in bundled]
                await grandfather(self._store, third_party, locations)
            await record_bundled(self._store, [m.name for m in bundled])
        enabled = await self._store.enabled_names()
        await self._store.touch_start()
        return [m for m in manifests if m.name in enabled and not disabled_in_this_process(m.name)]

    async def still_admitted(self, plugin_name: str) -> bool:
        """Re-check one admitted plugin just before it is imported or enabled: an admin may have disabled it since."""
        enabled = await self._store.is_enabled(plugin_name)
        return enabled and not disabled_in_this_process(plugin_name)


def build_plugin_manager() -> PluginManager:
    """The startup host: origin-bound credential resolvers (#18094) and the enable gate (#17421)."""
    return PluginManager(
        plugin_search_dirs(), plugin_credential_resolvers(), trusted_plugin_roots(), DatabaseEnableGate()
    )


async def retry_until_started(manager: PluginManager, delay: float) -> None:
    """Re-run the manager's own ``retry_discovery`` with backoff until a start completes or it is shut down."""
    delay = min(delay, RETRY_MAX_S)
    while manager.started:
        await asyncio.sleep(delay)
        try:
            if (await manager.retry_discovery())["completed"]:
                logger.info("Plugin gate: start completed on retry")
                return
        except Exception as exc:  # noqa: BLE001 -- the gate may still be down; keep trying
            logger.warning("Plugin gate: retry failed (%s: %s)", type(exc).__name__, exc)
        delay = min(delay * 2, RETRY_MAX_S)


async def start_plugin_manager(manager: PluginManager) -> None:
    """Start *manager*; if the gate cannot answer, load nothing and retry in the background (fail closed)."""
    try:
        await manager.startup()
    except Exception as exc:  # noqa: BLE001 -- fail closed, then retry
        logger.error("Plugin gate failed at boot, no plugin loaded; retrying in the background: %s", exc, exc_info=True)
        manager.start_retry_task = fire_and_forget(
            retry_until_started(manager, RETRY_INITIAL_S), name="plugin-gate-retry"
        )
