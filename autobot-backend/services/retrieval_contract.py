# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Request contract of the canonical retrieval entry ``RAGService.advanced_search`` (#21606, #20950).

``RetrievalPlan`` names the per-technique toggles, ``DEFAULT_PLAN`` is today's behaviour, and every
returned hit carries a ``HitProvenance`` (bucket, leg, per-leg scores, final score). A toggle whose
leg does not exist yet is accepted and listed in ``PlannedMetrics.unsupported`` -- never ignored.

The toggle names equal the benchmark gate's ``TECHNIQUES`` (#20949, ``knowledge/retrieval_gate.py``)
plus ``docs``; ``GATE_TECHNIQUES`` below mirrors them until that gate lands on main, and the
reconciliation test then reads the gate's tuple instead.
"""

from dataclasses import dataclass, field, fields
from typing import Any, Dict, List, Mapping, Tuple

from advanced_rag_optimizer import RAGMetrics, RankedResult

#: The gate's technique names (#20949) -- source of the plan's field names, plus ``docs``.
GATE_TECHNIQUES: Tuple[str, ...] = ("dense", "bm25", "fusion", "rerank", "query_expansion", "graph", "memory", "cache")

PROVENANCE_ATTR = "provenance"

BUCKET_DOCS = "docs"
BUCKET_FACTS = "facts"
LEG_DOCS = "docs"
LEG_CACHE = "cache"
LEG_HYBRID = "hybrid"

_CACHE_SOURCES = frozenset({"topic_cache", "semantic_cache"})


@dataclass(frozen=True)
class RetrievalPlan:
    """Which retrieval techniques one ``advanced_search`` call uses."""

    dense: bool = True
    bm25: bool = True
    fusion: bool = True
    rerank: bool = True
    query_expansion: bool = True
    graph: bool = False
    memory: bool = False
    docs: bool = True
    cache: bool = True


#: Today's behaviour exactly; changing it needs a benchmark-gate report (#20949).
DEFAULT_PLAN = RetrievalPlan()

#: Toggles ``advanced_search`` honours today; the others have no switchable leg yet (#20950 W2+).
SUPPORTED_TOGGLES = frozenset({"rerank", "docs", "cache"})


def unsupported_toggles(plan: RetrievalPlan) -> Tuple[str, ...]:
    """The toggles *plan* sets away from today's fixed engine behaviour that no leg can honour yet."""
    return tuple(
        f.name
        for f in fields(plan)
        if f.name not in SUPPORTED_TOGGLES and getattr(plan, f.name) != getattr(DEFAULT_PLAN, f.name)
    )


def require_plan(plan: Any) -> RetrievalPlan:
    """*plan* itself when it is a ``RetrievalPlan``; anything else is a caller bug and raises."""
    if not isinstance(plan, RetrievalPlan):
        raise TypeError("plan must be a RetrievalPlan")
    return plan


@dataclass(frozen=True)
class HitProvenance:
    """Where one returned hit came from and how it scored."""

    bucket: str
    leg: str
    scores: Mapping[str, float] = field(default_factory=dict)
    final_score: float = 0.0


@dataclass
class PlannedMetrics(RAGMetrics):
    """``RAGMetrics`` plus the plan report; returned only when the plan has unsupported toggles."""

    unsupported: List[str] = field(default_factory=list)


def _bucket_and_leg(source: str) -> Tuple[str, str]:
    if source == "autobot_docs":
        return BUCKET_DOCS, LEG_DOCS
    if source in _CACHE_SOURCES:
        return BUCKET_FACTS, LEG_CACHE
    return BUCKET_FACTS, LEG_HYBRID


def build_provenance(hit: RankedResult) -> HitProvenance:
    """The provenance of *hit*: its source decides bucket and leg, its score fields the per-leg scores."""
    bucket, leg = _bucket_and_leg((hit.metadata or {}).get("source", ""))
    scores: Dict[str, float] = {
        "semantic": hit.semantic_score,
        "keyword": hit.keyword_score,
        "hybrid": hit.hybrid_score,
    }
    if hit.rerank_score is not None:
        scores["rerank"] = hit.rerank_score
    final = hit.rerank_score if hit.rerank_score is not None else hit.hybrid_score
    return HitProvenance(bucket=bucket, leg=leg, scores=scores, final_score=final)


def get_provenance(hit: RankedResult) -> HitProvenance | None:
    """The provenance stamped on *hit* by ``advanced_search``, or ``None`` for a hit that never went through it."""
    return getattr(hit, PROVENANCE_ATTR, None)


def finalize_hits(
    results: List[RankedResult], metrics: RAGMetrics, plan: RetrievalPlan
) -> Tuple[List[RankedResult], RAGMetrics]:
    """Stamp provenance on every hit; wrap *metrics* only when the plan has unsupported toggles.

    Provenance is an attribute, not a field, so ``RankedResult`` equality and its cached form are
    untouched. Under ``DEFAULT_PLAN`` the metrics object is returned as is.
    """
    for hit in results:
        setattr(hit, PROVENANCE_ATTR, build_provenance(hit))
    unsupported = unsupported_toggles(plan)
    if unsupported:
        base = {f.name: getattr(metrics, f.name) for f in fields(RAGMetrics)}
        metrics = PlannedMetrics(**base, unsupported=list(unsupported))
    return results, metrics
