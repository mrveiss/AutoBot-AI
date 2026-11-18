# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Rollback restores the live config and never a placeholder over a secret (#18478)."""

import uuid
from types import SimpleNamespace

import pytest

from autobot_shared.secret_redaction import REDACTED_PLACEHOLDER
from services import config_rollback
from services.config_revision_service import ConfigRevisionService
from services.config_rollback import UnsupportedRollbackTarget, apply_snapshot, keep_live_secrets

_LIVE = "live-value"  # pragma: allowlist secret


class _LiveStore:
    """Stand-in for the live settings store; the assertions read this, not the revision table."""

    def __init__(self, config):
        self.config = config

    def get_full_config(self):
        return self.config

    def save_full_config(self, data):
        self.config = data
        return {"status": "success"}

    def get_backend_settings(self):
        return self.config.get("backend", {})

    def update_backend_settings(self, data):
        self.config["backend"] = data

    def clear_cache(self):
        pass


@pytest.fixture
def live(monkeypatch):
    store = _LiveStore({"llm": {"model": "new", "api_key": _LIVE}, "backend": {"port": 1}})  # pragma: allowlist secret
    for name in (
        "get_full_config",
        "save_full_config",
        "get_backend_settings",
        "update_backend_settings",
        "clear_cache",
    ):
        monkeypatch.setattr(config_rollback.ConfigService, name, getattr(store, name))
    return store


def test_settings_rollback_changes_the_live_read(live):
    apply_snapshot("system", "settings", {"llm": {"model": "old", "api_key": REDACTED_PLACEHOLDER}})
    assert live.get_full_config()["llm"]["model"] == "old"


def test_placeholders_keep_the_live_secret(live):
    snap = {"llm": {"model": "old", "api_key": REDACTED_PLACEHOLDER, "token": "***REDACTED***"}}
    apply_snapshot("system", "config", snap)
    assert live.get_full_config()["llm"] == {
        "model": "old",
        "api_key": _LIVE,
    }  # token has no live value: dropped


def test_keep_live_secrets_does_not_write_a_placeholder():
    assert keep_live_secrets({"a": REDACTED_PLACEHOLDER}, {}) == {}


def test_backend_rollback_changes_the_live_read(live):
    apply_snapshot("system", "backend", {"port": 2})
    assert live.get_backend_settings() == {"port": 2}


def test_agent_rollback_changes_the_live_agent_config(monkeypatch):
    import config as config_pkg

    calls = {}
    fake = SimpleNamespace(
        set_nested=lambda k, v: calls.__setitem__(k, v),
        save_settings=lambda: calls.__setitem__("saved", True),
    )
    fake.get_nested = lambda k, d=None: d
    monkeypatch.setattr(config_pkg, "config_manager", fake)
    monkeypatch.setattr(config_rollback.ConfigService, "clear_cache", lambda: None)
    from api.agent_config import DEFAULT_AGENT_CONFIGS

    agent = next(iter(DEFAULT_AGENT_CONFIGS))
    apply_snapshot("agent", agent, {"model": "m1", "provider": None, "enabled": False})
    assert calls == {f"agents.{agent}.model": "m1", f"agents.{agent}.enabled": False, "saved": True}


@pytest.mark.parametrize("etype,eid", [("bogus", "x"), ("system", "nope"), ("agent", "no-such-agent")])
def test_unknown_target_is_rejected(live, etype, eid):
    with pytest.raises(UnsupportedRollbackTarget):
        apply_snapshot(etype, eid, {"a": 1})


@pytest.mark.asyncio
async def test_failed_apply_records_no_rollback_row(monkeypatch, live):
    target = SimpleNamespace(entity_type="bogus", entity_id="x", after_config={"a": 1}, before_config=None)
    svc = ConfigRevisionService(session=SimpleNamespace())
    created = []

    async def _get(_id):
        return target

    async def _create(**kw):
        created.append(kw)

    monkeypatch.setattr(svc, "_get_or_raise", _get)
    monkeypatch.setattr(svc, "create_revision", _create)
    with pytest.raises(UnsupportedRollbackTarget):
        await svc.rollback_to_revision(uuid.uuid4(), "tester")
    assert created == []


