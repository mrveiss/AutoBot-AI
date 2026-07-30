# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for services.research.orchestrator.ResearchOrchestrator (#12622).

Mocks every composed dependency (search registry, WebFetcher, KB, extractor,
synthesizer) so these tests exercise only the orchestrator's own wiring and
budget/failure-path logic — not the composed modules themselves (already
tested in their own colocated test files).
"""

from dataclasses import dataclass
from unittest.mock import AsyncMock, patch

# Force full (non-partial) module init before any test patches
# "agent_loop.search.registry.search" — agent_loop/__init__.py pulls in a
# heavy import chain, and patching a module mid-circular-import can silently
# patch a stale partial module object instead of the one later imports see.
import agent_loop.search.registry  # noqa: F401,E402
import web_fetch  # noqa: F401,E402
from services.research.models import ExtractedClaim, StoredFact
from services.research.orchestrator import ResearchOrchestrator
from services.research.synthesizer import SynthesisResult

_MODULE = "services.research.orchestrator"


@dataclass
class _FakeSearchResult:
    url: str


@dataclass
class _FakeFetchResult:
    success: bool
    markdown: str = ""
    title: str = ""


def _make_kb(store_fact_status: str = "success") -> AsyncMock:
    kb = AsyncMock()
    kb.add_document = AsyncMock(return_value={"status": "success", "fact_id": "doc-1"})
    kb.store_fact = AsyncMock(return_value={"status": store_fact_status, "fact_id": "fact-1"})
    return kb


def _patch_common(kb, urls, fetch_result, claims, synthesis):
    """Patch the four seams ResearchOrchestrator delegates to."""
    return (
        patch(f"{_MODULE}.get_knowledge_base", AsyncMock(return_value=kb)),
        patch("agent_loop.search.registry.search", AsyncMock(return_value=[_FakeSearchResult(u) for u in urls])),
        patch("web_fetch.WebFetcher.fetch", AsyncMock(return_value=fetch_result)),
        patch(f"{_MODULE}.extract_claims", AsyncMock(return_value=claims)),
        patch(f"{_MODULE}.synthesize_answer", AsyncMock(return_value=synthesis)),
    )


class TestResearchHappyPath:
    """End-to-end happy path with every dependency mocked."""

    async def test_full_pipeline_produces_contract_shape(self):
        """One source -> one claim -> cited synthesis -> full response contract."""
        kb = _make_kb()
        claim = ExtractedClaim(content="X is Y.", confidence=0.8, source_url="https://a.example", source_doc_id="doc-1")
        fact = StoredFact(
            fact_id="fact-1",
            content="X is Y.",
            confidence=0.8,
            source_url="https://a.example",
            source_doc_id="doc-1",
            is_new=True,
        )
        synthesis = SynthesisResult(answer="X is Y [F1].", citations=[], confidence=0.7)
        # citations reference StoredFact ids the orchestrator itself built, so
        # set the citation to match the fact the mocked _store_claim path returns.
        from services.research.models import Citation

        synthesis.citations = [Citation(fact_id="fact-1", source_url="https://a.example", source_doc_id="doc-1")]
        fetch_result = _FakeFetchResult(success=True, markdown="X is Y because of Z.", title="Page A")

        patches = _patch_common(kb, ["https://a.example"], fetch_result, [claim], synthesis)
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            response = await ResearchOrchestrator(llm_service=AsyncMock()).research("what is X?")

        assert response.answer == "X is Y [F1]."
        assert response.sources_fetched == 1
        assert response.facts_stored == 1
        assert len(response.facts) == 1
        assert response.facts[0].fact_id == "fact-1"
        assert response.contradictions == []
        _ = fact  # documents the shape _store_claim would build; asserted via facts_stored above


class TestResearchBudget:
    """Budget clamping (design §8 D5)."""

    async def test_max_sources_clamped_to_config_cap(self):
        """A caller cannot request more sources than the configured hard cap."""
        kb = _make_kb()
        synthesis = SynthesisResult(answer="no facts", citations=[], confidence=0.0)
        search_mock = AsyncMock(return_value=[])

        with (
            patch(f"{_MODULE}.get_knowledge_base", AsyncMock(return_value=kb)),
            patch("agent_loop.search.registry.search", search_mock),
            patch(f"{_MODULE}.synthesize_answer", AsyncMock(return_value=synthesis)),
        ):
            await ResearchOrchestrator(llm_service=AsyncMock()).research("q", {"max_sources": 999})

        # config.research_max_sources default is 5 (see autobot_shared.ssot_config)
        assert search_mock.await_args.kwargs["count"] == 5


class TestResearchFailurePaths:
    """A single bad source must never sink the whole run."""

    async def test_kb_unavailable_returns_caveat_without_fetching(self):
        """When the KB is unavailable, research() short-circuits before any fetch."""
        with patch(f"{_MODULE}.get_knowledge_base", AsyncMock(return_value=None)):
            response = await ResearchOrchestrator(llm_service=AsyncMock()).research("q")

        assert "unavailable" in response.answer.lower()
        assert response.facts_stored == 0

    async def test_fetch_failure_yields_zero_facts_for_that_source(self):
        """A failed fetch contributes no facts but the run still completes."""
        kb = _make_kb()
        synthesis = SynthesisResult(answer="no facts", citations=[], confidence=0.0)
        failed_fetch = _FakeFetchResult(success=False)

        patches = _patch_common(kb, ["https://bad.example"], failed_fetch, [], synthesis)
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            response = await ResearchOrchestrator(llm_service=AsyncMock()).research("q")

        assert response.facts_stored == 0
        assert response.sources_fetched == 1

    async def test_add_document_failure_yields_zero_facts(self):
        """A failed add_document skips claim extraction for that source entirely."""
        kb = _make_kb()
        kb.add_document = AsyncMock(return_value={"status": "error", "message": "boom"})
        synthesis = SynthesisResult(answer="no facts", citations=[], confidence=0.0)
        fetch_result = _FakeFetchResult(success=True, markdown="some text", title="t")

        patches = _patch_common(kb, ["https://a.example"], fetch_result, [], synthesis)
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            response = await ResearchOrchestrator(llm_service=AsyncMock()).research("q")

        assert response.facts_stored == 0
        kb.store_fact.assert_not_awaited()

    async def test_duplicate_claim_reuses_existing_fact_not_a_new_one(self):
        """store_fact returning status=duplicate is treated as a landed (reused) fact."""
        kb = _make_kb(store_fact_status="duplicate")
        claim = ExtractedClaim(content="X is Y.", confidence=0.8, source_url="https://a.example", source_doc_id="doc-1")
        synthesis = SynthesisResult(answer="no facts", citations=[], confidence=0.0)
        fetch_result = _FakeFetchResult(success=True, markdown="X is Y.", title="t")

        patches = _patch_common(kb, ["https://a.example"], fetch_result, [claim], synthesis)
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            response = await ResearchOrchestrator(llm_service=AsyncMock()).research("q")

        assert response.facts_stored == 1
