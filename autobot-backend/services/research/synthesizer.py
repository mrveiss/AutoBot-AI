# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Grounded LLM synthesis over KB facts (#12622, design §4.8).

Every synthesized sentence must cite a fact id that was actually retrieved
for this run; the anti-hallucinated-citation post-check drops any inline
marker or structured citation the LLM invents.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger
from llm_shared.json_utils import extract_json_object

from .models import Citation, StoredFact

logger = get_logger(__name__)

_MARKER_RE = re.compile(r"\[F(\d+)\]")

_SYNTHESIS_SYSTEM_PROMPT = (
    "You answer a research question using ONLY the numbered facts provided. "
    "Rules: (1) every sentence that states something from the facts must end "
    "with one or more inline markers like [F1] or [F2,F3] referencing the "
    "fact number(s) it relies on; (2) never state anything not supported by "
    "a fact — omit it instead; (3) if facts disagree, say so explicitly and "
    "list the conflicting fact numbers. Respond with ONLY a JSON object: "
    '{"answer": str, "confidence": float 0.0-1.0}. confidence reflects how '
    "well the available facts cover the question (low if facts are sparse)."
)


@dataclass
class SynthesisResult:
    """Grounded answer plus the citations that survived the post-check."""

    answer: str
    citations: List[Citation]
    confidence: float


def _build_facts_block(facts: List[StoredFact]) -> str:
    """Render facts as a numbered block the LLM references via [F<n>]."""
    lines = [f"[F{i + 1}] {fact.content}" for i, fact in enumerate(facts)]
    return "\n".join(lines)


def _build_synthesis_messages(question: str, facts: List[StoredFact]) -> List[Dict[str, str]]:
    """Build the chat messages for one synthesis call."""
    user_content = f"Question: {question}\n\nFacts:\n{_build_facts_block(facts)}"
    return [
        {"role": "system", "content": _SYNTHESIS_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def _parse_synthesis_payload(raw_content: str) -> Dict[str, Any]:
    """Parse the LLM's JSON response, tolerating malformed output."""
    try:
        return extract_json_object(raw_content)
    except json.JSONDecodeError:
        logger.warning("synthesize_answer: LLM response was not valid JSON")
        return {}


def _sanitize_answer_and_collect_citations(answer: str, facts: List[StoredFact]) -> tuple[str, List[Citation]]:
    """Strip markers citing an out-of-range fact number; collect valid citations.

    Anti-hallucinated-citation post-check (#12622 acceptance criteria):
    every surviving ``[F<n>]`` marker maps to a fact that was actually
    retrieved for this run.
    """
    valid_indices: set[int] = set()

    def _replace(match: re.Match) -> str:
        idx = int(match.group(1))
        if 1 <= idx <= len(facts):
            valid_indices.add(idx)
            return match.group(0)
        return ""

    sanitized = _MARKER_RE.sub(_replace, answer)
    citations = [_fact_to_citation(facts[i - 1]) for i in sorted(valid_indices)]
    return sanitized, citations


def _fact_to_citation(fact: StoredFact) -> Citation:
    """Map a stored fact to its citation shape."""
    return Citation(fact_id=fact.fact_id, source_url=fact.source_url, source_doc_id=fact.source_doc_id)


async def synthesize_answer(llm_service: Any, question: str, facts: List[StoredFact]) -> SynthesisResult:
    """Produce a grounded, cited answer from *facts*, or a caveat if none exist."""
    if not facts:
        return SynthesisResult(
            answer="No facts were gathered for this question; unable to provide a grounded answer.",
            citations=[],
            confidence=0.0,
        )

    response = await llm_service.chat(messages=_build_synthesis_messages(question, facts), temperature=0.0)
    if response.error:
        logger.warning("synthesize_answer: LLM call failed: %s", response.error)
        return SynthesisResult(answer="Synthesis failed; raw facts are available below.", citations=[], confidence=0.0)

    payload = _parse_synthesis_payload(response.content)
    raw_answer = str(payload.get("answer", "")).strip()
    try:
        raw_confidence = max(0.0, min(1.0, float(payload.get("confidence", 0.0))))
    except (TypeError, ValueError):
        raw_confidence = 0.0

    sanitized_answer, citations = _sanitize_answer_and_collect_citations(raw_answer, facts)
    if not citations:
        return SynthesisResult(
            answer="No cited claim survived verification; unable to provide a grounded answer.",
            citations=[],
            confidence=0.0,
        )
    return SynthesisResult(answer=sanitized_answer, citations=citations, confidence=raw_confidence)
