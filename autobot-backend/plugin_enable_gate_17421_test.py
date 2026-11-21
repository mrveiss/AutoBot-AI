# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A plugin's code runs only after an operator enabled it, and upgrades keep what ran (#17421, #19302).

Real loader, real ``PluginManager``, real ``plugin_enable_state`` table (SQLite). The only fake is the
audit sink, which models the contract of ``audit_log``: awaited, returns whether the row was committed.
"""

import asyncio
import json
import os
import sys
import textwrap
import time

import pytest
import pytest_asyncio
from fastapi import HTTPException
from fastapi.routing import APIRoute
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import plugin_enable_gate as peg
import plugin_enable_state as pes
import plugin_manager as plugin_routes
from auth_middleware import check_admin_permission
from autobot_shared.plugin_sdk import PluginLoader, PluginManager
from autobot_shared.plugin_sdk.base import PluginRegistry
from autobot_shared.plugin_sdk.hooks import HookRegistry
from services.audit.taxonomy import AuditAction
from user_management.models.base import Base
from user_management.models.plugin_enable_state import PluginEnableState

_MODULE = """
    from autobot_shared.plugin_sdk import BasePlugin
    from autobot_shared.plugin_sdk.hooks import HookRegistry

    class P(BasePlugin):
        async def initialize(self):
            HookRegistry().register_hook("gate_hook", lambda: self.manifest.name, self.manifest.name)

        async def shutdown(self):
            pass
"""


class RecordingAudit:
    """Same contract as ``audit_log``: awaited, True when the entry was committed."""

    def __init__(self) -> None:
        self.entries: list[dict] = []
        self.committed = True
        self.delay = 0.0

    async def __call__(self, operation, result="success", **kwargs) -> bool:
        await asyncio.sleep(self.delay)
        if self.committed:
            self.entries.append({"operation": operation, **kwargs})
        return self.committed


@pytest_asyncio.fixture
async def store():
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)  # canonical: ignore py-adhoc-db-engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[PluginEnableState.__table__])
    factory = async_sessionmaker(engine, expire_on_commit=False)  # canonical: ignore py-adhoc-db-engine
    yield pes.PluginEnableStore(factory)
    await engine.dispose()


@pytest.fixture
def audit(monkeypatch):
    sink = RecordingAudit()
    monkeypatch.setattr(pes, "audit_log", sink)
    return sink


@pytest.fixture
def plugin_root(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(tmp_path))
    before = set(sys.modules)
    names: list[str] = []
    yield tmp_path, names
    for name in names:
        PluginRegistry().unregister(name)
        HookRegistry().unregister_plugin(name)
    for key in set(sys.modules) - before:
        del sys.modules[key]


def _add_plugin(root, names, name):
    (root / name).mkdir()
    (root / name / "plugin.json").write_text(
        json.dumps(
            dict(name=name, version="1.0.0", display_name=name, description=name, author="mrveiss", entry_point=name)
        ),
        encoding="utf-8",
    )
    (root / f"{name}.py").write_text(textwrap.dedent(_MODULE), encoding="utf-8")
    names.append(name)


def _manager(root, store):
    return PluginManager([root], enable_gate=peg.DatabaseEnableGate(store))


@pytest.mark.asyncio
async def test_upgrade_grandfathers_what_was_running_and_audits_each(store, audit, plugin_root):
    root, names = plugin_root
    _add_plugin(root, names, "gate_old_a")
    _add_plugin(root, names, "gate_old_b")
    await store.touch_start()  # the previous backend started after the plugins were dropped in
    manager = _manager(root, store)
    await manager.startup()
    assert {"gate_old_a", "gate_old_b"} <= set(PluginRegistry().get_all_plugins())
    assert await store.enabled_names() == {"gate_old_a", "gate_old_b"}
    grandfathered = [e for e in audit.entries if e["operation"] == AuditAction.PLUGIN_GRANDFATHER]
    assert sorted(e["resource"] for e in grandfathered) == ["plugin:gate_old_a", "plugin:gate_old_b"]
    assert all(e["durable"] for e in grandfathered)
    await manager.shutdown()


@pytest.mark.asyncio
async def test_new_plugin_is_not_imported_until_an_admin_enables_it(store, audit, plugin_root):
    root, names = plugin_root
    _add_plugin(root, names, "gate_old_a")
    await store.touch_start()
    first = _manager(root, store)
    await first.startup()
    await first.shutdown()
    audit.entries.clear()

    _add_plugin(root, names, "gate_new_c")
    second = _manager(root, store)
    await second.startup()
    assert "gate_old_a" in PluginRegistry().get_all_plugins()
    assert "gate_new_c" not in sys.modules, "discovery must not import the module"
    assert second.get_gated_plugins() == ["gate_new_c"]
    assert second.get_load_report()["gated"] == ["gate_new_c"]
    assert audit.entries == [], "grandfathering runs once"

    admin = {"username": "root"}
    await pes.decide_plugin_enabled("gate_new_c", True, admin, second._loader, store)
    await pes.require_enabled("gate_new_c", store)
    assert await second._loader.load_plugin(_manifest(second, "gate_new_c"))
    assert "gate_new_c" in sys.modules
    await second.shutdown()


def _manifest(manager, name):
    return next(m for m in manager._loader.discover_plugins() if m.name == name)


@pytest.mark.asyncio
async def test_load_route_refuses_a_plugin_nobody_enabled(store):
    with pytest.raises(HTTPException) as refused:
        await pes.require_enabled("gate_never_enabled", store)
    assert refused.value.status_code == 403


@pytest.mark.asyncio
async def test_disable_is_audited_persisted_and_silences_hooks(store, audit, plugin_root):
    root, names = plugin_root
    _add_plugin(root, names, "gate_old_a")
    await store.touch_start()
    manager = _manager(root, store)
    await manager.startup()
    assert await HookRegistry().call_hook("gate_hook") == ["gate_old_a"]

    await pes.decide_plugin_enabled("gate_old_a", False, {"username": "root"}, manager._loader, store)
    entry = audit.entries[-1]
    assert (entry["operation"], entry["user_id"], entry["durable"]) == (AuditAction.PLUGIN_DISABLE, "root", True)
    assert await HookRegistry().call_hook("gate_hook") == []
    assert await store.enabled_names() == set(), "a disable survives a restart"
    await manager.shutdown()


@pytest.mark.asyncio
async def test_no_decision_without_an_audit_entry(store, audit, plugin_root):
    root, names = plugin_root
    _add_plugin(root, names, "gate_old_a")
    await store.touch_start()
    manager = _manager(root, store)
    await manager.startup()
    audit.committed = False
    with pytest.raises(HTTPException) as unavailable:
        await pes.decide_plugin_enabled("gate_old_a", False, {"username": "root"}, manager._loader, store)
    assert unavailable.value.status_code == 503
    assert await store.enabled_names() == {"gate_old_a"}
    await manager.shutdown()


@pytest.mark.asyncio
async def test_unknown_plugin_cannot_be_enabled(store, audit):
    with pytest.raises(HTTPException) as missing:
        await pes.decide_plugin_enabled("gate_ghost", True, {"username": "root"}, PluginLoader([]), store)
    assert missing.value.status_code == 404
    assert audit.entries == []


@pytest.mark.parametrize("suffix", ["enable", "disable", "load"])
def test_routes_are_admin_gated(suffix):
    route = next(r for r in plugin_routes.router.routes if isinstance(r, APIRoute) and r.path.endswith(f"/{suffix}"))
    assert check_admin_permission in {d.call for d in route.dependant.dependencies}


def _age(root, name, delta_s):
    """Move a plugin directory's files by *delta_s* seconds from now (negative = older)."""
    when = time.time() + delta_s
    for path in (root / name).rglob("*"):
        os.utime(path, (when, when))


