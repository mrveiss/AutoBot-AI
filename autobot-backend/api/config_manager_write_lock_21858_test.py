# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Direct config_manager writes and a rollback serialise under the one config write lock (#21858)."""

import config as config_pkg
from api.agent_config import DEFAULT_AGENT_CONFIGS
from api.agent_config_write_lock_21742_test import _AGENT, _ParkingStore, _run_serialised
from services import config_rollback
from services.config_manager_writer import merge_nested_and_save, set_nested_and_save
from services.config_rollback import rollback_locked


def test_developer_merge_and_rollback_do_not_lose_either_write(monkeypatch):
    store = _ParkingStore()
    monkeypatch.setattr(config_pkg, "config_manager", store)
    monkeypatch.setattr(config_rollback.ConfigService, "clear_cache", lambda: None)
    snapshot = {"model": "rolled-back", "provider": "rolled-provider", "enabled": False}

    _run_serialised(
        store,
        lambda: merge_nested_and_save(store, "developer", {"enabled": True}),
        lambda: rollback_locked("agent", _AGENT, snapshot),
    )

    assert store.values["developer"] == {"enabled": True}
    assert store.values[f"agents.{_AGENT}.model"] == "rolled-back"
    assert store.values[f"agents.{_AGENT}.enabled"] is False
    assert _AGENT in DEFAULT_AGENT_CONFIGS


def test_two_direct_writers_do_not_interleave():
    store = _ParkingStore()
    _run_serialised(
        store,
        lambda: set_nested_and_save(store, "embedding.models", ["a"]),
        lambda: set_nested_and_save(store, "security.hash", "h"),
    )
    assert store.values == {"embedding.models": ["a"], "security.hash": "h"}
