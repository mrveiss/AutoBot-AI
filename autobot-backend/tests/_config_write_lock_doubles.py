# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shared deterministic helpers for the config write lock concurrency tests (#21742, #21858)."""

import threading

#: Longest the test waits to see the second writer NOT enter. Only the negative check is bounded by time;
#: the ordering itself comes from the events below.
_NEGATIVE_WAIT_SECONDS = 0.3
_PARK_TIMEOUT_SECONDS = 10


class ParkingStore:
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


class Workers:
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


def run_serialised(store, writer_a, writer_b):
    """Park A inside its locked write, start B, prove B has not entered, release A, join both."""
    workers = Workers()
    workers.start("writer-a", writer_a)
    assert store.parked.wait(_PARK_TIMEOUT_SECONDS), "writer A never reached its write"
    workers.start("writer-b", writer_b)
    entered = store.second_entered.wait(_NEGATIVE_WAIT_SECONDS)
    store.release.set()
    workers.join()
    assert not entered, "writer B entered its write while writer A held the config write lock"
