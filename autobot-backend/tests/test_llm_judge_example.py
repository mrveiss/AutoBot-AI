# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Example tests for the llm_judge fixture.

These tests demonstrate two usage patterns:

1. **String criteria** (plain-English description — judge picks dimensions):

       @pytest.mark.llm_judge
       async def test_rag_answer_relevance(llm_judge):
           await llm_judge.assert_llm(
               output=ANSWER,
               criteria="The answer must correctly identify Paris...",
               context=QUESTION,
           )

2. **Explicit JudgmentDimension list** (evaluate specific axes):

       @pytest.mark.llm_judge
       async def test_answer_accuracy(llm_judge):
           from judges import JudgmentDimension
           await llm_judge.assert_llm(
               output=ANSWER,
               criteria=[JudgmentDimension.ACCURACY, JudgmentDimension.COMPLETENESS],
           )

Running
-------
These tests SKIP by default.  To run them locally against a configured provider::

    AUTOBOT_LLM_JUDGE_TESTS=1 python -m pytest autobot-backend/tests/test_llm_judge_example.py -v

The unit tests in this file (``test_llm_judge_*_unit``) are NOT marked
``llm_judge`` and always run without a real LLM.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Fixtures are imported by pytest automatically via conftest.py plugin
# loading; we declare the import here only for the unit-test helpers below.
# ---------------------------------------------------------------------------

# Canned RAG scenario
_QUESTION = "What is the capital of France?"
_CORRECT_ANSWER = "The capital of France is Paris, which has served as the country's capital since the 10th century."
_IRRELEVANT_ANSWER = "Croissants are a popular French pastry often eaten at breakfast."

# ---------------------------------------------------------------------------
# Live LLM tests — skipped unless AUTOBOT_LLM_JUDGE_TESTS=1
# ---------------------------------------------------------------------------


@pytest.mark.llm_judge
async def test_rag_answer_relevance(llm_judge) -> None:
    """RAG answer about French capital should score high on relevance + accuracy."""
    await llm_judge.assert_llm(
        output=_CORRECT_ANSWER,
        criteria="The answer must correctly identify Paris as the capital of France and be relevant to the question.",
        context=_QUESTION,
        min_score=0.7,
    )


@pytest.mark.llm_judge
async def test_rag_answer_explicit_dimensions(llm_judge) -> None:
    """Same scenario using explicit JudgmentDimension list instead of a string."""
    from judges import JudgmentDimension

    await llm_judge.assert_llm(
        output=_CORRECT_ANSWER,
        criteria=[JudgmentDimension.RELEVANCE, JudgmentDimension.ACCURACY],
        context=_QUESTION,
        min_score=0.7,
    )


@pytest.mark.llm_judge
async def test_irrelevant_answer_fails(llm_judge) -> None:
    """An irrelevant answer should be judged poorly and raise AssertionError."""
    with pytest.raises(AssertionError, match="LLM judge score"):
        await llm_judge.assert_llm(
            output=_IRRELEVANT_ANSWER,
            criteria="The answer must directly answer what the capital of France is.",
            context=_QUESTION,
            min_score=0.9,  # high bar — irrelevant answer should fail
        )


# ---------------------------------------------------------------------------
# Unit tests — always run, no real LLM required
# ---------------------------------------------------------------------------


def _make_judgment(overall_score: float, criterion_scores: list | None = None):
    """Build a minimal JudgmentResult mock for unit tests."""
    from judges import JudgmentConfidence, JudgmentResult

    return JudgmentResult(
        subject_id="test-subject",
        judge_type="pytest_quality_judge",
        timestamp=MagicMock(),
        overall_score=overall_score,
        recommendation="APPROVE" if overall_score >= 0.7 else "REJECT",
        confidence=JudgmentConfidence.HIGH,
        criterion_scores=criterion_scores or [],
        reasoning="Unit test stub reasoning.",
        alternatives_considered=[],
        improvement_suggestions=[],
        context_used={},
        processing_time_ms=0.0,
        llm_model_used="stub",
    )


