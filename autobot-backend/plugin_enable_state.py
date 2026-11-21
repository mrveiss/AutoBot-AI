# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The operator's durable decision to let a plugin run in this process (#17421).

``plugin_enable_state`` is the system of record. Startup imports only the plugins it lists as
enabled (``plugin_enable_gate.DatabaseEnableGate``); the load route refuses the rest; enable and
disable are admin routes that write a durable audit entry first.

Two reserved rows are not plugins: ``__baseline__`` (the one-time grandfathering ran) and
``__last_start__`` (its ``updated_at`` is when a backend last finished admitting plugins).
"""

from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, List

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from autobot_shared.logging_manager import get_logger
from autobot_shared.plugin_sdk import PluginLoader, PluginRegistry
from autobot_shared.plugin_sdk.lifecycle import enable_attributed
from autobot_shared.store_authority import system_of_record
from services.audit.taxonomy import AuditAction
from services.audit_logger import audit_log
from user_management.database import get_async_session_factory
from user_management.models.plugin_enable_state import PluginEnableState

logger = get_logger(__name__)

SYSTEM_OF_RECORD = system_of_record("plugin_enable_state")

#: Row recording that the one-time grandfathering ran. Not a plugin name, so never enabled or listed.
BASELINE_ROW = "__baseline__"
#: Row whose ``updated_at`` is the previous backend start; the reference the grandfather scope compares to.
LAST_START_ROW = "__last_start__"
RESERVED_ROWS = frozenset({BASELINE_ROW, LAST_START_ROW})
SOURCE_GRANDFATHERED = "grandfathered"
SOURCE_ADMIN = "admin"
SOURCE_BUNDLED = "bundled"
SOURCE_SYSTEM = "system"
SYSTEM_ACTOR = "system"

Row = tuple[str, bool, str, str]


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
                    PluginEnableState.enabled.is_(True), PluginEnableState.plugin_name.not_in(RESERVED_ROWS)
                )
            )
            return set(rows.scalars())

    async def is_enabled(self, plugin_name: str) -> bool:
        return plugin_name in await self.enabled_names()

    async def has_baseline(self) -> bool:
        async with self._session() as session:
            return await session.get(PluginEnableState, BASELINE_ROW) is not None

    async def last_start(self) -> datetime | None:
        """When a backend last finished admitting plugins, or None when none ever recorded it."""
        async with self._session() as session:
            row = await session.get(PluginEnableState, LAST_START_ROW)
        if row is None:
            return None
        return row.updated_at if row.updated_at.tzinfo else row.updated_at.replace(tzinfo=timezone.utc)

    async def touch_start(self) -> None:
        """Record now as this backend's start (an explicit ``updated_at``, so an unchanged row still moves)."""
        row = PluginEnableState(
            plugin_name=LAST_START_ROW,
            enabled=False,
            source=SOURCE_SYSTEM,
            decided_by=SYSTEM_ACTOR,
            updated_at=datetime.now(timezone.utc),
        )
        async with self._session() as session:
            await session.merge(row)
            await session.commit()

    async def put(self, rows: List[Row]) -> None:
        """Upsert ``(plugin_name, enabled, source, decided_by)`` rows in one transaction."""
        async with self._session() as session:
            for name, enabled, source, actor in rows:
                await session.merge(
                    PluginEnableState(plugin_name=name, enabled=enabled, source=source, decided_by=actor)
                )
            await session.commit()

    async def known_names(self) -> set[str]:
        """Every plugin with a row, enabled or not (an admin's disable is a row)."""
        async with self._session() as session:
            rows = await session.execute(
                select(PluginEnableState.plugin_name).where(PluginEnableState.plugin_name.not_in(RESERVED_ROWS))
            )
            return set(rows.scalars())

    async def write_baseline(self, rows: List[Row], before_commit: Callable[[], Awaitable[None]]) -> bool:
        """Claim the baseline and write *rows* once; see :meth:`insert_once`."""
        baseline = (BASELINE_ROW, False, SOURCE_GRANDFATHERED, SYSTEM_ACTOR)
        return await self.insert_once([baseline] + rows, before_commit)

    async def insert_once(self, rows: List[Row], before_commit: Callable[[], Awaitable[None]]) -> bool:
        """Insert *rows*, run *before_commit* (the audit), then commit, all in one transaction.

        A concurrent boot inserting the same primary key blocks until the winner commits, then fails with
        ``IntegrityError`` and gets False: the audit runs and the rows are written exactly once. A failing
        *before_commit* rolls everything back. Existing rows are never overwritten.
        """
        async with self._session() as session:
            for name, enabled, source, actor in rows:
                session.add(PluginEnableState(plugin_name=name, enabled=enabled, source=source, decided_by=actor))
            try:
                await session.flush()
            except IntegrityError:
                await session.rollback()
                return False
            await before_commit()
            await session.commit()
            return True


async def audit_decision(action: AuditAction, plugin_name: str, actor: str, **details: Any) -> None:
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


async def require_enabled(plugin_name: str, store: PluginEnableStore | None = None) -> None:
    """403 unless an admin has enabled *plugin_name*; guards the load route."""
    if not await (store or PluginEnableStore()).is_enabled(plugin_name):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, f"Plugin {plugin_name} is not enabled; an admin must enable it first"
        )


async def decide_plugin_enabled(
    plugin_name: str,
    enabled: bool,
    user: dict,
    loader: PluginLoader,
    store: PluginEnableStore | None = None,
) -> bool:
    """Audit, persist and apply an admin's enable or disable of *plugin_name* (#17421).

    Returns whether the plugin is loaded in this process. The status flip applies to this worker only;
    the decision itself is durable and every worker honours it at its next start.
    """
    plugin = PluginRegistry().get_plugin(plugin_name)
    known = plugin is not None or any(m.name == plugin_name for m in loader.discover_plugins())
    if plugin_name in RESERVED_ROWS or not known:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Plugin not found: {plugin_name}")
    actor = user.get("username") or "unknown"
    action = AuditAction.PLUGIN_ENABLE if enabled else AuditAction.PLUGIN_DISABLE
    await audit_decision(action, plugin_name, actor, loaded=plugin is not None)
    await (store or PluginEnableStore()).put([(plugin_name, enabled, SOURCE_ADMIN, actor)])
    if plugin is not None:
        await (enable_attributed(plugin) if enabled else plugin.disable())
    return plugin is not None


def plugin_decision_message(plugin_name: str, enabled: bool, loaded: bool) -> str:
    """What an admin is told: the decision is durable, the live effect is per worker (#17421)."""
    verb = "enabled" if enabled else "disabled"
    if enabled and not loaded:
        return f"Plugin {plugin_name} enabled; load it or restart to activate"
    return f"Plugin {plugin_name} {verb}; takes effect on restart for other workers"
