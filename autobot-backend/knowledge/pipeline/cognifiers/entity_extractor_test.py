# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for EntityExtractor NLP mode (Issue #2025).

Covers _nlp_extract(), _select_mode(), and dual-mode dispatch added in
Issue #2025: Dual-mode entity extraction — LLM + NLP (Neural Mesh RAG Phase 2).
"""

import sys
from types import ModuleType
from uuid import uuid4

import pytest

spacy = pytest.importorskip("spacy")

# ---------------------------------------------------------------------------
# Stub out llm_shared so EntityExtractor can be imported without the
# real LLM stack being installed.
# ---------------------------------------------------------------------------
_mock_llm_mod = ModuleType("llm_shared")
_mock_llm_mod.LLMInterface = type("LLMInterface", (), {})  # type: ignore[attr-defined]
sys.modules.setdefault("llm_shared", _mock_llm_mod)

# Stub autobot_shared to satisfy any transitive imports.
_mock_shared = ModuleType("autobot_shared")
_mock_redis_mod = ModuleType("autobot_shared.redis_client")
_mock_redis_mod.get_redis_client = lambda *a, **kw: None  # type: ignore[attr-defined]
sys.modules.setdefault("autobot_shared", _mock_shared)
sys.modules.setdefault("autobot_shared.redis_client", _mock_redis_mod)

from knowledge.pipeline.cognifiers.entity_extractor import EntityExtractor  # noqa: E402
from knowledge.pipeline.models.chunk import ProcessedChunk  # noqa: E402
from knowledge.pipeline.models.entity import Entity  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_chunk(content: str) -> ProcessedChunk:
    return ProcessedChunk(content=content, document_id=uuid4(), chunk_index=0)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestNlpExtractsNamedEntities:
    """_nlp_extract() produces Entity instances for NER spans in text."""

    def test_finds_entities_in_sentence(self) -> None:
        extractor = EntityExtractor(mode="nlp")
        doc_id = uuid4()
        chunks = [_make_chunk("Redis is used by Microsoft")]
        entities = extractor._nlp_extract(chunks, doc_id)

        names = [e.name for e in entities]
        # spaCy en_core_web_sm recognises "Microsoft" as ORG → ORGANIZATION
        assert any("microsoft" in n.lower() for n in names), f"Expected 'Microsoft' in extracted entities, got: {names}"

    def test_returns_entity_model_instances(self) -> None:
        """All items returned by _nlp_extract() must be Entity instances."""
        extractor = EntityExtractor(mode="nlp")
        doc_id = uuid4()
        chunks = [_make_chunk("Apple was founded by Steve Jobs in California.")]
        entities = extractor._nlp_extract(chunks, doc_id)

        assert len(entities) > 0, "Expected at least one entity"
        for entity in entities:
            assert isinstance(entity, Entity), f"Expected Entity, got {type(entity)}"


class TestAutoModeSelection:
    """_select_mode() returns 'nlp' above threshold, 'llm' below."""

    def test_auto_selects_nlp_for_large_input(self) -> None:
        extractor = EntityExtractor(mode="auto", nlp_threshold=5)
        chunks = [_make_chunk(f"chunk {i}") for i in range(10)]
        assert extractor._select_mode(chunks) == "nlp"

    def test_auto_selects_llm_for_small_input(self) -> None:
        extractor = EntityExtractor(mode="auto", nlp_threshold=50)
        chunks = [_make_chunk("only one chunk")]
        assert extractor._select_mode(chunks) == "llm"

    def test_explicit_nlp_mode_ignores_threshold(self) -> None:
        extractor = EntityExtractor(mode="nlp", nlp_threshold=50)
        chunks = [_make_chunk("small")]
        assert extractor._select_mode(chunks) == "nlp"

    def test_explicit_llm_mode_ignores_threshold(self) -> None:
        extractor = EntityExtractor(mode="llm", nlp_threshold=0)
        chunks = [_make_chunk("many " * 100)]
        assert extractor._select_mode(chunks) == "llm"


class TestNlpDeduplication:
    """_nlp_extract() deduplicates by canonical_name (lowercase strip)."""

    def test_deduplicates_across_chunks(self) -> None:
        extractor = EntityExtractor(mode="nlp")
        doc_id = uuid4()
        # Two chunks that both mention "Microsoft" — should appear once.
        chunks = [
            _make_chunk("Microsoft builds Azure."),
            _make_chunk("Microsoft also builds Office."),
        ]
        entities = extractor._nlp_extract(chunks, doc_id)
        canonical_names = [e.canonical_name for e in entities]
        microsoft_entries = [n for n in canonical_names if n == "microsoft"]
        assert len(microsoft_entries) == 1, f"Expected one 'microsoft' entry after dedup, got: {canonical_names}"

    def test_extraction_count_increments_on_duplicate(self) -> None:
        extractor = EntityExtractor(mode="nlp")
        doc_id = uuid4()
        chunks = [
            _make_chunk("Microsoft builds Azure."),
            _make_chunk("Microsoft also builds Office."),
        ]
        entities = extractor._nlp_extract(chunks, doc_id)
        microsoft = next((e for e in entities if e.canonical_name == "microsoft"), None)
        assert microsoft is not None
        assert microsoft.extraction_count >= 2
