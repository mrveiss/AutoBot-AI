# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A cost record must actually land after a completion (#16845).

``LLMService._track_usage`` called ``LLMCostTracker.record(...)``, a method the
tracker has never defined. The ``AttributeError`` went into
``except Exception: logger.debug(...)``, so the main chat path recorded no spend
from 2026-04-01 until this was found -- and Budget Policy, which reads those
records, could not hard-stop chat traffic for the same five months.

Every assertion here is on a record arriving, never on a call being made.
``MagicMock()`` answers ``tracker.record(...)`` happily and returns another
mock, so a call-was-made test passes against the exact broken code. The doubles
below are ``create_autospec``'d against the real class for the same reason, and
``test_the_double_rejects_the_method_the_defect_called`` is the negative control
proving the double is strict enough to fail on the original defect -- a guard
whose subject cannot light it up is not evidence of anything.
"""

from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import MagicMock, create_autospec, patch

import pytest

from llm_shared.models import LLMResponse
from services.llm_cost_tracker import LLMCostTracker
from services.llm_usage_recording import (
    ESTIMATED_TOKENS,
    MEASURED_TOKENS,
    record_response_usage,
    record_token_usage,
    token_counts,
)

_LLM_SERVICE = Path(__file__).resolve().parent / "llm_service.py"


def _tracker() -> MagicMock:
    """A tracker double that accepts only methods the real class defines."""
    return create_autospec(LLMCostTracker, instance=True)


def _response(**overrides) -> LLMResponse:
    defaults = {
        "content": "hi",
        "model": "gpt-4o-mini",
        "provider": "openai",
        "usage": {"prompt_tokens": 120, "completion_tokens": 34, "total_tokens": 154},
        "processing_time": 1.5,
    }
    defaults.update(overrides)
    return LLMResponse(**defaults)


async def _record(response: LLMResponse, tracker: MagicMock, **kwargs) -> MagicMock:
    with patch("services.llm_usage_recording.get_cost_tracker", return_value=tracker):
        await record_response_usage(response, "session-1", **kwargs)
    return tracker


# ---------------------------------------------------------------------------
# Negative control: the double must fail on the defect it exists to catch
# ---------------------------------------------------------------------------


def test_the_tracker_has_no_record_method() -> None:
    """The defect itself, asserted directly so it cannot quietly come back."""
    assert not hasattr(LLMCostTracker, "record"), (
        "LLMCostTracker grew a `record` method. #16845 was about a call to a "
        "method that does not exist; if one now exists, this guard's premise "
        "changed and the call site needs re-reading, not this line deleting"
    )


def test_the_double_rejects_the_method_the_defect_called() -> None:
    """Without this, a clean run below would prove only that the double is lax."""
    with pytest.raises(AttributeError):
        _tracker().record(provider="openai", model="gpt-4o-mini", usage={}, conversation_id="c1")


# ---------------------------------------------------------------------------
# A record lands
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_completion_with_usage_lands_a_cost_record() -> None:
    tracker = await _record(_response(), _tracker())

    tracker.track_usage.assert_awaited_once()
    kwargs = tracker.track_usage.await_args.kwargs
    assert kwargs["provider"] == "openai"
    assert kwargs["model"] == "gpt-4o-mini"
    assert kwargs["input_tokens"] == 120
    assert kwargs["output_tokens"] == 34
    assert kwargs["session_id"] == "session-1"
    assert kwargs["success"] is True


@pytest.mark.asyncio
async def test_latency_is_recorded_in_milliseconds() -> None:
    tracker = await _record(_response(processing_time=1.5), _tracker())
    assert tracker.track_usage.await_args.kwargs["latency_ms"] == 1500.0


@pytest.mark.asyncio
async def test_an_errored_response_is_recorded_as_unsuccessful() -> None:
    """The fallback chain records the terminal error attempt too."""
    tracker = await _record(_response(error="upstream 500"), _tracker())

    kwargs = tracker.track_usage.await_args.kwargs
    assert kwargs["success"] is False
    assert kwargs["error_message"] == "upstream 500"


@pytest.mark.asyncio
async def test_caller_supplied_identity_reaches_the_record() -> None:
    """Budget policy keys on agent_id; a dropped one is an unenforceable record."""
    tracker = await _record(_response(), _tracker(), user_id="u1", agent_id="a1", endpoint="/v1/chat")

    kwargs = tracker.track_usage.await_args.kwargs
    assert (kwargs["user_id"], kwargs["agent_id"], kwargs["endpoint"]) == ("u1", "a1", "/v1/chat")


# ---------------------------------------------------------------------------
# The three outcomes stay distinguishable
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_usage_block_records_nothing_and_warns_about_nothing() -> None:
    """A provider that reports no usage is normal, not a fault to announce."""
    tracker = _tracker()
    with patch("services.llm_usage_recording.logger") as log:
        await _record(_response(usage={}), tracker)

    tracker.track_usage.assert_not_awaited()
    log.warning.assert_not_called()
    log.exception.assert_not_called()


@pytest.mark.asyncio
async def test_a_usage_block_without_token_keys_warns_instead_of_going_quiet() -> None:
    """A provider contract change must not read the same as "no usage"."""
    tracker = _tracker()
    with patch("services.llm_usage_recording.logger") as log:
        await _record(_response(usage={"total_tokens": 154}), tracker)

    tracker.track_usage.assert_not_awaited()
    log.warning.assert_called_once()


@pytest.mark.asyncio
async def test_a_tracker_failure_is_logged_with_a_traceback_not_swallowed_at_debug() -> None:
    """The actual #16845 defect: the failure existed, nobody could see it."""
    tracker = _tracker()
    tracker.track_usage.side_effect = RuntimeError("redis down")

    with patch("services.llm_usage_recording.logger") as log:
        await _record(_response(), tracker)

    log.exception.assert_called_once()
    log.debug.assert_not_called()


