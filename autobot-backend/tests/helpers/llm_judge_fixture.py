# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""pytest fixture: llm_judge

Thin integration between the existing judges framework and pytest.

Usage
-----
In any test::

    @pytest.mark.llm_judge
    async def test_answer_quality(llm_judge):
        await llm_judge.assert_llm(
            output="Paris is the capital of France.",
            criteria="The answer must be factually correct and relevant.",
            min_score=0.8,
        )

The fixture auto-skips when the opt-in env var ``AUTOBOT_LLM_JUDGE_TESTS=1``
is absent OR when no LLM provider is reachable, so it is **never** a hard CI
dependency.

All judges imports happen **inside** the fixture function so that collection
stays lightweight (this file is imported only via fixture lookup, not at
collection time).
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Union

import pytest

if TYPE_CHECKING:
    from judges import JudgmentDimension  # typing-time only — not imported at load

logger = logging.getLogger(__name__)

# Environment opt-in gate — CI sets this to nothing; local dev sets it to "1".
_JUDGE_TESTS_ENV = "AUTOBOT_LLM_JUDGE_TESTS"

# Configurable minimum score for the default threshold (env constant pattern).
_DEFAULT_MIN_SCORE = float(os.environ.get("AUTOBOT_LLM_JUDGE_MIN_SCORE", "0.7"))


def _is_judge_tests_enabled() -> bool:
    """Return True only when the opt-in env var is present and set to '1'."""
    return os.environ.get(_JUDGE_TESTS_ENV, "").strip() == "1"


def _provider_configured() -> bool:
    """Return True when a non-empty LLM provider endpoint/key appears to be set.

    Checks the SSOT config without importing heavy deps.  A provider is
    considered configured when *any* of the following is non-empty/non-default:
    - AUTOBOT_OLLAMA_ENDPOINT overrides the default value
    - AUTOBOT_OPENAI_API_KEY is non-empty
    - AUTOBOT_ANTHROPIC_API_KEY is non-empty
    - AUTOBOT_LLM_PROVIDER is set to anything other than the bare default

    This is a cheap heuristic — no socket connection is opened.
    """
    provider = os.environ.get("AUTOBOT_LLM_PROVIDER", "")
    ollama_ep = os.environ.get("AUTOBOT_OLLAMA_ENDPOINT", "")
    openai_key = os.environ.get("AUTOBOT_OPENAI_API_KEY", "")
    anthropic_key = os.environ.get("AUTOBOT_ANTHROPIC_API_KEY", "")
    # Any explicit configuration counts.
    return bool(provider or ollama_ep or openai_key or anthropic_key)


class _LLMJudgeWrapper:
    """Thin wrapper that exposes ``assert_llm`` for use in tests.

    Instantiation is deferred to the fixture so heavy deps are never imported
    at module/collection time.
    """

    def __init__(self, judge) -> None:
        self._judge = judge

    async def assert_llm(
        self,
        output: str,
        criteria: Union[str, list],
        *,
        min_score: float = _DEFAULT_MIN_SCORE,
        context: str = "",
    ) -> None:
        """Assert that *output* meets *criteria* at the given minimum quality score.

        Parameters
        ----------
        output:
            The LLM-generated text to evaluate.
        criteria:
            Either a plain-English string describing what the output must satisfy
            or a list of ``JudgmentDimension`` enum values to evaluate across.
        min_score:
            Minimum acceptable overall score (0–1).  Defaults to
            ``AUTOBOT_LLM_JUDGE_MIN_SCORE`` env var or 0.7.
        context:
            Optional background text provided to the judge (e.g. the question
            or retrieved documents for a RAG scenario).

        Raises
        ------
        AssertionError
            When the judge's overall score falls below *min_score*.  The error
            message includes per-criterion reasoning from the judgment.
        """
        # Late import — keeps collection cost zero.
        from judges import JudgmentDimension as _Dim

        if isinstance(criteria, str):
            dimensions = [_Dim.RELEVANCE, _Dim.ACCURACY, _Dim.QUALITY]
            judge_context = {"criteria_description": criteria, "context": context}
        else:
            dimensions = criteria
            judge_context = {"context": context}

        result = await self._judge.make_judgment(
            subject=output,
            criteria=dimensions,
            context=judge_context,
        )

        if result.overall_score < min_score:
            lines = [
                f"LLM judge score {result.overall_score:.3f} < required {min_score:.3f}",
                f"Recommendation: {result.recommendation}",
                f"Reasoning: {result.reasoning}",
            ]
            for cs in result.criterion_scores:
                lines.append(
                    f"  [{cs.dimension.value}] score={cs.score:.3f} — {cs.reasoning}"
                )
            raise AssertionError("\n".join(lines))


@pytest.fixture
async def llm_judge(request):
    """pytest fixture: provides ``_LLMJudgeWrapper`` for LLM-quality assertions.

    Auto-skips when:
    - ``AUTOBOT_LLM_JUDGE_TESTS`` != "1"  (opt-in gate)
    - No LLM provider environment variables are present

    The fixture is async so callers can ``await llm_judge.assert_llm(...)``
    in async test functions directly.
    """
    if not _is_judge_tests_enabled():
        pytest.skip(
            f"LLM judge tests disabled — set {_JUDGE_TESTS_ENV}=1 to enable"
        )

    if not _provider_configured():
        pytest.skip(
            "LLM judge tests skipped — no provider configured "
            "(set AUTOBOT_OLLAMA_ENDPOINT, AUTOBOT_OPENAI_API_KEY, etc.)"
        )

    # Late import — judges/__init__.py imports llm_shared and autobot_shared
    # chains that must NOT run at collection time.
    from judges import BaseLLMJudge

    judge = BaseLLMJudge(judge_type="pytest_quality_judge")
    yield _LLMJudgeWrapper(judge)
