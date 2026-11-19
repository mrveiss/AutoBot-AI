# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""An agent-config edit and a rollback serialise under the one config write lock (#21742)."""

import threading
from types import SimpleNamespace

import config as config_pkg
from api.agent_config import DEFAULT_AGENT_CONFIGS
from services import config_rollback
from services.agent_config_writer import write_agent_enabled, write_agent_model
from services.config_rollback import rollback_locked

_AGENT = next(iter(DEFAULT_AGENT_CONFIGS))
_BASE = DEFAULT_AGENT_CONFIGS[_AGENT]


#: Longest the test waits to see the second writer NOT enter. Only the negative check is bounded by time;
#: the ordering itself comes from the events below.
_NEGATIVE_WAIT_SECONDS = 0.3
_PARK_TIMEOUT_SECONDS = 10


class _ParkingStore:
    """Settings store whose first write parks inside the locked operation until released."""

    def __init__(self):
        self.values = {}
        self.owners = []
        self.parked = threading.Event()
        self.release = threading.Event()
        self.second_entered = threading.Event()
        self._first = None

    def get_nested(self, key, default=None):
        return self.values.get(key, default)

    def set_nested(self, key, value):
        me = threading.current_thread().name
        self.owners.append(me)
        if self._first is None:
            self._first = me
            self.parked.set()
            assert self.release.wait(_PARK_TIMEOUT_SECONDS), "writer A was never released"
        elif me != self._first:
            self.second_entered.set()
        self.values[key] = value

    def save_settings(self):
        pass


class _Workers:
    """Threads that capture their exception and re-raise it from ``join``."""

    def __init__(self):
        self.errors = []
        self.threads = []

    def start(self, name, target):
        def run():
            try:
                target()
            except BaseException as exc:  # noqa: BLE001 - re-raised in join()
                self.errors.append(exc)

        thread = threading.Thread(target=run, name=name)
        self.threads.append(thread)
        thread.start()

    def join(self):
        for thread in self.threads:
            thread.join(_PARK_TIMEOUT_SECONDS)
            assert not thread.is_alive(), f"{thread.name} did not finish"
        if self.errors:
            raise self.errors[0]


def _run_serialised(store, writer_a, writer_b):
    """Park A inside its locked write, start B, prove B has not entered, release A, join both."""
    workers = _Workers()
    workers.start("writer-a", writer_a)
    assert store.parked.wait(_PARK_TIMEOUT_SECONDS), "writer A never reached its write"
    workers.start("writer-b", writer_b)
    entered = store.second_entered.wait(_NEGATIVE_WAIT_SECONDS)
    store.release.set()
    workers.join()
    assert not entered, "writer B entered its write while writer A held the config write lock"


def test_agent_edit_and_rollback_do_not_lose_either_write(monkeypatch):
    store = _ParkingStore()
    monkeypatch.setattr(config_pkg, "config_manager", store)
    monkeypatch.setattr(config_rollback.ConfigService, "clear_cache", lambda: None)
    update = SimpleNamespace(model="edited", provider="edited-provider")
    snapshot = {"model": "rolled-back", "provider": "rolled-provider", "enabled": False}

    _run_serialised(
        store,
        lambda: write_agent_model(store, _AGENT, _BASE, update),
        lambda: rollback_locked("agent", _AGENT, snapshot),
    )

    assert store.owners.index("writer-b") > max(i for i, o in enumerate(store.owners) if o == "writer-a")
    assert store.values[f"agents.{_AGENT}.enabled"] is False
    pair = (store.values[f"agents.{_AGENT}.model"], store.values[f"agents.{_AGENT}.provider"])
    assert pair == ("rolled-back", "rolled-provider"), f"B ran second, so its pair must win: {pair}"


def test_two_agent_edits_do_not_interleave():
    store = _ParkingStore()
    update = SimpleNamespace(model="m", provider="p")
    _run_serialised(
        store,
        lambda: write_agent_model(store, _AGENT, _BASE, update),
        lambda: write_agent_enabled(store, _AGENT, False),
    )
    assert store.values == {
        f"agents.{_AGENT}.model": "m",
        f"agents.{_AGENT}.provider": "p",
        f"agents.{_AGENT}.enabled": False,
    }
