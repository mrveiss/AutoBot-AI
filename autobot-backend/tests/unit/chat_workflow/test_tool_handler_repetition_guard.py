# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Dispatch-level repetition enforcement (#13590).

Proves the repetition guard — previously only in the dormant `agent_loop` path —
now fires on the real production tool-dispatch seam
(`ToolHandlerMixin._dispatch_tool_call` via `_enforce_repetition`).

The unit-level behaviour of the counter lives in
`autobot_shared/repetition_guard_test.py`. What is asserted here is the seam
wiring: that the guard is reached, that its state is per-turn, and that
`AUTOBOT_GUARD_PROFILE` reaches it — the control that has read as hardening
while changing nothing in production.
"""

import os
from dataclasses import dataclass, field
from typing import Any, Dict
from unittest.mock import patch

import pytest

from chat_workflow.tool_handler import ToolHandlerMixin


def _mixin() -> ToolHandlerMixin:
    return ToolHandlerMixin.__new__(ToolHandlerMixin)


@dataclass
class _Ctx:
    """Stand-in for LLMIterationContext — the guard only touches `.context`."""

    context: Dict[str, Any] = field(default_factory=dict)


def _call(name: str = "read_file", **args: Any) -> Dict[str, Any]:
    return {"name": name, "params": args or {"path": "/tmp/a"}}


def _result(tool: str, value: str) -> Dict[str, Any]:
    return {"tool": tool, "status": "ok", "result": value}


def _drive(mixin, ctx, results, times, tool="read_file"):
    """Issue *times* identical calls; return the first halt message, if any."""
    for _ in range(times):
        msg = mixin._enforce_repetition(_call(tool), ctx, results)
        if msg is not None:
            return msg
    return None


def test_the_guard_is_reached_from_the_dispatch_seam() -> None:
    """`_dispatch_tool_call` must actually call it — a guard nothing invokes is #13590 again."""
    import inspect

    source = inspect.getsource(ToolHandlerMixin._dispatch_tool_call)

    assert "_enforce_repetition(" in source


def test_repeated_identical_calls_with_an_unchanged_result_halt() -> None:
    ctx, results = _Ctx(), [_result("read_file", "same")]

    msg = _drive(_mixin(), ctx, results, times=10)

    assert msg is not None
    assert msg.type == "error"
    assert msg.metadata.get("repetition_halt") is True
    assert results[-1]["repetition_halt"] is True
    assert results[-1]["status"] == "error"


def test_a_polling_loop_is_not_halted() -> None:
    """The result moves every turn — this is progress, not repetition."""
    mixin, ctx, results = _mixin(), _Ctx(), []

    for tick in range(12):
        results.append(_result("check_build", f"step {tick}"))
        assert mixin._enforce_repetition(_call("check_build"), ctx, results) is None


def test_without_a_context_the_guard_is_a_no_op() -> None:
    """Matches every other enforcer at this seam; per-turn state has nowhere to live."""
    assert _mixin()._enforce_repetition(_call(), None, [_result("read_file", "same")]) is None


def test_state_is_per_turn_not_module_global() -> None:
    """The seam is concurrent across sessions; counters must not pool."""
    mixin, results = _mixin(), [_result("read_file", "same")]
    session_a, session_b = _Ctx(), _Ctx()

    assert _drive(mixin, session_a, results, times=10) is not None
    assert mixin._enforce_repetition(_call(), session_b, results) is None, "session B inherited A's count"


def test_the_guard_stores_its_state_under_a_namespaced_key() -> None:
    """`ctx.context` is shared with other guards — collisions would be silent."""
    from autobot_shared.repetition_guard import REPETITION_STATE_KEY

    ctx = _Ctx(context={"_fact_forcing_investigated": set()})
    _mixin()._enforce_repetition(_call(), ctx, [_result("read_file", "x")])

    assert REPETITION_STATE_KEY in ctx.context
    assert ctx.context["_fact_forcing_investigated"] == set(), "another guard's state was clobbered"


@pytest.mark.parametrize(("profile", "identical_calls"), [("strict", 2), ("minimal", 5)])
def test_the_active_profile_changes_live_behaviour(profile: str, identical_calls: int) -> None:
    """AUTOBOT_GUARD_PROFILE=strict must demonstrably halt sooner than minimal."""
    mixin, results = _mixin(), [_result("read_file", "same")]

    with patch.dict(os.environ, {"AUTOBOT_GUARD_PROFILE": profile}, clear=False):
        os.environ.pop("AUTOBOT_GUARD_MAX_IDENTICAL", None)
        ctx = _Ctx()
        # One call short of the profile's threshold must still be allowed …
        assert _drive(mixin, ctx, results, times=identical_calls - 1) is None
        # … and the next one halts.
        assert mixin._enforce_repetition(_call(), ctx, results) is not None


def test_a_stagnation_run_halts_with_a_distinct_reason() -> None:
    """Different calls, nothing learned — a separate halt from repetition."""
    mixin, ctx = _mixin(), _Ctx()
    results = [{"tool": f"t{i}", "status": "ok", "result": "the same words over and over"} for i in range(12)]

    with patch.dict(os.environ, {"AUTOBOT_GUARD_PROFILE": "strict"}, clear=False):
        msg = mixin._enforce_repetition(_call("something_new"), ctx, results)

    assert msg is not None
    assert msg.metadata.get("stagnation_halt") is True
    assert msg.metadata.get("repetition_halt") is None, "the two halts must stay distinguishable"


def test_a_productive_run_is_not_halted_as_stagnant() -> None:
    mixin, ctx = _mixin(), _Ctx()
    results = [
        {"tool": f"t{i}", "status": "ok", "result": f"entirely distinct finding {i} about subsystem {i}"}
        for i in range(12)
    ]

    with patch.dict(os.environ, {"AUTOBOT_GUARD_PROFILE": "strict"}, clear=False):
        assert mixin._enforce_repetition(_call("something_new"), ctx, results) is None
