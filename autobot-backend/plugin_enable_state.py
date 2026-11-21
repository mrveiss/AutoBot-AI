# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The operator's durable decision to let a plugin run in this process (#17421).

``plugin_enable_state`` is the system of record. Startup imports only the plugins it lists as
enabled (:class:`DatabaseEnableGate`); the load route refuses the rest; enable and disable are
admin routes that write a durable audit entry first.

Upgrade: the first start after this table exists records every plugin discovered at that moment as
enabled ("grandfathered", one durable audit entry each), so nothing a user relies on stops. A plugin
discovered afterwards stays off until an admin enables it.
"""

from typing import Any, Callable, List

from fastapi import HTTPException, status
from sqlalchemy import select

from autobot_shared.logging_manager import get_logger
from autobot_shared.plugin_sdk import PluginLoader, PluginManager, PluginManifest, PluginRegistry
from autobot_shared.store_authority import system_of_record
from plugin_paths import plugin_search_dirs, trusted_plugin_roots
from services.audit.taxonomy import AuditAction
from services.audit_logger import audit_log
from services.provider_key_vault import plugin_credential_resolvers
from user_management.database import get_async_session_factory
from user_management.models.plugin_enable_state import PluginEnableState

logger = get_logger(__name__)

SYSTEM_OF_RECORD = system_of_record("plugin_enable_state")

#: Row recording that the one-time grandfathering ran. Not a plugin name, so never enabled or listed.
BASELINE_ROW = "__baseline__"
SOURCE_GRANDFATHERED = "grandfathered"
SOURCE_ADMIN = "admin"
SYSTEM_ACTOR = "system"


class PluginEnableStore:
    """Reads and writes ``plugin_enable_state``; *session_factory* is injectable for tests."""

    def __init__(self, session_factory: Callable[[], Any] | None = None) -> None:
        self._session_factory = session_factory

    def _session(self) -> Any:
        return (self._session_factory or get_async_session_factory())()

    async def enabled_names(self) -> set[str]:
        async with self._session() as session:
            rows = await session.execute(
                select(PluginEnableState.plugin_name).where(
                    PluginEnableState.enabled.is_(True), PluginEnableState.plugin_name != BASELINE_ROW
                )
            )
            return set(rows.scalars())

    async def is_enabled(self, plugin_name: str) -> bool:
        return plugin_name in await self.enabled_names()

    async def has_baseline(self) -> bool:
        async with self._session() as session:
            return await session.get(PluginEnableState, BASELINE_ROW) is not None

    async def put(self, rows: List[tuple[str, bool, str, str]]) -> None:
        """Upsert ``(plugin_name, enabled, source, decided_by)`` rows in one transaction."""
        async with self._session() as session:
            for name, enabled, source, actor in rows:
                await session.merge(
                    PluginEnableState(plugin_name=name, enabled=enabled, source=source, decided_by=actor)
                )
            await session.commit()


async def _audit(action: AuditAction, plugin_name: str, actor: str, **details: Any) -> None:
    """Write the durable audit entry; the decision is not made without one."""
    written = await audit_log(
        action,
        durable=True,
        user_id=actor,
        resource=f"plugin:{plugin_name}",
        details={"plugin": plugin_name, **details},
    )
    if not written:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "audit trail unavailable; plugin state not changed")


async def grandfather(store: PluginEnableStore, names: List[str]) -> None:
    """Record *names* as enabled, each with a durable audit entry, then mark the baseline done."""
    for name in names:
        await _audit(AuditAction.PLUGIN_GRANDFATHER, name, SYSTEM_ACTOR, reason="running before the enable gate")
    rows = [(name, True, SOURCE_GRANDFATHERED, SYSTEM_ACTOR) for name in names]
    await store.put(rows + [(BASELINE_ROW, False, SOURCE_GRANDFATHERED, SYSTEM_ACTOR)])
    logger.info("Plugin enable gate: grandfathered %d running plugin(s): %s", len(names), sorted(names))


class DatabaseEnableGate:
    """``autobot_shared.plugin_sdk.enable_gate.EnableGate`` backed by ``plugin_enable_state``."""

    def __init__(self, store: PluginEnableStore | None = None) -> None:
        self._store = store or PluginEnableStore()

    async def admit(self, manifests: List[PluginManifest]) -> List[PluginManifest]:
        if not await self._store.has_baseline():
            await grandfather(self._store, [m.name for m in manifests])
        enabled = await self._store.enabled_names()
        return [m for m in manifests if m.name in enabled]


async def require_enabled(plugin_name: str, store: PluginEnableStore | None = None) -> None:
    """403 unless an admin has enabled *plugin_name*; guards the load route."""
    if not await (store or PluginEnableStore()).is_enabled(plugin_name):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, f"Plugin {plugin_name} is not enabled; an admin must enable it first"
        )


async def apply_decision(
    plugin_name: str,
    enabled: bool,
    user: dict,
    loader: PluginLoader,
    store: PluginEnableStore | None = None,
) -> None:
    """Audit, persist and apply an admin's enable or disable of *plugin_name* (#17421)."""
    plugin = PluginRegistry().get_plugin(plugin_name)
    known = plugin is not None or any(m.name == plugin_name for m in loader.discover_plugins())
    if plugin_name == BASELINE_ROW or not known:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Plugin not found: {plugin_name}")
    actor = user.get("username") or "unknown"
    action = AuditAction.PLUGIN_ENABLE if enabled else AuditAction.PLUGIN_DISABLE
    await _audit(action, plugin_name, actor, loaded=plugin is not None)
    await (store or PluginEnableStore()).put([(plugin_name, enabled, SOURCE_ADMIN, actor)])
    if plugin is not None:
        await (plugin.enable() if enabled else plugin.disable())


def build_plugin_manager() -> PluginManager:
    """The startup host: origin-bound credential resolvers (#18094) and the enable gate (#17421)."""
    return PluginManager(
        plugin_search_dirs(), plugin_credential_resolvers(), trusted_plugin_roots(), DatabaseEnableGate()
    )
