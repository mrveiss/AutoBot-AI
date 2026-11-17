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
async def test_failed_apply_records_no_rollback_row(monkeypatch):
    target = SimpleNamespace(entity_type="bogus", entity_id="x", after_config={"a": 1})
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
