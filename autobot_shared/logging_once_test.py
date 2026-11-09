# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The shared log-once helper (#21071)."""

from __future__ import annotations

import logging
import threading

import pytest

from autobot_shared import logging_once
from autobot_shared.logging_once import first_time, log_once, reset_log_once


@pytest.fixture(autouse=True)
def _clean():
    reset_log_once()
    yield
    reset_log_once()


def test_a_key_logs_once_at_the_given_level(caplog):
    log = logging.getLogger("once.a")
    with caplog.at_level(logging.INFO, logger="once.a"):
        assert log_once(log, logging.INFO, "k", "hello %s", "x") is True
        assert log_once(log, logging.INFO, "k", "hello %s", "y") is False
    assert [(r.levelno, r.getMessage()) for r in caplog.records] == [(logging.INFO, "hello x")]


def test_the_record_points_at_the_caller(caplog):
    log = logging.getLogger("once.b")
    with caplog.at_level(logging.WARNING, logger="once.b"):
        log_once(log, logging.WARNING, "k", "m")
    assert caplog.records[0].funcName == "test_the_record_points_at_the_caller"


def test_scope_is_the_logger_so_modules_may_share_a_key(caplog):
    with caplog.at_level(logging.WARNING):
        log_once(logging.getLogger("once.c1"), logging.WARNING, "k", "one")
        log_once(logging.getLogger("once.c2"), logging.WARNING, "k", "two")
    assert [r.getMessage() for r in caplog.records] == ["one", "two"]


def test_reset_scopes(caplog):
    a, b = logging.getLogger("once.d1"), logging.getLogger("once.d2")
    for lg in (a, b):
        log_once(lg, logging.WARNING, "k", "m")
        log_once(lg, logging.WARNING, "j", "m")
    reset_log_once(a, "k")
    assert first_time("once.d1", "k") and not first_time("once.d1", "j")
    reset_log_once("once.d2")
    assert first_time("once.d2", "k") and first_time("once.d2", "j")


def test_the_key_set_is_bounded_least_recent_first(monkeypatch):
    monkeypatch.setattr(logging_once, "_MAX_KEYS", 2)
    assert first_time("s", "a") and first_time("s", "b")
    assert not first_time("s", "a")  # refreshes a, so b is now the oldest
    assert first_time("s", "c")  # evicts b
    assert len(logging_once._SEEN) == 2
    assert not first_time("s", "a") and first_time("s", "b")


def test_concurrent_first_sights_emit_exactly_once():
    wins: list[bool] = []
    gate = threading.Barrier(16)

    def work():
        gate.wait()
        wins.append(first_time("race", "k"))

    threads = [threading.Thread(target=work) for _ in range(16)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert wins.count(True) == 1


def test_works_with_get_logger(caplog):
    from autobot_shared.logging_manager import get_logger

    log = get_logger("once.e")
    log.propagate = True
    with caplog.at_level(logging.WARNING, logger="once.e"):
        log_once(log, logging.WARNING, "k", "via get_logger")
        log_once(log, logging.WARNING, "k", "via get_logger")
    assert [r.getMessage() for r in caplog.records] == ["via get_logger"]
