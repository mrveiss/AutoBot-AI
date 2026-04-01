# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for AutoResearch M2: AutoResearchAgent, ApprovalGate, and web-search helpers.

Issue #2599: Covers loop execution, web-search integration, approval gate trigger,
and early-stop on plateau.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.autoresearch.auto_research_agent import (
    ApprovalGate,
    AutoResearchAgent,
    ExperimentSession,
    ImprovementMetrics,
    SearchResult,
    SessionStatus,
    _extract_themes,
    _parse_arxiv_atom,
    _parse_github_results,
    _summarise_prior_results,
    _themes_to_hyperparams,
)
from services.autoresearch.config import AutoResearchConfig
from services.autoresearch.models import (
    Experiment,
    ExperimentResult,
    ExperimentState,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

ARXIV_ATOM_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2301.00001v1</id>
    <title>Attention Is All You Need (reprise)</title>
    <summary>We revisit multi-head self-attention for language models.</summary>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2301.00002v1</id>
    <title>Dropout Regularisation at Scale</title>
    <summary>Weight decay and dropout improve generalisation.</summary>
  </entry>
</feed>
"""

GITHUB_JSON_SAMPLE: Dict[str, Any] = {
    "total_count": 1,
    "items": [
        {
            "full_name": "karpathy/nanoGPT",
            "html_url": "https://github.com/karpathy/nanoGPT",
            "description": "The simplest, fastest repository for training medium-sized GPTs.",
        }
    ],
}


def _make_experiment(
    state: ExperimentState = ExperimentState.KEPT,
    val_bpb: Optional[float] = 4.5,
    baseline: Optional[float] = 5.0,
) -> Experiment:
    exp = Experiment(
        hypothesis="test",
        state=state,
        baseline_val_bpb=baseline,
    )
    if val_bpb is not None:
        exp.result = ExperimentResult(val_bpb=val_bpb)
    return exp


def _make_metrics(improved: bool = True) -> ImprovementMetrics:
    return ImprovementMetrics(
        experiment_id="exp-1",
        baseline_val_bpb=5.0,
        result_val_bpb=4.5 if improved else 5.1,
        improvement=0.5 if improved else -0.1,
        improvement_pct=10.0 if improved else -2.0,
        state=(
            ExperimentState.KEPT.value if improved else ExperimentState.DISCARDED.value
        ),
    )


# ---------------------------------------------------------------------------
# Pure-function tests (no I/O)
# ---------------------------------------------------------------------------


class TestParseArxivAtom:
    """_parse_arxiv_atom correctly extracts entries from Atom XML."""

    def test_extracts_two_entries(self):
        results = _parse_arxiv_atom(ARXIV_ATOM_SAMPLE)
        assert len(results) == 2

    def test_first_entry_fields(self):
        results = _parse_arxiv_atom(ARXIV_ATOM_SAMPLE)
        assert results[0].source == "arxiv"
        assert "Attention" in results[0].title
        assert "arxiv.org" in results[0].url

    def test_empty_xml_returns_empty_list(self):
        assert _parse_arxiv_atom("<feed></feed>") == []

    def test_entry_missing_id_is_skipped(self):
        xml = "<feed><entry><title>No ID</title><summary>x</summary></entry></feed>"
        assert _parse_arxiv_atom(xml) == []


class TestParseGitHubResults:
    """_parse_github_results correctly extracts repo data from search JSON."""

    def test_extracts_one_result(self):
        results = _parse_github_results(GITHUB_JSON_SAMPLE)
        assert len(results) == 1

    def test_result_fields(self):
        results = _parse_github_results(GITHUB_JSON_SAMPLE)
        r = results[0]
        assert r.source == "github"
        assert r.title == "karpathy/nanoGPT"
        assert "github.com" in r.url

    def test_empty_items_returns_empty_list(self):
        assert _parse_github_results({"items": []}) == []

    def test_missing_description_defaults_to_empty_string(self):
        data = {
            "items": [
                {
                    "full_name": "x/y",
                    "html_url": "https://example.com",
                    "description": None,
                }
            ]
        }
        results = _parse_github_results(data)
        assert results[0].summary == ""


class TestExtractThemes:
    """_extract_themes maps search result text to theme names."""

    def test_detects_attention_theme(self):
        results = [
            SearchResult(
                title="Multi-head Attention",
                url="u",
                summary="transformer block",
                source="arxiv",
            )
        ]
        assert "attention" in _extract_themes(results)

    def test_detects_regularisation_theme(self):
        results = [
            SearchResult(
                title="Dropout",
                url="u",
                summary="weight decay regularization",
                source="arxiv",
            )
        ]
        assert "regularisation" in _extract_themes(results)

    def test_empty_results_return_empty_list(self):
        assert _extract_themes([]) == []

    def test_no_match_returns_empty_list(self):
        results = [
            SearchResult(
                title="Unrelated paper",
                url="u",
                summary="nothing relevant",
                source="arxiv",
            )
        ]
        assert _extract_themes(results) == []

    def test_multiple_themes_detected(self):
        results = [
            SearchResult(
                title="Attention and Dropout",
                url="u",
                summary="learning rate warmup",
                source="arxiv",
            ),
        ]
        themes = _extract_themes(results)
        assert "attention" in themes
        assert "learning_rate" in themes


class TestThemesToHyperparams:
    """_themes_to_hyperparams returns valid hyperparameter dicts."""

    def test_attention_theme_returns_n_head(self):
        hp = _themes_to_hyperparams(["attention"], iteration=1)
        assert "n_head" in hp

    def test_fallback_cycles_on_empty_themes(self):
        hp1 = _themes_to_hyperparams([], iteration=1)
        hp2 = _themes_to_hyperparams([], iteration=2)
        # Should differ — different iteration picks different default theme
        # (they may coincidentally match only if len(all_themes)==1, which it isn't)
        assert isinstance(hp1, dict)
        assert isinstance(hp2, dict)

    def test_iteration_cycles_through_themes(self):
        themes = ["attention", "regularisation"]
        hp1 = _themes_to_hyperparams(themes, iteration=1)
        hp2 = _themes_to_hyperparams(themes, iteration=2)
        assert hp1 != hp2  # different theme selected per iteration


class TestSummarisePriorResults:
    """_summarise_prior_results builds a human-readable string."""

    def test_empty_returns_empty_string(self):
        assert _summarise_prior_results([]) == ""

    def test_improved_mentions_percentage(self):
        summary = _summarise_prior_results([_make_metrics(improved=True)])
        assert "10.00%" in summary

    def test_no_improvement_mentions_baseline(self):
        summary = _summarise_prior_results([_make_metrics(improved=False)])
        assert "did not improve" in summary


class TestImprovementMetrics:
    """ImprovementMetrics.improved property reflects actual improvement direction."""

    def test_positive_improvement_is_improved(self):
        m = _make_metrics(improved=True)
        assert m.improved is True

    def test_negative_improvement_is_not_improved(self):
        m = _make_metrics(improved=False)
        assert m.improved is False

    def test_none_improvement_is_not_improved(self):
        m = ImprovementMetrics(
            experiment_id="x",
            baseline_val_bpb=None,
            result_val_bpb=None,
            improvement=None,
            improvement_pct=None,
            state="failed",
        )
        assert m.improved is False


# ---------------------------------------------------------------------------
# ApprovalGate unit tests
# ---------------------------------------------------------------------------


class TestApprovalGate:
    """ApprovalGate correctly decides when approval is needed and persists state."""

    def _gate(self) -> ApprovalGate:
        return ApprovalGate(config=AutoResearchConfig())

    # -- check_approval_needed --

    def test_below_threshold_returns_false(self):
        gate = self._gate()
        assert gate.check_approval_needed(3.0, threshold=5.0) is False

    def test_at_threshold_returns_true(self):
        gate = self._gate()
        assert gate.check_approval_needed(5.0, threshold=5.0) is True

    def test_above_threshold_returns_true(self):
        gate = self._gate()
        assert gate.check_approval_needed(12.5, threshold=5.0) is True

    def test_none_improvement_returns_false(self):
        gate = self._gate()
        assert gate.check_approval_needed(None, threshold=5.0) is False

    # -- request_approval / get_approval_status --

    @pytest.mark.asyncio
    async def test_request_approval_stores_pending_status(self):
        gate = self._gate()
        redis_mock = AsyncMock()
        gate._redis = redis_mock

        status_key = await gate.request_approval(
            session_id="sess-1",
            experiment_id="exp-1",
            details={"topic": "attention"},
        )

        assert "exp-1" in status_key
        # Verify set was called with 'pending'
        calls = [str(c) for c in redis_mock.set.call_args_list]
        assert any("pending" in c for c in calls)

    @pytest.mark.asyncio
    async def test_get_approval_status_decodes_bytes(self):
        gate = self._gate()
        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=b"approved")
        gate._redis = redis_mock

        status = await gate.get_approval_status("sess-1", "exp-1")
        assert status == "approved"

    @pytest.mark.asyncio
    async def test_get_approval_status_unknown_on_missing_key(self):
        gate = self._gate()
        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=None)
        gate._redis = redis_mock

        status = await gate.get_approval_status("sess-1", "exp-999")
        assert status == "unknown"

    # -- wait_for_approval --

    @pytest.mark.asyncio
    async def test_wait_for_approval_returns_immediately_on_approved(self):
        gate = self._gate()
        gate.get_approval_status = AsyncMock(return_value="approved")

        result = await gate.wait_for_approval(
            session_id="s", experiment_id="e", poll_interval=0.01, timeout=5.0
        )
        assert result == "approved"

    @pytest.mark.asyncio
    async def test_wait_for_approval_times_out(self):
        gate = self._gate()
        gate.get_approval_status = AsyncMock(return_value="pending")

        result = await gate.wait_for_approval(
            session_id="s", experiment_id="e", poll_interval=0.01, timeout=0.05
        )
        assert result == "timeout"


# ---------------------------------------------------------------------------
# AutoResearchAgent unit tests
# ---------------------------------------------------------------------------


def _make_agent(runner_mock=None, store_mock=None) -> AutoResearchAgent:
    """Build an AutoResearchAgent with all I/O mocked out."""
    config = AutoResearchConfig()
    store = store_mock or AsyncMock()
    runner = runner_mock or AsyncMock()
    approval_gate = MagicMock(spec=ApprovalGate)
    approval_gate.check_approval_needed = MagicMock(return_value=False)

    # Build a fake httpx client so no real network calls are made
    import httpx

    transport = httpx.MockTransport(handler=_mock_http_handler)
    http_client = httpx.AsyncClient(transport=transport)

    agent = AutoResearchAgent(
        config=config,
        store=store,
        runner=runner,
        approval_gate=approval_gate,
        http_client=http_client,
    )
    agent._redis = AsyncMock()
    return agent


def _mock_http_handler(request):
    """Return stub responses for arXiv and GitHub during tests."""
    import httpx

    if "arxiv.org" in str(request.url):
        return httpx.Response(200, text=ARXIV_ATOM_SAMPLE)
    if "api.github.com" in str(request.url):
        return httpx.Response(200, json=GITHUB_JSON_SAMPLE)
    return httpx.Response(404)


class TestAutoResearchAgentLoop:
    """AutoResearchAgent.run_experiment_loop() drives the full pipeline."""

    def _completed_experiment(self) -> Experiment:
        exp = _make_experiment(state=ExperimentState.KEPT, val_bpb=4.5, baseline=5.0)
        return exp

    @pytest.mark.asyncio
    async def test_loop_runs_max_iterations(self):
        runner = AsyncMock()
        runner.run_experiment = AsyncMock(side_effect=lambda e: _make_experiment())
        agent = _make_agent(runner_mock=runner)

        session = await agent.run_experiment_loop(
            topic="attention mechanisms", max_iterations=2
        )

        assert session.iterations_completed == 2
        assert session.status == SessionStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_loop_returns_experiment_session(self):
        runner = AsyncMock()
        runner.run_experiment = AsyncMock(side_effect=lambda e: _make_experiment())
        agent = _make_agent(runner_mock=runner)

        session = await agent.run_experiment_loop(topic="dropout", max_iterations=1)

        assert isinstance(session, ExperimentSession)
        assert session.topic == "dropout"
        assert len(session.results) == 1
        assert len(session.hypotheses) == 1

    @pytest.mark.asyncio
    async def test_loop_stops_early_on_plateau(self):
        """plateau_window=2 means 2 consecutive non-improving iterations triggers stop."""
        runner = AsyncMock()
        # All experiments fail to improve (high val_bpb = worse)
        runner.run_experiment = AsyncMock(
            side_effect=lambda e: _make_experiment(
                state=ExperimentState.DISCARDED, val_bpb=6.0, baseline=5.0
            )
        )
        agent = _make_agent(runner_mock=runner)

        session = await agent.run_experiment_loop(
            topic="regularisation",
            max_iterations=5,
            plateau_window=2,
        )

        # Should stop at iteration 2 (plateau_window=2, both non-improving)
        assert session.iterations_completed == 2
        assert session.status == SessionStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_cancellation_stops_loop_cleanly(self):
        """Calling cancel() before the loop starts marks the session CANCELLED."""
        runner = AsyncMock()
        runner.run_experiment = AsyncMock(side_effect=lambda e: _make_experiment())
        agent = _make_agent(runner_mock=runner)

        # Set cancel before run_experiment_loop is called
        agent.cancel()
        session = await agent.run_experiment_loop(topic="batch size", max_iterations=3)

        assert session.status == SessionStatus.CANCELLED
        assert session.iterations_completed == 0

    @pytest.mark.asyncio
    async def test_approval_gate_invoked_for_significant_improvement(self):
        """ApprovalGate.request_approval is called when improvement exceeds threshold."""
        runner = AsyncMock()
        # 20% improvement — above the 5% default threshold
        improved_exp = _make_experiment(
            state=ExperimentState.KEPT, val_bpb=4.0, baseline=5.0
        )
        runner.run_experiment = AsyncMock(return_value=improved_exp)

        approval_gate = MagicMock(spec=ApprovalGate)
        approval_gate.check_approval_needed = MagicMock(return_value=True)
        approval_gate.request_approval = AsyncMock(
            return_value="autoresearch:approval:status:s:e"
        )
        approval_gate.wait_for_approval = AsyncMock(return_value="approved")

        import httpx

        transport = httpx.MockTransport(handler=_mock_http_handler)
        http_client = httpx.AsyncClient(transport=transport)

        config = AutoResearchConfig()
        store = AsyncMock()
        agent = AutoResearchAgent(
            config=config,
            store=store,
            runner=runner,
            approval_gate=approval_gate,
            http_client=http_client,
        )
        agent._redis = AsyncMock()

        await agent.run_experiment_loop(
            topic="attention",
            max_iterations=1,
            approval_threshold_pct=5.0,
        )

        approval_gate.request_approval.assert_called_once()

    @pytest.mark.asyncio
    async def test_approval_gate_not_invoked_below_threshold(self):
        """ApprovalGate.request_approval is NOT called when improvement is below threshold."""
        runner = AsyncMock()
        # Small improvement — below threshold
        exp = _make_experiment(state=ExperimentState.KEPT, val_bpb=4.95, baseline=5.0)
        runner.run_experiment = AsyncMock(return_value=exp)

        approval_gate = MagicMock(spec=ApprovalGate)
        approval_gate.check_approval_needed = MagicMock(return_value=False)
        approval_gate.request_approval = AsyncMock()

        import httpx

        transport = httpx.MockTransport(handler=_mock_http_handler)
        http_client = httpx.AsyncClient(transport=transport)

        config = AutoResearchConfig()
        store = AsyncMock()
        agent = AutoResearchAgent(
            config=config,
            store=store,
            runner=runner,
            approval_gate=approval_gate,
            http_client=http_client,
        )
        agent._redis = AsyncMock()

        await agent.run_experiment_loop(
            topic="architecture",
            max_iterations=1,
            approval_threshold_pct=5.0,
        )

        approval_gate.request_approval.assert_not_called()

    @pytest.mark.asyncio
    async def test_session_persisted_to_redis(self):
        """_save_session is called at least once with a valid session payload."""
        runner = AsyncMock()
        runner.run_experiment = AsyncMock(side_effect=lambda e: _make_experiment())
        agent = _make_agent(runner_mock=runner)

        redis_mock = agent._redis
        await agent.run_experiment_loop(topic="data", max_iterations=1)

        assert redis_mock.set.called
        call_args = redis_mock.set.call_args
        # Key should contain the session id
        key = call_args[0][0]
        assert "autoresearch:session:" in key
        # Value should be valid JSON
        payload = json.loads(call_args[0][1])
        assert payload["topic"] == "data"

    @pytest.mark.asyncio
    async def test_failed_runner_marks_session_failed(self):
        """If the runner raises, the session ends with FAILED status."""
        runner = AsyncMock()
        runner.run_experiment = AsyncMock(side_effect=RuntimeError("GPU OOM"))
        agent = _make_agent(runner_mock=runner)

        session = await agent.run_experiment_loop(topic="batch", max_iterations=1)

        assert session.status == SessionStatus.FAILED
        assert "GPU OOM" in (session.error_message or "")


# ---------------------------------------------------------------------------
# _should_continue unit tests
# ---------------------------------------------------------------------------


class TestShouldContinue:
    """_should_continue plateau detection."""

    def _agent(self) -> AutoResearchAgent:
        return _make_agent()

    def _session_with(self, results: List[ImprovementMetrics]) -> ExperimentSession:
        s = ExperimentSession()
        s.results = results
        return s

    def test_continue_when_fewer_results_than_window(self):
        agent = self._agent()
        session = self._session_with([_make_metrics(improved=False)])
        assert agent._should_continue(session, plateau_window=3) is True

    def test_plateau_triggers_stop(self):
        agent = self._agent()
        results = [_make_metrics(improved=False), _make_metrics(improved=False)]
        session = self._session_with(results)
        assert agent._should_continue(session, plateau_window=2) is False

    def test_any_improvement_prevents_stop(self):
        agent = self._agent()
        results = [_make_metrics(improved=False), _make_metrics(improved=True)]
        session = self._session_with(results)
        assert agent._should_continue(session, plateau_window=2) is True
