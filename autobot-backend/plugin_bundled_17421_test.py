# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Plugins under the core-plugins root are enabled by default; everything else still waits (#17421).

The real gate over a real table (SQLite) and real directories. Only the audit sink is faked, with the
``audit_log`` contract.
"""

import json
import time

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import plugin_enable_gate as peg
import plugin_enable_state as pes
import plugin_previous_start as pps
from autobot_shared import backend_start_marker as marker
from autobot_shared.plugin_sdk import PluginLoader, PluginManifest
from user_management.models.base import Base
from user_management.models.plugin_enable_state import PluginEnableState


class RecordingAudit:
    def __init__(self) -> None:
        self.entries: list[dict] = []

    async def __call__(self, operation, result="success", **kwargs) -> bool:
        self.entries.append({"operation": operation, **kwargs})
        return True


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
def fresh_install(tmp_path, monkeypatch):
    """No recorded start, no updater marker, no backend log: nothing can be grandfathered."""
    monkeypatch.setattr(marker, "marker_path", lambda: tmp_path / "marker")
    logs = tmp_path / "logs"
    logs.mkdir()
    monkeypatch.setattr(pps, "resolve_logs_dir", lambda: logs)
    monkeypatch.setattr(pps, "boot_started_at", lambda: time.time())


def _plugin(root, name):
    (root / name).mkdir(parents=True)
    data = dict(name=name, version="1.0.0", display_name=name, description=name, author="mrveiss", entry_point=name)
    (root / name / "plugin.json").write_text(json.dumps(data), encoding="utf-8")


def _gate(store, core):
    return peg.DatabaseEnableGate(store, core_roots=[core])


async def _admit(gate, *roots):
    manifests = PluginLoader(list(roots)).discover_plugins()
    locations = {m.name: next(r / m.name for r in roots if (r / m.name).exists()) for m in manifests}
    return sorted(m.name for m in await gate.admit(manifests, locations))


@pytest.mark.asyncio
async def test_a_fresh_install_enables_bundled_plugins_and_third_party_waits(store, audit, tmp_path, fresh_install):
    core, third = tmp_path / "core-plugins", tmp_path / "community-plugins"
    _plugin(core, "bundled_a")
    _plugin(third, "third_b")
    assert await _admit(_gate(store, core), core, third) == ["bundled_a"]
    assert await store.enabled_names() == {"bundled_a"}
    bundled = [e for e in audit.entries if e["resource"] == "plugin:bundled_a"]
    assert [e["operation"] for e in bundled] == [pes.AuditAction.PLUGIN_ENABLE]
    assert bundled[0]["durable"] and bundled[0]["details"]["reason"] == "bundled core plugin"


@pytest.mark.asyncio
async def test_an_admin_disabled_bundled_plugin_stays_off_across_restarts(store, audit, tmp_path, fresh_install):
    core = tmp_path / "core-plugins"
    _plugin(core, "bundled_a")
    gate = _gate(store, core)
    assert await _admit(gate, core) == ["bundled_a"]
    await store.put([("bundled_a", False, pes.SOURCE_ADMIN, "root")])
    audit.entries.clear()
    for _ in range(2):  # two restarts
        assert await _admit(_gate(store, core), core) == []
    assert audit.entries == [], "an existing row is never rewritten or re-audited"


@pytest.mark.asyncio
async def test_a_plugin_symlinked_into_the_core_root_is_not_bundled(store, audit, tmp_path, fresh_install):
    core, outside = tmp_path / "core-plugins", tmp_path / "elsewhere"
    core.mkdir()
    _plugin(outside, "linked_c")
    (core / "linked_c").symlink_to(outside / "linked_c", target_is_directory=True)
    manifest = PluginManifest(
        name="linked_c", version="1.0.0", display_name="c", description="c", author="mrveiss", entry_point="linked_c"
    )
    admitted = await _gate(store, core).admit([manifest], {"linked_c": core / "linked_c"})
    assert admitted == []
    assert await store.known_names() == set(), "not recorded as bundled"
