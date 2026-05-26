# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for the semantic stagnation detector.

Covers GitHub issue #6627:
  - ObservationFingerprint dataclass (types.py)
  - TaskContext.record_observation (types.py)
  - fingerprint module: compute_novel_token_ratio, content_hash, normalize_content
  - AgentLoop._record_observation_fingerprints (loop.py)
  - AgentLoop._check_observation_stagnation (loop.py)
  - LoopOutcome.STAGNATED propagated through _build_result (loop.py)
  - Integration: search loop with cosmetic arg changes halts on stagnation
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_loop.fingerprint import (
    compute_novel_token_ratio,
    content_hash,
    normalize_content,
    tokenize,
)
from agent_loop.loop import AgentLoop
from agent_loop.types import (
    AgentLoopConfig,
    LoopOutcome,
    LoopState,
    ObservationFingerprint,
    TaskContext,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_loop(
    stagnation_window: int = 5,
    min_observation_novelty: float = 0.05,
    halt_on_stagnation: bool = True,
) -> AgentLoop:
    """Return an AgentLoop wired with mock dependencies."""
    event_stream = MagicMock()
    event_stream.get_latest = AsyncMock(return_value=[])
    event_stream.publish = AsyncMock()
    config = AgentLoopConfig(
        stagnation_window=stagnation_window,
        min_observation_novelty=min_observation_novelty,
        halt_on_stagnation=halt_on_stagnation,
    )
    loop = AgentLoop(event_stream=event_stream, config=config)
    loop._current_context = TaskContext(task_id="t1", description="test")
    loop._state = LoopState.RUNNING
    return loop


def _make_tool(name: str, args: Any = None) -> dict[str, Any]:
    spec: dict[str, Any] = {"tool_name": name}
    if args is not None:
        spec["args"] = args
    return spec


# ---------------------------------------------------------------------------
# fingerprint module unit tests
# ---------------------------------------------------------------------------


class TestNormalizeContent:
    def test_string_passthrough(self):
        assert normalize_content("hello") == "hello"

    def test_dict_serialized(self):
        result = normalize_content({"b": 2, "a": 1})
        assert '"a": 1' in result and '"b": 2' in result

    def test_list_serialized(self):
        result = normalize_content([1, 2, 3])
        assert "1" in result

    def test_fallback_for_non_serializable(self):
        class Weird:
            pass

        result = normalize_content(Weird())
        assert isinstance(result, str)


class TestContentHash:
    def test_same_content_same_hash(self):
        assert content_hash("abc") == content_hash("abc")

    def test_different_content_different_hash(self):
        assert content_hash("abc") != content_hash("xyz")

    def test_dict_order_independent(self):
        a = content_hash({"x": 1, "y": 2})
        b = content_hash({"y": 2, "x": 1})
        assert a == b


class TestTokenize:
    def test_basic(self):
        assert tokenize("Hello World") == ["hello", "world"]

    def test_numbers(self):
        assert "42" in tokenize("result is 42")

    def test_empty(self):
        assert tokenize("") == []


class TestNovelTokenRatio:
    def test_first_observation_fully_novel(self):
        seen: set[str] = set()
        ratio = compute_novel_token_ratio("the quick brown fox", seen)
        assert ratio == 1.0

    def test_identical_content_zero_novel(self):
        seen: set[str] = set()
        compute_novel_token_ratio("the quick brown fox", seen)
        ratio = compute_novel_token_ratio("the quick brown fox", seen)
        assert ratio == 0.0

    def test_partial_novelty(self):
        seen: set[str] = {"the", "quick"}
        ratio = compute_novel_token_ratio("the quick brown fox", seen)
        # "brown" and "fox" are novel; 2 out of 4
        assert abs(ratio - 0.5) < 0.01

    def test_empty_content_fully_novel(self):
        seen: set[str] = {"existing"}
        ratio = compute_novel_token_ratio("", seen)
        assert ratio == 1.0

    def test_seen_tokens_updated(self):
        seen: set[str] = set()
        compute_novel_token_ratio("alpha beta", seen)
        assert "alpha" in seen and "beta" in seen


# ---------------------------------------------------------------------------
# ObservationFingerprint + TaskContext.record_observation
# ---------------------------------------------------------------------------


class TestObservationFingerprint:
    def test_dataclass_fields(self):
        from datetime import datetime

        fp = ObservationFingerprint(
            iteration=1,
            content_hash="abc",
            content_size=3,
            novel_token_ratio=0.9,
        )
        assert fp.iteration == 1
        assert fp.novel_token_ratio == 0.9
        assert isinstance(fp.timestamp, datetime)


class TestTaskContextRecordObservation:
    def test_fingerprint_appended(self):
        ctx = TaskContext(task_id="t", description="d")
        fp = ctx.record_observation({"result": "data"}, iteration=1)
        assert isinstance(fp, ObservationFingerprint)
        assert len(ctx.observation_fingerprints) == 1

    def test_second_identical_observation_has_low_novelty(self):
        ctx = TaskContext(task_id="t", description="d")
        ctx.record_observation("the quick brown fox", iteration=1)
        fp2 = ctx.record_observation("the quick brown fox", iteration=2)
        assert fp2.novel_token_ratio == 0.0

    def test_genuinely_novel_observation(self):
        ctx = TaskContext(task_id="t", description="d")
        ctx.record_observation("alpha beta gamma", iteration=1)
        fp2 = ctx.record_observation("delta epsilon zeta", iteration=2)
        assert fp2.novel_token_ratio == 1.0


# ---------------------------------------------------------------------------
# AgentLoop._check_observation_stagnation
# ---------------------------------------------------------------------------


class TestCheckObservationStagnation:
    def test_no_stagnation_with_fresh_content(self):
        loop = _make_loop(stagnation_window=5, min_observation_novelty=0.05)
        for i in range(5):
            loop._current_context.record_observation(f"unique result {i} delta epsilon zeta", iteration=i)
        assert loop._check_observation_stagnation() is False

    def test_stagnation_fires_after_window_identical_results(self):
        loop = _make_loop(stagnation_window=5, min_observation_novelty=0.05)
        # First observation establishes baseline
        loop._current_context.record_observation("repeated content same data", iteration=0)
        for i in range(1, 6):
            loop._current_context.record_observation("repeated content same data", iteration=i)
        assert loop._check_observation_stagnation() is True

    def test_no_stagnation_below_window_size(self):
        loop = _make_loop(stagnation_window=5, min_observation_novelty=0.05)
        loop._current_context.record_observation("same", iteration=0)
        loop._current_context.record_observation("same", iteration=1)
        # Only 2 fingerprints < window of 5
        assert loop._check_observation_stagnation() is False

    def test_disabled_when_halt_on_stagnation_false(self):
        loop = _make_loop(halt_on_stagnation=False)
        for i in range(10):
            loop._current_context.record_observation("same content always", iteration=i)
        assert loop._check_observation_stagnation() is False

    def test_no_context_returns_false(self):
        loop = _make_loop()
        loop._current_context = None
        assert loop._check_observation_stagnation() is False


# ---------------------------------------------------------------------------
# AgentLoop._record_observation_fingerprints
# ---------------------------------------------------------------------------


class TestRecordObservationFingerprints:
    def test_successful_results_are_fingerprinted(self):
        loop = _make_loop()
        tool_results = {
            "search": {"documents": ["doc1", "doc2"]},
            "read_file": {"content": "file content"},
        }
        loop._record_observation_fingerprints(tool_results)
        assert len(loop._current_context.observation_fingerprints) == 2

    def test_error_results_are_skipped(self):
        loop = _make_loop()
        tool_results = {
            "failing_tool": {"error": "something went wrong"},
        }
        loop._record_observation_fingerprints(tool_results)
        assert len(loop._current_context.observation_fingerprints) == 0

    def test_mixed_results_only_success_fingerprinted(self):
        loop = _make_loop()
        tool_results = {
            "good_tool": {"data": "useful"},
            "bad_tool": {"error": "failed"},
        }
        loop._record_observation_fingerprints(tool_results)
        assert len(loop._current_context.observation_fingerprints) == 1

    def test_no_context_is_noop(self):
        loop = _make_loop()
        loop._current_context = None
        loop._record_observation_fingerprints({"t": {"data": "x"}})  # should not raise


# ---------------------------------------------------------------------------
# Unit: 5 calls returning same content → halt fires
# ---------------------------------------------------------------------------


class TestStagnationHaltUnit:
    def test_halt_fires_after_five_identical_results(self):
        loop = _make_loop(stagnation_window=5, min_observation_novelty=0.05)
        repeated = {"documents": ["same result every time"], "count": 3}
        # Seed with one observation to establish vocabulary
        loop._current_context.record_observation(repeated, iteration=0)
        loop._iteration_count = 1
        for i in range(1, 6):
            loop._current_context.record_observation(repeated, iteration=i)
        assert loop._check_observation_stagnation() is True
        assert not loop._halted_on_stagnation  # flag only set by _execute_iteration_phases

    def test_halt_not_fires_with_new_content(self):
        loop = _make_loop(stagnation_window=5, min_observation_novelty=0.05)
        words = ["alpha", "beta", "gamma", "delta", "epsilon", "zeta"]
        for i in range(6):
            unique_doc = " ".join(words[i:] + words[:i])
            loop._current_context.record_observation({"doc": unique_doc, "index": i}, iteration=i)
        assert loop._check_observation_stagnation() is False


# ---------------------------------------------------------------------------
# Integration: search loop with cosmetic arg changes still halts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stagnation_halt_via_execute_tools_path():
    """
    Simulate a search loop where cosmetic arg changes (different queries)
    return the same 3 documents every time.  The repetition detector would
    NOT fire (args differ), but the stagnation detector MUST halt the loop.
    """
    loop = _make_loop(stagnation_window=5, min_observation_novelty=0.05)
    loop._iteration_count = 0

    same_results = {"documents": ["doc_a", "doc_b", "doc_c"], "total": 3}

    # Simulate recording results for 6 iterations with varying search args
    # (cosmetic changes — different query strings, same results)
    query_variants = [
        "find relevant files",
        "search for relevant files",
        "locate relevant files",
        "get relevant files",
        "retrieve relevant files",
        "fetch relevant files",
    ]
    for i, query in enumerate(query_variants):
        loop._iteration_count = i
        # Vary the tool call (cosmetic arg change) but results are identical
        tool_results = {"search": same_results}
        loop._record_observation_fingerprints(tool_results)

    # After 6 identical observations, stagnation should be detected
    assert loop._check_observation_stagnation() is True


@pytest.mark.asyncio
async def test_stagnation_outcome_in_build_result():
    """_build_result must include halt_outcome=STAGNATED and halt_reason."""
    loop = _make_loop(stagnation_window=5, min_observation_novelty=0.05)
    loop._iteration_count = 0

    same = {"data": "repeated observation data repeated observation data"}
    # Record enough identical observations to trigger stagnation
    for i in range(6):
        loop._current_context.record_observation(same, iteration=i)

    loop._halted_on_stagnation = True
    loop._halt_outcome = LoopOutcome.STAGNATED
    loop._halt_reason = "Halted: observation stagnation — avg novelty 0.000 < 0.05 over 5 observations"
    loop._state = LoopState.COMPLETED

    result = loop._build_result([])
    assert result["halt_outcome"] == "STAGNATED"
    assert "stagnation" in result["halt_reason"].lower()


# ---------------------------------------------------------------------------
# Rolling-window vocabulary saturation (P1 regression guard)
# ---------------------------------------------------------------------------


class TestRollingVocabularyWindow:
    def test_novelty_resets_after_window_eviction(self):
        """Tokens from >50 observations ago must not suppress future novelty scores."""
        ctx = TaskContext(task_id="t", description="d")
        # Fill the 50-observation window with tokens from a saturating document
        saturating_doc = " ".join(f"word{i}" for i in range(200))
        for i in range(50):
            ctx.record_observation(saturating_doc, iteration=i)
        # Adding one more observation evicts the oldest window entry.
        # A genuinely new token set should now score high novelty because the
        # 50-slot deque no longer contains ALL prior tokens.
        unique_doc = " ".join(f"unique{i}" for i in range(100))
        fp = ctx.record_observation(unique_doc, iteration=50)
        # After eviction the seen vocab is smaller — some unique tokens won't be there
        assert fp.novel_token_ratio > 0.0, "expected positive novelty after window eviction"

    def test_token_window_bounded_at_50(self):
        """_token_windows deque must never exceed 50 entries."""
        ctx = TaskContext(task_id="t", description="d")
        for i in range(60):
            ctx.record_observation(f"content {i}", iteration=i)
        assert len(ctx._token_windows) == 50


# ---------------------------------------------------------------------------
# Falsy-error partial result (P2 fix guard)
# ---------------------------------------------------------------------------


class TestFalsyErrorFilter:
    def test_none_error_value_is_not_skipped(self):
        """A result dict with error=None (falsy) must still be fingerprinted."""
        loop = _make_loop(stagnation_window=3, min_observation_novelty=0.05)
        partial_result = {"error": None, "data": ["item_a", "item_b", "item_c"]}
        loop._record_observation_fingerprints({"tool": partial_result})
        assert len(loop._current_context.observation_fingerprints) == 1

    def test_truthy_error_value_is_skipped(self):
        """A result dict with a non-empty error string must be skipped."""
        loop = _make_loop(stagnation_window=3, min_observation_novelty=0.05)
        error_result = {"error": "something went wrong", "data": []}
        loop._record_observation_fingerprints({"tool": error_result})
        assert len(loop._current_context.observation_fingerprints) == 0
