# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Direct config_manager writes and a rollback serialise under the one config write lock (#21858)."""

import config as config_pkg
from services import config_rollback
from services.config_manager_writer import merge_nested_and_save, set_nested_and_save
from services.config_rollback import rollback_locked
from tests._config_write_lock_doubles import ParkingStore, run_serialised

_ROLLBACK_AGENT = "orchestrator"


def test_developer_merge_and_rollback_do_not_lose_either_write(monkeypatch):
    store = ParkingStore()
    monkeypatch.setattr(config_pkg, "config_manager", store)
    monkeypatch.setattr(config_rollback.ConfigService, "clear_cache", lambda: None)
    snapshot = {"model": "rolled-back", "provider": "rolled-provider", "enabled": False}

    run_serialised(
        store,
        lambda: merge_nested_and_save(store, "developer", {"enabled": True}),
        lambda: rollback_locked("agent", _ROLLBACK_AGENT, snapshot),
    )

    assert store.values["developer"] == {"enabled": True}
    assert store.values[f"agents.{_ROLLBACK_AGENT}.model"] == "rolled-back"
    assert store.values[f"agents.{_ROLLBACK_AGENT}.enabled"] is False


def test_two_direct_writers_do_not_interleave():
    store = ParkingStore()
    run_serialised(
        store,
        lambda: set_nested_and_save(store, "embedding.models", ["a"]),
        lambda: set_nested_and_save(store, "security.hash", "h"),
    )
    assert store.values == {"embedding.models": ["a"], "security.hash": "h"}