@pytest.mark.asyncio
async def test_a_tracker_failure_does_not_break_the_served_completion() -> None:
    tracker = _tracker()
    tracker.track_usage.side_effect = RuntimeError("redis down")
    await _record(_response(), tracker)  # must not raise


# ---------------------------------------------------------------------------
# Token extraction
# ---------------------------------------------------------------------------


def test_one_missing_token_key_is_zero_not_unreadable() -> None:
    assert token_counts({"prompt_tokens": 10}) == (10, 0)
    assert token_counts({"completion_tokens": 7}) == (0, 7)


def test_a_block_with_neither_token_key_is_unreadable() -> None:
    assert token_counts({"total_tokens": 17}) is None


def test_ollamas_native_key_names_are_not_read_here() -> None:
    """Ollama normalises upstream; reading its raw keys here would be a second
    contract, and a wrong one for every other provider."""
    assert token_counts({"prompt_eval_count": 10, "eval_count": 7}) is None


# ---------------------------------------------------------------------------
# The call sites must await it
# ---------------------------------------------------------------------------


def _parsed_llm_service() -> ast.Module:
    return ast.parse(_LLM_SERVICE.read_text(encoding="utf-8"))


def test_track_usage_is_a_coroutine_function() -> None:
    tree = _parsed_llm_service()
    defs = [
        n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "_track_usage"
    ]
    assert len(defs) == 1, f"expected exactly one _track_usage definition, found {len(defs)}"
    assert isinstance(defs[0], ast.AsyncFunctionDef)


def test_every_track_usage_call_is_awaited() -> None:
    """An un-awaited coroutine records nothing and raises nothing.

    That is the same shape as the bug this file exists for: a call that looks
    made and does nothing. Counted first so an empty result cannot read as pass.
    """
    tree = _parsed_llm_service()
    calls = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "_track_usage"
    ]
    assert len(calls) >= 3, f"expected the known _track_usage call sites, found {len(calls)} — has the file moved?"

    awaited = {id(n.value) for n in ast.walk(tree) if isinstance(n, ast.Await) and isinstance(n.value, ast.Call)}
    unawaited = [c.lineno for c in calls if id(c) not in awaited]
    assert not unawaited, f"_track_usage called without await at llm_service.py lines {unawaited}"


