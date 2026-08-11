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
    return SimpleNamespace(session_id="sess-1", context={})


def _call(name: str = "write_file", **args) -> dict:
    return {"name": name, "params": args or {"path": "/tmp/a"}}


def _verdict(verdict: VerifierVerdict, prob: float = 0.9, rationale: str = "flawed") -> VerifierResult:
    return VerifierResult(
        verdict=verdict,
        refutation_probability=prob,
        rationale=rationale,
        tool_name="write_file",
    )


def test_the_guard_is_reached_from_the_dispatch_seam() -> None:
    """`_dispatch_tool_call` must actually call it — a guard nothing invokes is #14031 all over again."""
    import inspect

    source = inspect.getsource(ToolHandlerMixin._dispatch_tool_call)

    assert "_enforce_pre_action_verifier(" in source


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
