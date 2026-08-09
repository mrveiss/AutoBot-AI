# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the production repetition guard (#13590).

The guard exists to stop an agent burning the iteration budget on a call that
cannot produce new information. The hard part is not the counting — it is *not*
halting the legitimate patterns, so most of these assert the guard staying out
of the way.
"""

import os
from unittest.mock import patch

import pytest

from autobot_shared.repetition_guard import (
    call_fingerprint,
    last_result_hash,
    max_identical_tool_calls,
    register_call,
    repetition_halt_reason,
)


def _call(name="read_file", **args):
    return {"name": name, "params": args or {"path": "/tmp/a"}}


def _result(tool, value):
    return {"tool": tool, "status": "ok", "result": value}


# ----------------------------------------------------------- fingerprinting


def test_same_tool_and_args_fingerprint_identically():
    assert call_fingerprint(_call(path="/a")) == call_fingerprint(_call(path="/a"))


def test_different_args_fingerprint_differently():
    assert call_fingerprint(_call(path="/a")) != call_fingerprint(_call(path="/b"))


def test_argument_order_does_not_change_the_fingerprint():
    """Canonical hashing — key order is not a semantic difference."""
    a = {"name": "t", "params": {"x": 1, "y": 2}}
    b = {"name": "t", "params": {"y": 2, "x": 1}}

    assert call_fingerprint(a) == call_fingerprint(b)


def test_both_argument_key_spellings_are_read():
    """The seam passes `params` at some call sites and `arguments` at others."""
    assert call_fingerprint({"name": "t", "params": {"x": 1}}) == call_fingerprint(
        {"name": "t", "arguments": {"x": 1}}
    )


def test_last_result_hash_reads_the_most_recent_entry_for_that_tool():
    results = [_result("read_file", "old"), _result("other", "x"), _result("read_file", "new")]

    assert last_result_hash("read_file", results) != last_result_hash("read_file", results[:1])
    assert last_result_hash("absent", results) is None


# ------------------------------------------------------------- the halt


def test_an_identical_call_with_an_unchanged_result_halts_at_the_threshold():
    state, results = {}, [_result("read_file", "same")]

    assert repetition_halt_reason(_call(), results, state, threshold=3) is None
    assert repetition_halt_reason(_call(), results, state, threshold=3) is None
    reason = repetition_halt_reason(_call(), results, state, threshold=3)

    assert reason is not None
    assert "read_file" in reason, "the reason must name the tool — a silent halt is not actionable"


def test_the_halt_reason_says_what_to_do_next():
    state, results = {}, [_result("read_file", "same")]
    for _ in range(2):
        repetition_halt_reason(_call(), results, state, threshold=2)
    reason = repetition_halt_reason(_call(), results, state, threshold=2)

    assert "different approach" in reason or "explain" in reason


# ------------------------------------------- the patterns it must NOT halt


def test_a_polling_loop_against_a_changing_result_is_never_halted():
    """The whole reason the key is a pair. A single-counter guard breaks this."""
    state, results = {}, []

    for tick in range(10):
        results.append(_result("check_build", f"progress {tick}"))
        assert repetition_halt_reason(_call("check_build"), results, state, threshold=2) is None


def test_the_count_resets_when_the_result_finally_moves():
    state, results = {}, [_result("read_file", "same")]
    repetition_halt_reason(_call(), results, state, threshold=3)
    repetition_halt_reason(_call(), results, state, threshold=3)

    results.append(_result("read_file", "CHANGED"))

    assert repetition_halt_reason(_call(), results, state, threshold=3) is None, "a moved result is progress"


def test_different_arguments_are_counted_separately():
    state, results = {}, [_result("read_file", "same")]

    for path in ("/a", "/b", "/c", "/d"):
        assert repetition_halt_reason(_call(path=path), results, state, threshold=2) is None


def test_an_explicitly_pollable_tool_is_exempt():
    state, results = {}, [_result("sleep", "ok")]

    for _ in range(5):
        assert repetition_halt_reason({"name": "sleep", "params": {}}, results, state, threshold=2) is None


# ------------------------------------------------------- profile plumbing


def test_the_threshold_comes_from_the_guard_profile():
    """AUTOBOT_GUARD_PROFILE has read as a hardening control while changing nothing."""
    with patch.dict(os.environ, {"AUTOBOT_GUARD_PROFILE": "strict"}, clear=False):
        strict = max_identical_tool_calls()
    with patch.dict(os.environ, {"AUTOBOT_GUARD_PROFILE": "minimal"}, clear=False):
        minimal = max_identical_tool_calls()

    assert strict < minimal, "strict must halt sooner than minimal"


def test_an_unknown_profile_falls_back_rather_than_raising():
    with patch.dict(os.environ, {"AUTOBOT_GUARD_PROFILE": "nonsense"}, clear=False):
        assert max_identical_tool_calls() >= 1


def test_the_per_guard_env_override_wins():
    with patch.dict(
        os.environ, {"AUTOBOT_GUARD_PROFILE": "strict", "AUTOBOT_GUARD_MAX_IDENTICAL": "7"}, clear=False
    ):
        assert max_identical_tool_calls() == 7


@pytest.mark.parametrize("raw", ["0", "-3", "not-a-number"])
def test_a_nonsense_threshold_never_disables_the_guard(raw):
    """A threshold below 1 would halt every first call or none at all."""
    with patch.dict(os.environ, {"AUTOBOT_GUARD_MAX_IDENTICAL": raw}, clear=False):
        assert max_identical_tool_calls() >= 1


# ----------------------------------------------------------- concurrency


def test_two_sessions_do_not_share_counters():
    """State is caller-owned; two turns must not pool into one counter."""
    session_a, session_b = {}, {}
    results = [_result("read_file", "same")]

    for _ in range(2):
        repetition_halt_reason(_call(), results, session_a, threshold=3)

    assert repetition_halt_reason(_call(), results, session_b, threshold=3) is None
    assert register_call(_call(), results, session_b) == 2, "session B counted session A's calls"
