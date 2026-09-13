# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A summary that drops a late fact scores lower than one that keeps it (#16110, criterion 3).

``recursive_summarizer_eval_coverage_test.py`` proves a fact past the old
200-character boundary reaches the evaluator's excerpt: a claim about the
evaluator's input. The criterion is about its output, that dropping the fact
actually moves the score. These tests go through ``_summarize_with_refinement``
with the model stubbed, at all three levels, and grade with a stand-in that can
only judge the facts its query shows it. That is exactly the defect: under
``text[:200]`` the late fact never reached the query, so dropping it cost nothing.
"""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from knowledge.pipeline.cognifiers.recursive_summarizer import RecursiveSummarizer

_HEAD_FACT = "HEAD-FACT-ALPHA"
_TAIL_FACT = "TAIL-FACT-OMEGA"


class _FactCheckingEvaluator:
    """Grades a summary by the share of facts it keeps, among those its query shows.

    A stand-in for the model grader, which can only judge what the query hands it.
    """

    def __init__(self) -> None:
        self.scores: list[float] = []
        self.queries: list[str] = []

    async def evaluate(self, query: str, response: str, iteration: int):
        seen = [fact for fact in (_HEAD_FACT, _TAIL_FACT) if fact in query]
        kept = [fact for fact in seen if fact in response]
        score = len(kept) / len(seen) if seen else 0.0
        self.queries.append(query)
        self.scores.append(score)
        # The real result's shape: a sub-threshold score is followed by a read of the hint.
        return SimpleNamespace(quality_score=score, refinement_hint="keep every fact", critique="")


def _source(length: int) -> str:
    """The head fact first and the tail fact last, far past the old 200-character window."""
    filler = "lorem ipsum dolor sit amet " * (length // 27 + 1)
    return f"{_HEAD_FACT} {filler[:length]} {_TAIL_FACT}"


async def _score(text: str, summary: str, level: str) -> tuple[float, str]:
    """Run one refinement round with the model stubbed to return *summary*; return (score, eval query)."""
    summarizer = object.__new__(RecursiveSummarizer)
    summarizer.max_refinement_depth = 0
    summarizer.rlm_config = SimpleNamespace(quality_threshold=0.7)
    summarizer.evaluator = _FactCheckingEvaluator()

    async def _generate(_prompt: str) -> dict:
        return {"summary": summary, "key_topics": [], "key_entities": []}

    summarizer._generate_and_parse = _generate
    result = await summarizer._summarize_with_refinement(text, [uuid4()], uuid4(), level, 50, {})

    assert result is not None and result.content == summary
    return summarizer.evaluator.scores[0], summarizer.evaluator.queries[0]


@pytest.mark.asyncio
@pytest.mark.parametrize(("level", "length"), [("chunk", 400), ("section", 2500), ("document", 20000)])
async def test_a_dropped_late_fact_lowers_the_score(level: str, length: int) -> None:
    """Chunk and section sources fit the evaluator's budget; the document one is sampled."""
    text = _source(length)

    kept, query = await _score(text, f"{_HEAD_FACT} and {_TAIL_FACT}", level)
    dropped, _ = await _score(text, f"{_HEAD_FACT} only", level)

    assert _TAIL_FACT in query, f"{level}: the late fact never reached the evaluator's view of the source"
    assert dropped < kept, f"{level}: dropping the late fact did not cost the summary anything"
