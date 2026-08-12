# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Dispatch-level pre-action verifier enforcement (#10547, extracted #14031).

Proves the adversarial pre-action verifier — previously reachable only through
the dormant `AgentLoop` (no production caller, #13587/#14031) — now fires on
the real production tool-dispatch seam (`ToolHandlerMixin._dispatch_tool_call`
via `_enforce_pre_action_verifier`). Only `SENSITIVE_TOOLS` are verified, a
BLOCK verdict with `VERIFIER_HARD_BLOCK=1` hard-blocks, and without it the call
is held pending approval with the verifier's rationale attached.

The unit-level behaviour of the pure decision surface (threshold resolution,
verdict determination) lives in
`autobot_shared/pre_action_verifier_guard_test.py`. What is asserted here is
the seam wiring.
"""

import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from autobot_shared.pre_action_verifier_guard import VerifierResult, VerifierVerdict
from chat_workflow.tool_handler import ToolHandlerMixin


def _mixin() -> ToolHandlerMixin:
    return ToolHandlerMixin.__new__(ToolHandlerMixin)


def _ctx() -> SimpleNamespace:
    # `agent_context`/`requires_approval_before`/`consecutive_invalid_tool_calls`
    # are only touched by the OTHER stops on the seam (forbidden_work,
    # work-item approval, the unknown-tool fallback) — included here so this
    # stand-in also survives a full `_dispatch_tool_call` drive that falls
    # through past the verifier (e.g. under the mutation test below), not just
    # direct `_enforce_pre_action_verifier` calls.
    return SimpleNamespace(
        session_id="sess-1",
        context={},
        agent_context=None,
        requires_approval_before=None,
        consecutive_invalid_tool_calls=0,
    )


def _call(name: str = "write_file", **args) -> dict:
    return {"name": name, "params": args or {"path": "/tmp/a"}}


def _verdict(verdict: VerifierVerdict, prob: float = 0.9, rationale: str = "flawed") -> VerifierResult:
    return VerifierResult(
        verdict=verdict,
        refutation_probability=prob,
        rationale=rationale,
        tool_name="write_file",
    )


def test_the_call_site_still_names_the_enforcer() -> None:
    """Rename guard, NOT a wiring guard (see `test_the_live_dispatch_seam_...` below).

    A source-text substring check proves the call is *written*, not that it is
    *reached* — it stays green if the call sits after an early `return`, behind
    a condition that is never true, or is otherwise made dead while the text
    stays in the file. It exists only to catch the call site being renamed or
    deleted outright; it is deliberately NOT relied on for wiring proof.
    """
    import inspect

    source = inspect.getsource(ToolHandlerMixin._dispatch_tool_call)

    assert "_enforce_pre_action_verifier(" in source


@pytest.mark.asyncio
async def test_the_live_dispatch_seam_reaches_and_awaits_the_verifier() -> None:
    """Behavioural wiring proof: drive the REAL `_dispatch_tool_call`, not a text scan.

    Patches `PreActionVerifier.verify` and asserts it was awaited with the
    call the seam should have passed it, end to end through the actual
    enforcer chain (forbidden_work -> config_protection -> fact_forcing ->
    verifier -> ...). This is what catches the failure mode a source-text
    check cannot: the call site present in the file but unreachable.
    """
    verify_mock = AsyncMock(return_value=_verdict(VerifierVerdict.BLOCK, prob=0.9, rationale="flawed"))
    execution_results: list = []
    messages = []

    with patch("autobot_shared.pre_action_verifier_guard.PreActionVerifier.verify", new=verify_mock):
        async for item in _mixin()._dispatch_tool_call(
            _call("write_file", path="/tmp/a"),
            "session-1",
            "term-1",
            "http://localhost:11434",
            "test-model",
            execution_results,
            [],
            ctx=_ctx(),
        ):
            messages.append(item)

    verify_mock.assert_awaited_once()
    awaited = verify_mock.await_args
    assert awaited.args[0] == "write_file"
    assert awaited.args[1] == {"path": "/tmp/a"}
    assert awaited.kwargs.get("task_id") == "sess-1"
    # The BLOCK verdict short-circuits dispatch — only the verifier's own
    # message is yielded, proving the call was reached mid-seam, not bypassed.
    assert len(messages) == 1
    assert messages[0].type == "approval_required"


@pytest.mark.asyncio
async def test_a_non_sensitive_tool_is_never_verified() -> None:
    """respond/delegate/read_file etc. are outside SENSITIVE_TOOLS — no LLM round trip."""
    with patch(
        "autobot_shared.pre_action_verifier_guard.PreActionVerifier.verify",
        new=AsyncMock(side_effect=AssertionError("verify() must not be called for a non-sensitive tool")),
    ):
        result = await _mixin()._enforce_pre_action_verifier(_call("read_file"), _ctx(), [])

    assert result is None


@pytest.mark.asyncio
async def test_disabled_via_guard_profile_is_a_no_op() -> None:
    with (
        patch.dict(os.environ, {"AUTOBOT_GUARD_VERIFIER": "0"}, clear=False),
        patch(
            "autobot_shared.pre_action_verifier_guard.PreActionVerifier.verify",
            new=AsyncMock(side_effect=AssertionError("verify() must not run when the guard is disabled")),
        ),
    ):
        result = await _mixin()._enforce_pre_action_verifier(_call(), _ctx(), [])

    assert result is None


@pytest.mark.asyncio
async def test_a_pass_verdict_lets_the_call_proceed() -> None:
    with patch(
        "autobot_shared.pre_action_verifier_guard.PreActionVerifier.verify",
        new=AsyncMock(return_value=_verdict(VerifierVerdict.PASS, prob=0.1)),
    ):
        execution_results: list = []
        result = await _mixin()._enforce_pre_action_verifier(_call(), _ctx(), execution_results)

    assert result is None
    assert execution_results == []


@pytest.mark.asyncio
async def test_block_without_hard_block_holds_for_approval_with_rationale() -> None:
    with (
        patch.dict(os.environ, {}, clear=False),
        patch(
            "autobot_shared.pre_action_verifier_guard.HARD_BLOCK",
            False,
        ),
        patch(
            "autobot_shared.pre_action_verifier_guard.PreActionVerifier.verify",
            new=AsyncMock(return_value=_verdict(VerifierVerdict.BLOCK, prob=0.92, rationale="path does not exist")),
        ),
    ):
        execution_results: list = []
        result = await _mixin()._enforce_pre_action_verifier(_call(), _ctx(), execution_results)

    assert result is not None
    assert result.type == "approval_required"
    assert "path does not exist" in result.content
    assert execution_results[-1]["status"] == "pending_approval"
    assert execution_results[-1]["verifier_rationale"] == "path does not exist"


@pytest.mark.asyncio
async def test_block_with_hard_block_stops_the_call_outright() -> None:
    with (
        patch(
            "autobot_shared.pre_action_verifier_guard.HARD_BLOCK",
            True,
        ),
        patch(
            "autobot_shared.pre_action_verifier_guard.PreActionVerifier.verify",
            new=AsyncMock(return_value=_verdict(VerifierVerdict.BLOCK, prob=0.95, rationale="hard-blocked reason")),
        ),
    ):
        execution_results: list = []
        result = await _mixin()._enforce_pre_action_verifier(_call(), _ctx(), execution_results)

    assert result is not None
    assert result.type == "error"
    assert result.metadata.get("verifier_hard_block") is True
    assert execution_results[-1]["status"] == "error"
    assert execution_results[-1]["verifier_hard_block"] is True


@pytest.mark.asyncio
async def test_works_without_a_context() -> None:
    """Unlike repetition/fact-forcing the verifier carries no per-turn state — no ctx needed."""
    with patch(
        "autobot_shared.pre_action_verifier_guard.PreActionVerifier.verify",
        new=AsyncMock(return_value=_verdict(VerifierVerdict.PASS, prob=0.1)),
    ):
        result = await _mixin()._enforce_pre_action_verifier(_call(), None, [])

    assert result is None
