# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Semantic contradiction detector for AutoBot knowledge base.

Groups KB chunks by shared keywords, then asks the LLM to identify
contradictions within each group.  Results are returned as a
``ContradictionReport`` dataclass and can be persisted to Redis.

Issue #4566.
"""

import json
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client
from autobot_shared.time_utils import now_utc
from llm_shared.types import LLMType
from services.llm_service import get_llm_service

logger = get_logger(__name__)

# Redis key / TTL constants
_REPORT_KEY = "kb:lint:report"
_REPORT_TTL = 7 * 24 * 3600  # 7 days in seconds

# Minimum group size to check for contradictions
_MIN_GROUP_SIZE = 2

# Keyword stop-words (ignored when building topic groups)
_STOPWORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "and",
        "or",
        "but",
        "if",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "with",
        "by",
        "from",
        "as",
        "it",
        "its",
        "this",
        "that",
        "which",
        "not",
        "no",
        "so",
        "do",
        "did",
        "have",
        "has",
        "had",
    }
)


@dataclass
class ConflictPair:
    """A pair of chunks that contain contradictory information."""

    chunk_a: str
    chunk_b: str
    explanation: str
    confidence: float


@dataclass
class ContradictionReport:
    """Full output of a contradiction scan."""

    contradictions: list[ConflictPair] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    checked_at: datetime = field(default_factory=lambda: now_utc())


# ---------------------------------------------------------------------------
# Grouping helpers
# ---------------------------------------------------------------------------


def _keywords(text: str) -> frozenset[str]:
    """Return lowercased meaningful words from *text*."""
    tokens = re.findall(r"[a-z]+", text.lower())
    return frozenset(t for t in tokens if t not in _STOPWORDS and len(t) > 2)


def _group_chunks(chunks: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Group chunks by their dominant keyword.

    Each chunk is assigned to the group of its most-frequent keyword so that
    chunks sharing many words end up in the same bucket.  Simple but O(n*k)
    where k is keyword count — fast enough for typical KB sizes.
    """
    # Count global keyword frequency so we can pick the rarest meaningful word
    freq: dict[str, int] = {}
    chunk_keywords: list[frozenset[str]] = []
    for chunk in chunks:
        kws = _keywords(chunk.get("text", ""))
        chunk_keywords.append(kws)
        for kw in kws:
            freq[kw] = freq.get(kw, 0) + 1

    groups: dict[str, list[dict[str, Any]]] = {}
    for chunk, kws in zip(chunks, chunk_keywords):
        if not kws:
            groups.setdefault("__ungrouped__", []).append(chunk)
            continue
        # Pick the most frequent keyword as the group label so chunks that
        # share a common topic word land in the same bucket.
        label = max(kws, key=lambda k: freq.get(k, 0))
        groups.setdefault(label, []).append(chunk)
    return groups


# ---------------------------------------------------------------------------
# LLM interaction helpers
# ---------------------------------------------------------------------------

_CONTRADICTION_PROMPT = """\
You are a knowledge-base auditor. Below are {n} statements from a knowledge base.

Identify any direct contradictions between pairs of statements.  A contradiction
is when two statements assert incompatible facts about the same subject.

Return ONLY valid JSON in this exact schema (no markdown, no extra text):
{{
  "contradictions": [
    {{
      "chunk_a": "<exact text of first statement>",
      "chunk_b": "<exact text of second statement>",
      "explanation": "<why they contradict>",
      "confidence": <float 0.0-1.0>
    }}
  ],
  "gaps": ["<topic or fact type that appears to be missing>"]
}}

Statements:
{statements}
"""


def _build_prompt(group_texts: list[str]) -> str:
    """Return the LLM prompt for a group of chunk texts."""
    numbered = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(group_texts))
    return _CONTRADICTION_PROMPT.format(n=len(group_texts), statements=numbered)


def _parse_llm_response(raw: str) -> tuple[list[ConflictPair], list[str]]:
    """Parse the LLM JSON response into ConflictPair list + gaps list."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("LLM returned non-JSON response; skipping group")
        return [], []

    contradictions = [
        ConflictPair(
            chunk_a=c.get("chunk_a", ""),
            chunk_b=c.get("chunk_b", ""),
            explanation=c.get("explanation", ""),
            confidence=float(c.get("confidence", 0.5)),
        )
        for c in data.get("contradictions", [])
    ]
    gaps = [str(g) for g in data.get("gaps", [])]
    return contradictions, gaps


# ---------------------------------------------------------------------------
# Main detector class
# ---------------------------------------------------------------------------


class ContradictionDetector:
    """Detect contradictions in a list of KB chunks.

    Args:
        llm_interface: injected LLM interface (optional; uses default if None)
    """

    def __init__(self, llm_interface=None) -> None:
        self._llm = llm_interface or get_llm_service()

    async def _check_group(self, texts: list[str]) -> tuple[list[ConflictPair], list[str]]:
        """Run LLM contradiction check on a single group of texts."""
        prompt = _build_prompt(texts)
        response = await self._llm.chat(
            [{"role": "user", "content": prompt}],
            llm_type=LLMType.EXTRACTION,
            structured_output=True,
        )
        if not response or response.error:
            logger.warning(
                "LLM error for contradiction check: %s",
                response.error if response else "no response",
            )
            return [], []
        return _parse_llm_response(response.content)

    async def scan(self, chunks: list[dict[str, Any]]) -> ContradictionReport:
        """Run contradiction scan across all chunks.

        Args:
            chunks: list of dicts with at least a ``text`` key and optional
                    metadata fields.

        Returns:
            ContradictionReport with all found contradictions and gaps.
        """
        groups = _group_chunks(chunks)
        logger.info("Contradiction scan: %d chunks → %d groups", len(chunks), len(groups))

        all_conflicts: list[ConflictPair] = []
        all_gaps: list[str] = []

        for label, group in groups.items():
            if len(group) < _MIN_GROUP_SIZE:
                continue
            texts = [c.get("text", "") for c in group]
            conflicts, gaps = await self._check_group(texts)
            if conflicts:
                logger.info("Group '%s': %d contradiction(s) found", label, len(conflicts))
            all_conflicts.extend(conflicts)
            all_gaps.extend(gaps)

        return ContradictionReport(
            contradictions=all_conflicts,
            gaps=list(dict.fromkeys(all_gaps)),  # deduplicate preserving order
        )


# ---------------------------------------------------------------------------
# Redis persistence helpers
# ---------------------------------------------------------------------------


def _report_to_dict(report: ContradictionReport) -> dict[str, Any]:
    """Serialize ContradictionReport to a JSON-safe dict."""
    d = asdict(report)
    d["checked_at"] = report.checked_at.isoformat()
    return d


async def store_report(report: ContradictionReport) -> None:
    """Persist *report* to Redis under ``kb:lint:report`` with 7-day TTL."""
    redis = await get_async_redis_client(database="knowledge")
    payload = json.dumps(_report_to_dict(report), ensure_ascii=False)
    await redis.set(_REPORT_KEY, payload, ex=_REPORT_TTL)
    logger.info("Contradiction report stored in Redis (key=%s)", _REPORT_KEY)


async def load_report() -> dict[str, Any] | None:
    """Load the latest contradiction report from Redis.

    Returns:
        Parsed report dict or None if no report is stored.
    """
    redis = await get_async_redis_client(database="knowledge")
    raw = await redis.get(_REPORT_KEY)
    if raw is None:
        return None
    return json.loads(raw)


def generate_job_id() -> str:
    """Return a unique job identifier for a lint run."""
    return str(uuid.uuid4())
