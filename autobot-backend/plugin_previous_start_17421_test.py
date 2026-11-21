# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The upgrade boot's "previous start": recorded start, updater marker, backend log, else nothing (#17421).

Each branch runs the real gate over a real table (SQLite) and real plugin directories with controlled file
times. Only the audit sink is faked, with the ``audit_log`` contract.
"""

import asyncio
import json
import os
import time
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import plugin_enable_gate as peg
import plugin_enable_state as pes
import plugin_previous_start as pps
from autobot_shared import backend_start_marker as marker
from autobot_shared.plugin_sdk import PluginLoader
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
def plugins(tmp_path):
    """An old plugin (files an hour old) and a newer one (an hour in the future), discovered for real."""
    root = tmp_path / "plugins"
    for name, offset in (("prev_old", -3600), ("prev_new", 3600)):
        (root / name).mkdir(parents=True)
        manifest = dict(name=name, version="1.0.0", display_name=name, description=name, author="mrveiss")
        (root / name / "plugin.json").write_text(json.dumps(dict(manifest, entry_point=name)), encoding="utf-8")
        when = time.time() + offset
        os.utime(root / name / "plugin.json", (when, when))
    loader = PluginLoader([root])
    manifests = loader.discover_plugins()
    return manifests, {m.name: root / m.name for m in manifests}


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """No marker, an empty log directory, and a boot that began now."""
    monkeypatch.setattr(marker, "marker_path", lambda: tmp_path / "marker")
    logs = tmp_path / "logs"
    logs.mkdir()
    monkeypatch.setattr(pps, "resolve_logs_dir", lambda: logs)
    monkeypatch.setattr(pps, "boot_started_at", lambda: time.time())
    return tmp_path, logs


async def _admitted(store, plugins):
    manifests, locations = plugins
    admitted = await peg.DatabaseEnableGate(store).admit(manifests, locations)
    return sorted(m.name for m in admitted)


@pytest.mark.asyncio
async def test_updater_marker_scopes_the_grandfather(store, audit, plugins, isolated):
    marker.write_marker(datetime.now(timezone.utc))
    assert await _admitted(store, plugins) == ["prev_old"]
    assert [e["resource"] for e in audit.entries] == ["plugin:prev_old"]
    assert "updater marker" in audit.entries[0]["details"]["reason"]


@pytest.mark.asyncio
async def test_backend_log_is_the_fallback_and_ignores_this_boots_own_line(store, audit, plugins, isolated):
    _, logs = isolated
    stamp = "%Y-%m-%d %H:%M:%S"
    previous = time.strftime(stamp, time.localtime(time.time() - 60))
    own = time.strftime(stamp, time.localtime(time.time() + 120))  # written by this boot, after it began
    line = "%s,123 - autobot_shared.plugin_sdk.plugin_manager - INFO - " + pps.START_LINE + "\n"
    log = logs / "backend.log"
    await asyncio.to_thread(log.write_text, (line % previous) + (line % own), encoding="utf-8")
    assert await _admitted(store, plugins) == ["prev_old"]
    assert "backend log" in audit.entries[0]["details"]["reason"]


@pytest.mark.asyncio
async def test_no_source_grandfathers_nothing_and_audits_why(store, audit, plugins, isolated):
    assert await _admitted(store, plugins) == []
    assert await store.has_baseline(), "the baseline is written so a later boot does not grandfather"
    assert await store.enabled_names() == set()
    (entry,) = audit.entries
    assert entry["details"]["reason"].startswith("no previous start is known")
    assert entry["durable"]


@pytest.mark.asyncio
async def test_a_recorded_start_wins_over_the_marker(store, audit, plugins, isolated):
    marker.write_marker(datetime.fromtimestamp(time.time() - 7200, tz=timezone.utc))  # would exclude both
    await store.touch_start()
    assert await _admitted(store, plugins) == ["prev_old"]


def test_systemd_unix_timestamps_parse():
    assert marker.parse_unix_timestamp("@1763700000\n") == datetime.fromtimestamp(1763700000, tz=timezone.utc)
    assert marker.parse_unix_timestamp("") is None
    assert marker.parse_unix_timestamp("@0") is None
    assert marker.parse_unix_timestamp("Sat 2026-11-21 10:12:33 UTC") is None
