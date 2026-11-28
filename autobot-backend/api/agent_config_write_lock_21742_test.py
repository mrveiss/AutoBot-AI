# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""An agent-config edit and a rollback serialise under the one config write lock (#21742)."""

from types import SimpleNamespace

import config as config_pkg
from api.agent_config import DEFAULT_AGENT_CONFIGS
from services import config_rollback
from services.agent_config_writer import write_agent_enabled, write_agent_model
from services.config_rollback import rollback_locked
from tests._config_write_lock_doubles import ParkingStore, run_serialised

_AGENT = next(iter(DEFAULT_AGENT_CONFIGS))
_BASE = DEFAULT_AGENT_CONFIGS[_AGENT]


def test_agent_edit_and_rollback_do_not_lose_either_write(monkeypatch):
    store = ParkingStore()
    monkeypatch.setattr(config_pkg, "config_manager", store)
    monkeypatch.setattr(config_rollback.ConfigService, "clear_cache", lambda: None)
    update = SimpleNamespace(model="edited", provider="edited-provider")
    snapshot = {"model": "rolled-back", "provider": "rolled-provider", "enabled": False}

    run_serialised(
        store,
        lambda: write_agent_model(store, _AGENT, _BASE, update),
        lambda: rollback_locked("agent", _AGENT, snapshot),
    )

    assert store.owners.index("writer-b") > max(i for i, o in enumerate(store.owners) if o == "writer-a")
    assert store.values[f"agents.{_AGENT}.enabled"] is False
    pair = (store.values[f"agents.{_AGENT}.model"], store.values[f"agents.{_AGENT}.provider"])
    assert pair == ("rolled-back", "rolled-provider"), f"B ran second, so its pair must win: {pair}"


def test_two_agent_edits_do_not_interleave():
    store = ParkingStore()
    update = SimpleNamespace(model="m", provider="p")
    run_serialised(
        store,
        lambda: write_agent_model(store, _AGENT, _BASE, update),
        lambda: write_agent_enabled(store, _AGENT, False),
    )
    assert store.values == {
        f"agents.{_AGENT}.model": "m",
        f"agents.{_AGENT}.provider": "p",
        f"agents.{_AGENT}.enabled": False,
    }
