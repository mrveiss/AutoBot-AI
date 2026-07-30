# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Planner (#12624, design §4.3) — LLM sub-question decomposition, branch
pruning, and skip-known filtering for ``ResearchOrchestrator``.

Reuses the shared LLM service seam (same call pattern as ``extractor.py`` /
``synthesizer.py``) and the shared fence-tolerant JSON parser
(``llm_shared.json_utils``) rather than inventing new prompt-parsing.
Saturation/plateau stop lives in ``services.plateau_detector`` (extracted
from ``AutoResearchAgent``, not duplicated) and is driven by the orchestrator
round loop, not this module.

Termination guarantee (#12624): every function here is a single bounded call
that never raises and never blocks the caller's own round-cap / budget
enforcement — a malformed or adversarial LLM response degrades to a safe
fallback, it never grows the search space.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config
from llm_shared.json_utils import extract_json_object

logger = get_logger(__name__)

_DECOMPOSE_SYSTEM_PROMPT = (
    "You break a research question into focused sub-questions that, if "
    "answered, would materially help answer the original question. For each "
    "sub-question, assign expected_value 0.0-1.0 reflecting how much it "
    "narrows the answer (1.0 = highly valuable, 0.0 = not worth pursuing). "
    "Respond with ONLY a JSON object: "
    '{"sub_questions": [{"text": str, "expected_value": float}, ...]}. '
    "If the question needs no further decomposition, return exactly one "
    "sub-question equal to the original question with expected_value 1.0."
)


@dataclass
class SubQuestion:
    """One candidate branch the Planner may pursue this round."""

    text: str
    expected_value: float


@dataclass
class SkippedSubQuestion:
    """Audit record for a sub-question skipped as already-known (design: auditable skips)."""

    text: str
    fact_id: str
    confidence: float


def _build_decompose_messages(question: str, max_branches: int) -> List[Dict[str, str]]:
    """Build the chat messages for one decomposition call."""
    user_content = f"Original question: {question}\nMaximum sub-questions: {max_branches}"
    return [
        {"role": "system", "content": _DECOMPOSE_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def _to_subquestion(raw: Dict[str, Any]) -> SubQuestion | None:
    """Convert one raw sub-question dict to a ``SubQuestion``, or None if malformed."""
    text = str(raw.get("text", "")).strip()
    if not text:
        return None
    try:
        value = float(raw.get("expected_value", 0.0))
    except (TypeError, ValueError):
        value = 0.0
    return SubQuestion(text=text, expected_value=max(0.0, min(1.0, value)))


def _parse_subquestions(raw_content: str, fallback_text: str) -> List[SubQuestion]:
    """Parse the LLM's JSON response; a malformed/empty response degrades to the original question.

    This is the pathological-LLM-output guard (#12624): "nonsense" output can
    never expand the branch count beyond one — it can only ever fall back to
    exactly the original question.
    """
    try:
        payload = extract_json_object(raw_content)
    except json.JSONDecodeError:
        logger.warning("planner.decompose_question: LLM response was not valid JSON; using fallback question")
        return [SubQuestion(text=fallback_text, expected_value=1.0)]
    raw_list = payload.get("sub_questions", [])
    if not isinstance(raw_list, list):
        return [SubQuestion(text=fallback_text, expected_value=1.0)]
    subs = [s for s in (_to_subquestion(raw) for raw in raw_list) if s is not None]
    return subs or [SubQuestion(text=fallback_text, expected_value=1.0)]


async def decompose_question(llm_service: Any, question: str) -> List[SubQuestion]:
    """Decompose *question* into sub-questions, capped at the configured branch limit.

    Never raises and never returns an empty list — the round cap (not this
    function) is the loop's sole termination guarantee (design: "budget
    enforced by the loop's own control flow").
    """
    max_branches = config.research_planner_max_subquestions_per_round
    response = await llm_service.chat(
        messages=_build_decompose_messages(question, max_branches),
        temperature=0.0,
        timeout=int(config.research_planner_decompose_timeout_seconds),
    )
    if response.error:
        logger.warning("planner.decompose_question: LLM call failed: %s", response.error)
        return [SubQuestion(text=question, expected_value=1.0)]
    return _parse_subquestions(response.content, fallback_text=question)[:max_branches]


def prune_low_value(sub_questions: List[SubQuestion]) -> Tuple[List[SubQuestion], List[SubQuestion]]:
    """Drop sub-questions scoring below the configured prune threshold (design §4.3).

    Never prunes to zero branches — a round always keeps its single
    best-scoring sub-question, so an all-low-scoring (or all-high-scoring)
    LLM response can never starve or explode the round; saturation/round-cap
    own the actual stop decision.
    """
    threshold = config.research_planner_prune_threshold
    kept = [s for s in sub_questions if s.expected_value >= threshold]
    pruned = [s for s in sub_questions if s.expected_value < threshold]
    if not kept and sub_questions:
        best = max(sub_questions, key=lambda s: s.expected_value)
        kept, pruned = [best], [s for s in sub_questions if s is not best]
    if pruned:
        logger.info(
            "planner.prune_low_value: pruned %d/%d sub-question(s) below threshold %.2f: %s",
            len(pruned),
            len(sub_questions),
            threshold,
            [s.text for s in pruned],
        )
    return kept, pruned


def _best_known_match(results: List[dict]) -> Tuple[str, float] | None:
    """Return the (fact_id, confidence) of the highest-confidence result, if any."""
    best_id, best_confidence = None, 0.0
    for result in results or []:
        metadata = result.get("metadata") or {}
        try:
            confidence = float(metadata.get("confidence", 0.0) or 0.0)
        except (TypeError, ValueError):
            continue
        fact_id = metadata.get("fact_id") or result.get("node_id") or result.get("doc_id")
        if fact_id and confidence > best_confidence:
            best_id, best_confidence = fact_id, confidence
    return (best_id, best_confidence) if best_id is not None else None


async def filter_skip_known(
    kb: Any, sub_questions: List[SubQuestion]
) -> Tuple[List[SubQuestion], List[SkippedSubQuestion]]:
    """Drop sub-questions already answered by a high-confidence KB fact (design §4.3).

    Correctness note (#12624): skipping is a risk in the opposite direction
    from pruning — a wrong/stale fact could suppress real re-investigation.
    The threshold is a config tunable (never a literal) and every skip is
    audited (fact id + confidence) so it is traceable.
    """
    threshold = config.research_planner_skip_known_confidence_threshold
    to_search: List[SubQuestion] = []
    skipped: List[SkippedSubQuestion] = []
    for sub in sub_questions:
        results = await kb.search(query=sub.text, top_k=config.research_corroboration_search_top_k)
        match = _best_known_match(results)
        if match is None or match[1] < threshold:
            to_search.append(sub)
            continue
        fact_id, confidence = match
        skipped.append(SkippedSubQuestion(text=sub.text, fact_id=fact_id, confidence=confidence))
        logger.info(
            "planner.filter_skip_known: skipping %r — already answered by fact %s (confidence=%.2f >= %.2f)",
            sub.text,
            fact_id,
            confidence,
            threshold,
        )
    return to_search, skipped
