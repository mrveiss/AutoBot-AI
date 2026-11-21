# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Which discovered plugins this backend may import at startup (#17421).

Upgrade rule (owner, 2026-11-21): the first start after ``plugin_enable_state`` exists grandfathers the
discovered plugins as enabled, EXCEPT any whose files are newer than the previous start (dropped in
after the last run); those wait for an admin. Nothing recorded what the previous version loaded, so
this is the approved approximation. The previous start is the ``__last_start__`` row, touched on every
admit; when none was ever recorded (the upgrade boot itself) there is nothing to compare to and every
discovered plugin is grandfathered.

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
from plugin_enable_state import (
    SOURCE_GRANDFATHERED,
    SYSTEM_ACTOR,
    PluginEnableStore,
    audit_decision,
)
from plugin_paths import plugin_search_dirs, trusted_plugin_roots
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


async def eligible_names(
    manifests: List[PluginManifest], locations: Mapping[str, Path], since: datetime | None
) -> List[str]:
    """The manifests old enough to grandfather: no file newer than *since*; all of them when *since* is None."""
    if since is None:
        logger.warning("Plugin gate: no previous start recorded; grandfathering every discovered plugin")
        return [m.name for m in manifests]
    kept = []
    for manifest in manifests:
        root = locations.get(manifest.name)
        if root is not None and await asyncio.to_thread(_newest_mtime, root) <= since.timestamp():
            kept.append(manifest.name)
        else:
            logger.info("Plugin gate: '%s' is newer than the previous start; it waits for an admin", manifest.name)
    return kept


async def grandfather(store: PluginEnableStore, manifests: List[PluginManifest], locations: Mapping[str, Path]) -> None:
    """Record the eligible plugins as enabled, once, with a durable audit entry each."""
    names = await eligible_names(manifests, locations, await store.last_start())

    async def audit_all() -> None:
        for name in names:
            await audit_decision(AuditAction.PLUGIN_GRANDFATHER, name, SYSTEM_ACTOR, reason="running before the gate")

    rows = [(name, True, SOURCE_GRANDFATHERED, SYSTEM_ACTOR) for name in names]
    if await store.write_baseline(rows, audit_all):
        logger.info("Plugin gate: grandfathered %d plugin(s): %s", len(names), sorted(names))


class DatabaseEnableGate:
    """``EnableGate`` backed by ``plugin_enable_state``."""

    def __init__(self, store: PluginEnableStore | None = None) -> None:
        self._store = store or PluginEnableStore()

    async def admit(self, manifests: List[PluginManifest], locations: Mapping[str, Path]) -> List[PluginManifest]:
        if not manifests:
            logger.warning(
                "Plugin gate: discovery found no plugins (directory missing or unmounted?); no baseline written"
            )
        elif not await self._store.has_baseline():
            await grandfather(self._store, manifests, locations)
        enabled = await self._store.enabled_names()
        await self._store.touch_start()
        return [m for m in manifests if m.name in enabled]


def build_plugin_manager() -> PluginManager:
    """The startup host: origin-bound credential resolvers (#18094) and the enable gate (#17421)."""
    return PluginManager(
        plugin_search_dirs(), plugin_credential_resolvers(), trusted_plugin_roots(), DatabaseEnableGate()
    )


async def retry_until_started(manager: PluginManager, delay: float) -> None:
    """Re-run the manager's own ``retry_discovery`` with backoff until a start completes."""
    while True:
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
        fire_and_forget(retry_until_started(manager, RETRY_INITIAL_S), name="plugin-gate-retry")