def test_partial_snapshot_leaves_untouched_live_sections_intact(live):
    live.config["other"] = {"keep": 1}
    apply_snapshot("system", "settings", {"llm": {"model": "old"}})
    cfg = live.get_full_config()
    assert cfg["other"] == {"keep": 1}
    assert cfg["llm"] == {"model": "old", "api_key": _LIVE}


def test_only_keys_the_revision_changed_are_restored(live):
    live.config["other"] = {"keep": "later-edit"}
    before = {"llm": {"model": "a"}, "other": {"keep": "x"}}
    after = {"llm": {"model": "old"}, "other": {"keep": "x"}}
    apply_snapshot("system", "hardware_priority", after, before)
    cfg = live.get_full_config()
    assert cfg["llm"]["model"] == "old"
    assert cfg["other"] == {"keep": "later-edit"}


def test_nested_leaf_delta_does_not_reassert_sibling_leaves(live):
    live.config["llm"]["temp"] = "edited-later"
    before = {"llm": {"model": "a", "temp": "t0"}}
    after = {"llm": {"model": "old", "temp": "t0"}}
    apply_snapshot("system", "config", after, before)
    assert live.get_full_config()["llm"] == {"model": "old", "temp": "edited-later", "api_key": _LIVE}


def test_a_key_the_revision_deleted_is_deleted_from_live(live):
    live.config["llm"]["legacy"] = 1
    live.config["gone"] = {"x": 1}
    before = {"llm": {"model": "a", "legacy": 1}, "gone": {"x": 1}}
    after = {"llm": {"model": "a"}}
    apply_snapshot("system", "config", after, before)
    cfg = live.get_full_config()
    assert "legacy" not in cfg["llm"] and "gone" not in cfg


def test_keep_live_secrets_recurses_into_lists():
    snap = {"hosts": [{"name": "a", "pw": REDACTED_PLACEHOLDER}]}
    live = {"hosts": [{"name": "a", "pw": "live-pw"}]}  # pragma: allowlist secret
    assert keep_live_secrets(snap, live) == {"hosts": [{"name": "a", "pw": "live-pw"}]}  # pragma: allowlist secret


def test_agent_write_failure_restores_prior_values(monkeypatch):
    import config as config_pkg
    from api.agent_config import DEFAULT_AGENT_CONFIGS

    agent = next(iter(DEFAULT_AGENT_CONFIGS))
    store = {f"agents.{agent}.model": "old-model"}

    def _set(k, v):
        if k.endswith(".enabled"):
            raise RuntimeError("boom")
        store[k] = v

    fake = SimpleNamespace(get_nested=lambda k, d=None: store.get(k, d), set_nested=_set, save_settings=lambda: None)
    monkeypatch.setattr(config_pkg, "config_manager", fake)
    with pytest.raises(RuntimeError):
        apply_snapshot("agent", agent, {"model": "m2", "enabled": False})
    assert store == {f"agents.{agent}.model": "old-model"}


@pytest.mark.asyncio
async def test_row_before_after_come_from_the_locked_live_read(live):
    target = SimpleNamespace(
        entity_type="system", entity_id="settings", after_config={"llm": {"model": "old"}}, before_config=None
    )
    svc = ConfigRevisionService(session=SimpleNamespace())
    created = []

    async def _get(_id):
        return target

    async def _create(**kw):
        created.append(kw)
        return SimpleNamespace(id=uuid.uuid4())

    async def _latest(*_a):
        raise AssertionError("row must not be built from a separate _get_latest read")

    svc._get_or_raise, svc.create_revision, svc._get_latest = _get, _create, _latest
    await svc.rollback_to_revision(uuid.uuid4(), "tester")
    assert created[0]["before_config"]["llm"]["model"] == "new"
    assert created[0]["after_config"]["llm"]["model"] == "old"