# ---------------------------------------------------------------------------
# record_token_usage: the compat gateways' entry point
# ---------------------------------------------------------------------------


async def _record_tokens(tracker: MagicMock, **kwargs) -> MagicMock:
    defaults = {"provider": "openai", "model": "gpt-4o-mini", "input_tokens": 12, "output_tokens": 3}
    defaults.update(kwargs)
    with patch("services.llm_usage_recording.get_cost_tracker", return_value=tracker):
        await record_token_usage(**defaults)
    return tracker


@pytest.mark.asyncio
async def test_loose_token_counts_land_a_cost_record() -> None:
    tracker = await _record_tokens(_tracker(), endpoint="/v1/chat/completions")

    kwargs = tracker.track_usage.await_args.kwargs
    assert (kwargs["input_tokens"], kwargs["output_tokens"]) == (12, 3)
    assert kwargs["endpoint"] == "/v1/chat/completions"


@pytest.mark.asyncio
async def test_estimated_tokens_are_recorded_as_estimated() -> None:
    """Streaming has no provider counts; estimated and measured spend must not
    be indistinguishable once in the ledger."""
    tracker = await _record_tokens(_tracker(), metadata=dict(ESTIMATED_TOKENS))
    assert tracker.track_usage.await_args.kwargs["metadata"] == {"token_source": "estimated"}


def test_the_two_token_sources_are_not_the_same_marker() -> None:
    """If these ever collapse, the ledger silently loses the distinction."""
    assert ESTIMATED_TOKENS != MEASURED_TOKENS


@pytest.mark.asyncio
async def test_a_tracker_failure_on_loose_counts_is_logged_not_raised() -> None:
    tracker = _tracker()
    tracker.track_usage.side_effect = RuntimeError("redis down")

    with patch("services.llm_usage_recording.logger") as log:
        await _record_tokens(tracker)  # must not raise

    log.exception.assert_called_once()
    log.debug.assert_not_called()


@pytest.mark.asyncio
async def test_the_model_override_wins_over_the_response_model() -> None:
    """The compat gateways price under resolved_model; a record naming a
    different model than the cost was computed from cannot be reconciled."""
    tracker = await _record(_response(model="gpt-4o-mini"), _tracker(), model="gpt-4o-2024-08-06")
    assert tracker.track_usage.await_args.kwargs["model"] == "gpt-4o-2024-08-06"


# ---------------------------------------------------------------------------
# The compat gateways must actually record (#16845 AC2)
# ---------------------------------------------------------------------------

_COMPAT_MODULES = ("openai_compat.py", "anthropic_compat.py")
_RECORDERS = {"record_token_usage", "record_response_usage"}


@pytest.mark.parametrize("module_name", _COMPAT_MODULES)
def test_each_compat_gateway_awaits_a_recorder_on_both_paths(module_name: str) -> None:
    """Both gateways priced usage with calculate_cost and persisted nothing.

    Asserted on the call being awaited, and on there being one per path
    (streaming + non-streaming), so dropping either half fails here rather than
    silently restoring half the defect.
    """
    path = _LLM_SERVICE.parent.parent / "api" / module_name
    assert path.is_file(), f"{module_name} moved; this guard has no subject"
    tree = ast.parse(path.read_text(encoding="utf-8"))

    awaited = [
        n.value.func.id
        for n in ast.walk(tree)
        if isinstance(n, ast.Await) and isinstance(n.value, ast.Call) and isinstance(n.value.func, ast.Name)
    ]
    recorded = [name for name in awaited if name in _RECORDERS]
    assert len(recorded) >= 2, (
        f"{module_name} awaits {len(recorded)} recorder call(s); expected one for the "
        "streaming path and one for the non-streaming path"
    )