@pytest.mark.asyncio
async def test_a_plugin_dropped_in_after_the_last_start_waits_for_an_admin(store, audit, plugin_root):
    root, names = plugin_root
    _add_plugin(root, names, "gate_old_a")
    _add_plugin(root, names, "gate_dropped_b")
    _age(root, "gate_old_a", -3600)
    _age(root, "gate_dropped_b", 3600)
    await store.touch_start()
    manager = _manager(root, store)
    await manager.startup()
    assert await store.enabled_names() == {"gate_old_a"}
    assert manager.get_gated_plugins() == ["gate_dropped_b"]
    assert [e["resource"] for e in audit.entries] == ["plugin:gate_old_a"]
    await manager.shutdown()


@pytest.mark.asyncio
async def test_empty_discovery_writes_no_baseline(store, audit, tmp_path):
    for missing in (tmp_path / "unmounted", tmp_path):
        manager = PluginManager([missing], enable_gate=peg.DatabaseEnableGate(store))
        await manager.startup()
        assert not await store.has_baseline()
        assert audit.entries == []


@pytest.mark.asyncio
async def test_two_concurrent_first_boots_grandfather_once(plugin_root, audit, tmp_path):
    root, names = plugin_root
    _add_plugin(root, names, "gate_old_a")
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'gate.db'}")  # canonical: ignore py-adhoc-db-engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[PluginEnableState.__table__])
    factory = async_sessionmaker(engine, expire_on_commit=False)  # canonical: ignore py-adhoc-db-engine
    audit.delay = 0.05
    await pes.PluginEnableStore(factory).touch_start()
    manifests = PluginLoader([root]).discover_plugins()
    locations = {"gate_old_a": root / "gate_old_a"}
    gates = [peg.DatabaseEnableGate(pes.PluginEnableStore(factory)) for _ in range(2)]
    admitted = await asyncio.gather(*(g.admit(manifests, locations) for g in gates))
    assert [[m.name for m in a] for a in admitted] == [["gate_old_a"], ["gate_old_a"]]
    assert [e["resource"] for e in audit.entries] == ["plugin:gate_old_a"], "the loser must not audit again"
    await engine.dispose()


class _FlakyStore:
    """The database is down for the first *failures* reads, then answers; everything else is the real store."""

    def __init__(self, inner: pes.PluginEnableStore, failures: int) -> None:
        self._inner, self.failures = inner, failures

    async def has_baseline(self) -> bool:
        if self.failures:
            self.failures -= 1
            raise ConnectionError("database unavailable")
        return await self._inner.has_baseline()

    def __getattr__(self, name):
        return getattr(self._inner, name)


@pytest.mark.asyncio
async def test_gate_failure_loads_nothing_then_retries_without_a_restart(store, audit, plugin_root, monkeypatch):
    root, names = plugin_root
    _add_plugin(root, names, "gate_old_a")
    await store.touch_start()
    monkeypatch.setattr(peg, "RETRY_INITIAL_S", 0.01)
    manager = PluginManager([root], enable_gate=peg.DatabaseEnableGate(_FlakyStore(store, failures=2)))
    await peg.start_plugin_manager(manager)
    assert "gate_old_a" not in PluginRegistry().get_all_plugins(), "fail closed"
    for _ in range(300):
        if "gate_old_a" in PluginRegistry().get_all_plugins():
            break
        await asyncio.sleep(0.02)
    assert "gate_old_a" in PluginRegistry().get_all_plugins(), "loaded once the database answered"
    assert manager.get_load_report()["completed"]
    await manager.shutdown()