@pytest.mark.asyncio
async def test_llm_judge_wrapper_passes_on_high_score() -> None:
    """_LLMJudgeWrapper.assert_llm must not raise when score >= min_score."""
    from tests.helpers.llm_judge_fixture import _LLMJudgeWrapper

    mock_judge = MagicMock()
    mock_judge.make_judgment = AsyncMock(return_value=_make_judgment(0.85))
    wrapper = _LLMJudgeWrapper(mock_judge)

    # Should complete without exception.
    await wrapper.assert_llm(output="Paris is the capital.", criteria="Correct answer.")


@pytest.mark.asyncio
async def test_llm_judge_wrapper_raises_on_low_score() -> None:
    """_LLMJudgeWrapper.assert_llm must raise AssertionError when score < min_score."""
    from tests.helpers.llm_judge_fixture import _LLMJudgeWrapper

    mock_judge = MagicMock()
    mock_judge.make_judgment = AsyncMock(return_value=_make_judgment(0.4))
    wrapper = _LLMJudgeWrapper(mock_judge)

    with pytest.raises(AssertionError, match="LLM judge score"):
        await wrapper.assert_llm(output="Irrelevant text.", criteria="Must be relevant.", min_score=0.7)


@pytest.mark.asyncio
async def test_llm_judge_wrapper_includes_reasoning_in_error() -> None:
    """Failure message must include per-criterion reasoning for debuggability."""
    from judges import CriterionScore, JudgmentConfidence, JudgmentDimension

    from tests.helpers.llm_judge_fixture import _LLMJudgeWrapper

    criterion = CriterionScore(
        dimension=JudgmentDimension.RELEVANCE,
        score=0.3,
        confidence=JudgmentConfidence.LOW,
        reasoning="Response does not address the question.",
        evidence=[],
    )
    mock_judge = MagicMock()
    mock_judge.make_judgment = AsyncMock(return_value=_make_judgment(0.3, [criterion]))
    wrapper = _LLMJudgeWrapper(mock_judge)

    with pytest.raises(AssertionError) as exc_info:
        await wrapper.assert_llm(output="Off-topic text.", criteria="Must be relevant.", min_score=0.7)

    error_text = str(exc_info.value)
    assert "relevance" in error_text.lower()
    assert "does not address" in error_text


def test_is_judge_tests_enabled_off_by_default() -> None:
    """Gate env var must default to disabled (CI-safe)."""
    import os

    from tests.helpers.llm_judge_fixture import _is_judge_tests_enabled

    env_backup = os.environ.pop("AUTOBOT_LLM_JUDGE_TESTS", None)
    try:
        assert not _is_judge_tests_enabled()
    finally:
        if env_backup is not None:
            os.environ["AUTOBOT_LLM_JUDGE_TESTS"] = env_backup


def test_is_judge_tests_enabled_when_set(monkeypatch) -> None:
    """Gate returns True when env var is '1'."""
    from tests.helpers.llm_judge_fixture import _is_judge_tests_enabled

    monkeypatch.setenv("AUTOBOT_LLM_JUDGE_TESTS", "1")
    assert _is_judge_tests_enabled()


def test_provider_configured_no_env(monkeypatch) -> None:
    """Provider check returns False when no provider env vars are set."""
    from tests.helpers.llm_judge_fixture import _provider_configured

    for key in ("AUTOBOT_LLM_PROVIDER", "AUTOBOT_OLLAMA_ENDPOINT", "AUTOBOT_OPENAI_API_KEY", "AUTOBOT_ANTHROPIC_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    assert not _provider_configured()


def test_provider_configured_with_openai_key(monkeypatch) -> None:
    """Provider check returns True when AUTOBOT_OPENAI_API_KEY is set."""
    from tests.helpers.llm_judge_fixture import _provider_configured

    for key in ("AUTOBOT_LLM_PROVIDER", "AUTOBOT_OLLAMA_ENDPOINT", "AUTOBOT_ANTHROPIC_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("AUTOBOT_OPENAI_API_KEY", "sk-test")
    assert _provider_configured()
