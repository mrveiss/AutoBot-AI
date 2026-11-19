# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""An agent-config edit and a rollback serialise under the one config write lock (#21742)."""

import threading
import time
from types import SimpleNamespace

import config as config_pkg
from api.agent_config import DEFAULT_AGENT_CONFIGS
from services import config_rollback
from services.agent_config_writer import write_agent_enabled, write_agent_model
from services.config_rollback import rollback_locked

_AGENT = next(iter(DEFAULT_AGENT_CONFIGS))
_BASE = DEFAULT_AGENT_CONFIGS[_AGENT]


class _SlowStore:
    """Settings store whose writes yield, so an unlocked second writer would interleave."""

    def __init__(self):
        self.values = {}
        self.events = []

    def get_nested(self, key, default=None):
        return self.values.get(key, default)

    def set_nested(self, key, value):
        self.events.append((threading.current_thread().name, "set"))
        time.sleep(0.02)
        self.values[key] = value

    def save_settings(self):
        self.events.append((threading.current_thread().name, "save"))


def _run_concurrently(*targets):
    threads = [threading.Thread(target=t, name=f"w{i}") for i, t in enumerate(targets)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()


def _assert_no_interleave(events):
    owners = [name for name, _ in events]
    runs = [n for i, n in enumerate(owners) if i == 0 or owners[i - 1] != n]
    assert len(runs) == len(set(runs)), f"writers interleaved: {events}"


def test_agent_edit_and_rollback_do_not_lose_either_write(monkeypatch):
    store = _SlowStore()
    monkeypatch.setattr(config_pkg, "config_manager", store)
    monkeypatch.setattr(config_rollback.ConfigService, "clear_cache", lambda: None)
    update = SimpleNamespace(model="edited", provider="edited-provider")
    snapshot = {"model": "rolled-back", "provider": None, "enabled": False}

    _run_concurrently(
        lambda: write_agent_model(store, _AGENT, _BASE, update),
        lambda: rollback_locked("agent", _AGENT, snapshot),
    )

    _assert_no_interleave(store.events)
    assert store.values[f"agents.{_AGENT}.enabled"] is False
    assert store.values[f"agents.{_AGENT}.model"] in {"edited", "rolled-back"}


def test_two_agent_edits_do_not_interleave():
    store = _SlowStore()
    update = SimpleNamespace(model="m", provider=None)
    _run_concurrently(
        lambda: write_agent_model(store, _AGENT, _BASE, update),
        lambda: write_agent_enabled(store, _AGENT, False),
    )
    _assert_no_interleave(store.events)
