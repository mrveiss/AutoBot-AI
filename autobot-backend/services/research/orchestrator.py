# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""ResearchOrchestrator (#12622, design §4.1) — the one new coordinator.

Composes existing modules (never recreates them, design §6):
  * ``services.research.router`` — topic-based source routing over the
    shared ``agent_loop.search.registry`` (#12625)
  * ``web_fetch.WebFetcher`` — fast-HTTP page fetch
  * ``knowledge_base_factory.get_knowledge_base`` — the canonical KB facade
  * ``services.research.extractor`` / ``synthesizer`` — the two new LLM steps
  * ``services.research.planner`` — sub-question decomposition, pruning,
    skip-known filtering (#12624)
  * ``services.plateau_detector`` — saturation stop, shared with
    ``AutoResearchAgent`` (#12624)
  * ``services.claim_verifier.ClaimVerifier.corroborate`` — N-source
    corroboration + promotion gate (#12623)

The round loop (``_plan_and_fetch``) is bounded by three independent, always
-enforced guards so a mis-scored branch or a garbage LLM response can never
cause unbounded iteration/spend (#12624): a hard round cap, a total-source
budget, and plateau/saturation detection.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config
from knowledge_base_factory import get_knowledge_base
from services.claim_verifier import ClaimVerifier, CorroborationResult
from services.knowledge_grounding_models import KBSource
from services.llm_service import get_llm_service
from services.plateau_detector import plateau_reached

from .extractor import extract_claims
from .models import ExtractedClaim, ResearchBudget, ResearchFactOut, ResearchResponse, StoredFact
from .planner import decompose_question, filter_skip_known, prune_low_value
from .synthesizer import synthesize_answer

logger = get_logger(__name__)


def _resolve_budget(options: dict) -> ResearchBudget:
    """Build the run's budget, clamped to the configured hard caps (design §8 D5)."""
    requested_sources = int(options.get("max_sources", config.research_max_sources))
    return ResearchBudget(
        max_sources=max(1, min(requested_sources, config.research_max_sources)),
        max_content_chars=config.research_max_content_chars,
        fetch_timeout_seconds=config.research_fetch_timeout_seconds,
    )


async def _discover_sources(question: str, max_sources: int) -> List[str]:
    """Find candidate URLs for *question* via topic-routed search (#12625).

    Delegates to ``services.research.router.route_search``, which prefers a
    specialized provider for the question's inferred topic and otherwise
    preserves the registry's unchanged default fallback order.
    """
    from services.research.router import route_search  # noqa: PLC0415

    results = await route_search(question, count=max_sources)
    return [r.url for r in results if r.url]


async def _fetch_source(url: str, timeout: float) -> Any:
    """Fetch one URL, logging and swallowing per-source failures (budget §8 D5)."""
    from web_fetch import RenderMode, WebFetcher  # noqa: PLC0415

    try:
        result = await WebFetcher.fetch(url, render=RenderMode.AUTO, timeout=timeout)
    except Exception as exc:  # noqa: BLE001 — one bad source must not sink the run
        logger.warning("ResearchOrchestrator: fetch failed for %s: %s", url, exc)
        return None
    return result if result.success and result.markdown.strip() else None


def _claim_unique_key(url: str, claim_text: str) -> str:
    """Stable dedup key: same (source, claim) across runs collapses to one fact."""
    digest = hashlib.sha256(f"{url}::{claim_text.strip().lower()}".encode("utf-8")).hexdigest()
    return f"research:{digest[:32]}"


async def _store_source_document(kb: Any, url: str, title: str, markdown: str) -> str | None:
    """Store the fetched page as the KB document of record (design §4.5)."""
    metadata = {
        "source_type": "web_research",
        "url": url,
        "title": title,
        "collection": config.research_quarantine_collection,
    }
    result = await kb.add_document(content=markdown, metadata=metadata)
    if result.get("status") not in ("success", "duplicate"):
        logger.warning("ResearchOrchestrator: add_document failed for %s: %s", url, result)
        return None
    return result.get("fact_id")


async def _store_claim(kb: Any, claim: ExtractedClaim) -> StoredFact | None:
    """Land one extracted claim as a quarantined KB fact (design §5)."""
    metadata = {
        "collection": config.research_quarantine_collection,
        "source_type": "web_research",
        "url": claim.source_url,
        "source_doc_id": claim.source_doc_id,
        "confidence": claim.confidence,
        "unique_key": _claim_unique_key(claim.source_url, claim.content),
    }
    result = await kb.store_fact(claim.content, metadata=metadata)
    if result.get("status") not in ("success", "duplicate"):
        logger.warning("ResearchOrchestrator: store_fact failed: %s", result)
        return None
    is_new = result.get("status") == "success"
    return StoredFact(
        fact_id=result["fact_id"],
        content=claim.content,
        confidence=claim.confidence,
        source_url=claim.source_url,
        source_doc_id=claim.source_doc_id,
        is_new=is_new,
    )


def _kb_result_to_source(result: dict) -> KBSource:
    """Map a raw ``kb.search()`` result dict to a ``KBSource`` (#12623)."""
    metadata = result.get("metadata") or {}
    return KBSource(
        source_id=metadata.get("fact_id", result.get("node_id", result.get("doc_id", ""))),
        source_type=metadata.get("source_type", "document"),
        text=result.get("content", ""),
        confidence=result.get("score", 0.0),
        age_days=metadata.get("age_days", 0.0),
        url=metadata.get("url"),
    )


async def _gather_candidate_sources(kb: Any, fact: StoredFact) -> List[KBSource]:
    """Search the quarantine collection for other facts that might corroborate *fact*."""
    raw = await kb.search(
        query=fact.content,
        top_k=config.research_corroboration_search_top_k,
        filters={"collection": config.research_quarantine_collection},
    )
    sources = [_kb_result_to_source(r) for r in (raw or [])]
    return [s for s in sources if s.source_id and s.source_id != fact.fact_id]


async def _promote_fact(kb: Any, fact: StoredFact, result: CorroborationResult) -> None:
    """Promote a corroborated fact out of quarantine (#12623, one-way trust boundary).

    Reversible/auditable: records the evidence count and confidence that
    justified promotion rather than silently moving the fact.
    """
    await kb.update_fact(
        fact.fact_id,
        metadata={
            "collection": config.research_promoted_collection,
            "verification_status": "verified",
            "requires_human_review": False,
            "promoted_at": datetime.now(tz=timezone.utc).isoformat(),
            "promotion_confidence": result.confidence,
            "promotion_evidence_count": result.independent_agree_count,
        },
    )
    logger.info(
        "ResearchOrchestrator: promoted fact %s (confidence=%.2f, sources=%d)",
        fact.fact_id,
        result.confidence,
        result.independent_agree_count,
    )


async def _flag_contradiction(kb: Any, fact: StoredFact, result: CorroborationResult) -> dict:
    """Record a contradiction: fact->fact relation(s) + human-review flag; never promoted."""
    for source in result.contradicting_sources:
        await kb.create_fact_relation(
            fact.fact_id,
            source.source_id,
            "contradicts",
            metadata={"detected_by": "research_corroborator"},
        )
    await kb.update_fact(
        fact.fact_id,
        metadata={"verification_status": "disputed", "requires_human_review": True},
    )
    logger.warning(
        "ResearchOrchestrator: fact %s disputed by %d source(s) — staying quarantined",
        fact.fact_id,
        len(result.contradicting_sources),
    )
    return {
        "fact_id": fact.fact_id,
        "content": fact.content,
        "contradicting_fact_ids": [s.source_id for s in result.contradicting_sources],
    }


class ResearchOrchestrator:
    """Bundles fetch -> KB-fact landing -> grounded synthesis for one question."""

    def __init__(self, llm_service: Any | None = None) -> None:
        self._llm_service = llm_service

    async def _llm(self) -> Any:
        if self._llm_service is None:
            self._llm_service = get_llm_service()
        return self._llm_service

    @staticmethod
    def _record_truncation_if_needed(url: str, markdown: str, budget: ResearchBudget) -> None:
        """Record *url* in ``budget.truncated_sources`` if its content exceeded the
        content-char budget that ``extract_claims`` enforces (design §8 D5).

        This is the one place ``ResearchBudget.max_content_chars`` is actually
        applied against a source (``extract_claims`` slices to it, #12622) —
        recording here keeps that single truncation point auditable via the
        budget itself, not just a log line.
        """
        if len(markdown) > budget.max_content_chars:
            budget.truncated_sources.append(url)
            logger.info(
                "ResearchOrchestrator: truncated %s to max_content_chars=%d (source was %d chars)",
                url,
                budget.max_content_chars,
                len(markdown),
            )

    async def _land_page(self, kb: Any, url: str, budget: ResearchBudget) -> List[StoredFact]:
        """Fetch one URL, extract claims, and land them as quarantined facts."""
        fetch_result = await _fetch_source(url, budget.fetch_timeout_seconds)
        if fetch_result is None:
            return []
        doc_id = await _store_source_document(kb, url, fetch_result.title, fetch_result.markdown)
        if doc_id is None:
            return []
        self._record_truncation_if_needed(url, fetch_result.markdown, budget)
        llm = await self._llm()
        claims = await extract_claims(llm, fetch_result.markdown, url, doc_id, budget.max_content_chars)
        stored = [await _store_claim(kb, claim) for claim in claims]
        return [fact for fact in stored if fact is not None]

    async def _run_one_round(
        self, kb: Any, llm: Any, question: str, budget: ResearchBudget, remaining_sources: int
    ) -> Tuple[List[StoredFact], int]:
        """One planner round: decompose -> prune -> skip-known -> fetch (design §4.3).

        Bounded by *remaining_sources* (the caller's total-source budget) in
        addition to the per-discovery-call ``budget.max_sources``.
        """
        sub_questions = await decompose_question(llm, question)
        kept, _pruned = prune_low_value(sub_questions)
        to_search, _skipped = await filter_skip_known(kb, kept)
        landed: List[StoredFact] = []
        used = 0
        for sub in to_search:
            if used >= remaining_sources:
                break
            count = min(budget.max_sources, remaining_sources - used)
            urls = await _discover_sources(sub.text, count)
            for url in urls:
                if used >= remaining_sources:
                    break
                landed.extend(await self._land_page(kb, url, budget))
                used += 1
        return landed, used

    async def _plan_and_fetch(
        self, kb: Any, llm: Any, question: str, budget: ResearchBudget
    ) -> Tuple[List[StoredFact], int]:
        """Run the bounded round loop until saturation, the round cap, or the
        total-source budget stops it — whichever comes first (#12624; never
        unbounded, design §8 D5).
        """
        all_facts: List[StoredFact] = []
        round_progress: List[bool] = []
        sources_used = 0
        max_total = config.research_planner_max_total_sources
        max_rounds = config.research_planner_max_rounds
        for round_num in range(1, max_rounds + 1):
            remaining = max_total - sources_used
            if remaining <= 0:
                logger.info(
                    "ResearchOrchestrator: total-source budget (%d) exhausted before round %d", max_total, round_num
                )
                break
            landed, used = await self._run_one_round(kb, llm, question, budget, remaining)
            all_facts.extend(landed)
            sources_used += used
            round_progress.append(any(f.is_new for f in landed))
            if plateau_reached(round_progress, config.research_planner_plateau_window):
                logger.info("ResearchOrchestrator: saturation reached at round %d/%d", round_num, max_rounds)
                break
        else:
            logger.info("ResearchOrchestrator: round cap (%d) reached", max_rounds)
        return all_facts, sources_used

    async def _corroborate_material_facts(
        self, kb: Any, material_facts: List[StoredFact]
    ) -> tuple[List[dict], Dict[str, float]]:
        """N-source corroboration + promotion gate for cited (material) facts only (#12623).

        Cost control: only claims the synthesizer actually asserted are worth
        the corroboration LLM calls (design: "verify only asserted claims").
        Returns (contradiction records for ``contradictions[]``, confidence
        overrides for promoted facts so ``facts[].confidence`` in the response
        reflects the corroboration outcome per the acceptance criteria).
        """
        verifier = ClaimVerifier(knowledge_base=kb, llm_service=await self._llm())
        contradictions: List[dict] = []
        confidence_overrides: Dict[str, float] = {}
        for fact in material_facts:
            candidates = await _gather_candidate_sources(kb, fact)
            result = await verifier.corroborate(fact.content, candidates, claim_url=fact.source_url)
            if result.verified:
                await _promote_fact(kb, fact, result)
                confidence_overrides[fact.fact_id] = result.confidence
            elif result.requires_human_review:
                contradictions.append(await _flag_contradiction(kb, fact, result))
        return contradictions, confidence_overrides

    async def research(self, question: str, options: dict | None = None) -> ResearchResponse:
        """Run the bounded planner-driven pipeline and return the full #12622 contract."""
        budget = _resolve_budget(options or {})
        kb = await get_knowledge_base()
        if kb is None:
            return ResearchResponse(answer="Knowledge base unavailable; cannot perform research.", confidence=0.0)

        llm = await self._llm()
        all_facts, sources_fetched = await self._plan_and_fetch(kb, llm, question, budget)

        synthesis = await synthesize_answer(llm, question, all_facts)
        cited_ids = {c.fact_id for c in synthesis.citations}
        material_facts = [f for f in all_facts if f.fact_id in cited_ids]
        contradictions, confidence_overrides = await self._corroborate_material_facts(kb, material_facts)
        facts_out = [
            ResearchFactOut(
                fact_id=f.fact_id,
                content=f.content,
                source_url=f.source_url,
                confidence=confidence_overrides.get(f.fact_id, f.confidence),
            )
            for f in material_facts
        ]
        return ResearchResponse(
            answer=synthesis.answer,
            citations=synthesis.citations,
            facts=facts_out,
            contradictions=contradictions,
            confidence=synthesis.confidence,
            sources_fetched=sources_fetched,
            facts_stored=len(all_facts),
        )
