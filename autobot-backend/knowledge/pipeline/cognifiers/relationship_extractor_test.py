# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for RelationshipExtractor NLP-mode additions.

Issue #2026: Dual-mode relationship extraction — LLM + NLP.
"""

import sys
from types import ModuleType
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

# Mock llm_shared before importing cognifiers
_mock_llm = ModuleType("llm_shared")
_mock_llm.LLMInterface = MagicMock
sys.modules["llm_shared"] = _mock_llm

# Mock autobot_shared before importing cognifiers
_mock_shared = ModuleType("autobot_shared")
_mock_redis_mod = ModuleType("autobot_shared.redis_client")
_mock_redis_mod.get_redis_client = MagicMock()
sys.modules["autobot_shared"] = _mock_shared
sys.modules["autobot_shared.redis_client"] = _mock_redis_mod

from knowledge.pipeline.cognifiers.relationship_extractor import (  # noqa: E402
    NLP_KEYWORD_PATTERNS,
    RelationshipExtractor,
)
from knowledge.pipeline.models.chunk import ProcessedChunk  # noqa: E402
from knowledge.pipeline.models.entity import Entity  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _entity(name: str, doc_id=None) -> Entity:
    """Build a minimal Entity with canonical_name = name.lower()."""
    return Entity(
        name=name,
        canonical_name=name.lower(),
        entity_type="TECHNOLOGY",
        source_document_id=doc_id or uuid4(),
    )


def _chunk(content: str) -> ProcessedChunk:
    """Build a minimal ProcessedChunk."""
    return ProcessedChunk(content=content, document_id=uuid4(), chunk_index=0)


@pytest.fixture
def extractor() -> RelationshipExtractor:
    return RelationshipExtractor(mode="nlp")


# ---------------------------------------------------------------------------
# Test: co-occurrence creates a RELATES_TO relationship
# ---------------------------------------------------------------------------


class TestCoOccurrenceCreatesRelationship:
    """Issue #2026: two entities in same chunk yield CO_OCCURS (RELATES_TO)."""

    def test_co_occurrence_creates_relationship(self, extractor):
        chunk = _chunk("FastAPI and Redis are used together in this service.")
        entities = [_entity("FastAPI"), _entity("Redis")]

        rels = extractor._nlp_extract([chunk], entities)

        assert len(rels) == 1
        assert rels[0].relationship_type == "RELATES_TO"
        assert rels[0].confidence == 0.6

    def test_single_entity_produces_no_relationship(self, extractor):
        chunk = _chunk("FastAPI is a web framework.")
        entities = [_entity("FastAPI")]

        rels = extractor._nlp_extract([chunk], entities)

        assert rels == []

    def test_entity_absent_from_chunk_excluded(self, extractor):
        chunk = _chunk("FastAPI is fast.")
        entities = [_entity("FastAPI"), _entity("Celery")]

        rels = extractor._nlp_extract([chunk], entities)

        # "celery" not in chunk text -> only FastAPI present -> no pair
        assert rels == []


# ---------------------------------------------------------------------------
# Test: keyword pattern creates typed relationship
# ---------------------------------------------------------------------------


class TestKeywordPatternCreatesTypedRelationship:
    """Issue #2026: keyword in chunk text overrides default RELATES_TO type."""

    def test_import_keyword_creates_uses(self, extractor):
        chunk = _chunk("FastAPI import Redis for caching.")
        entities = [_entity("FastAPI"), _entity("Redis")]

        rels = extractor._nlp_extract([chunk], entities)

        assert len(rels) == 1
        assert rels[0].relationship_type == "USES"

    def test_extend_keyword_creates_extends(self, extractor):
        chunk = _chunk("AuthService extend BaseService configuration.")
        entities = [_entity("AuthService"), _entity("BaseService")]

        rels = extractor._nlp_extract([chunk], entities)

        assert len(rels) == 1
        assert rels[0].relationship_type == "EXTENDS"

    def test_depend_keyword_creates_depends_on(self, extractor):
        chunk = _chunk("Celery depend on Redis broker.")
        entities = [_entity("Celery"), _entity("Redis")]

        rels = extractor._nlp_extract([chunk], entities)

        assert len(rels) == 1
        assert rels[0].relationship_type == "DEPENDS_ON"

    def test_trigger_keyword_creates_triggers(self, extractor):
        chunk = _chunk("Workflow trigger Celery task execution.")
        entities = [_entity("Workflow"), _entity("Celery")]

        rels = extractor._nlp_extract([chunk], entities)

        assert len(rels) == 1
        assert rels[0].relationship_type == "TRIGGERS"

    def test_call_keyword_creates_triggers(self, extractor):
        chunk = _chunk("FastAPI call Redis directly.")
        entities = [_entity("FastAPI"), _entity("Redis")]

        rels = extractor._nlp_extract([chunk], entities)

        assert len(rels) == 1
        assert rels[0].relationship_type == "TRIGGERS"

    def test_all_patterns_map_to_valid_relation_types(self):
        """Ensure every NLP_KEYWORD_PATTERNS value is a valid RelationType."""
        from knowledge.pipeline.models.relationship import RelationType

        valid = set(RelationType.__args__)
        for keyword, rel_type in NLP_KEYWORD_PATTERNS.items():
            assert rel_type in valid, f"Keyword '{keyword}' maps to '{rel_type}' which is not a valid RelationType"


# ---------------------------------------------------------------------------
# Test: auto mode selects NLP for large input
# ---------------------------------------------------------------------------


class TestAutoSelectsNlpForLargeInput:
    """Issue #2026: auto mode switches to NLP when total chars exceed threshold."""

    def test_auto_selects_nlp_above_threshold(self):
        extractor = RelationshipExtractor(mode="auto", nlp_threshold=10)
        chunk = _chunk("A" * 20)  # 20 chars > threshold 10

        mode = extractor._select_mode([chunk])

        assert mode == "nlp"

    def test_auto_selects_llm_below_threshold(self):
        extractor = RelationshipExtractor(mode="auto", nlp_threshold=500)
        chunk = _chunk("Short chunk.")

        mode = extractor._select_mode([chunk])

        assert mode == "llm"

    def test_auto_selects_nlp_multi_chunk_cumulative(self):
        extractor = RelationshipExtractor(mode="auto", nlp_threshold=50)
        chunks = [_chunk("A" * 30), _chunk("B" * 30)]  # 60 total > 50

        mode = extractor._select_mode(chunks)

        assert mode == "nlp"

    def test_explicit_nlp_mode_bypasses_select(self):
        extractor = RelationshipExtractor(mode="nlp", nlp_threshold=500)
        chunk = _chunk("Tiny.")

        # _select_mode would return "llm" for tiny input, but mode is forced
        assert extractor.mode == "nlp"
        assert extractor._select_mode([chunk]) == "llm"


# ---------------------------------------------------------------------------
# Test: deduplication by entity pair
# ---------------------------------------------------------------------------


class TestDeduplicationByEntityPair:
    """Issue #2026: same (src, tgt, type) triple across chunks yields one rel."""

    def test_different_types_not_deduplicated(self, extractor):
        entities = [_entity("FastAPI"), _entity("Redis")]
        # chunk1: no keyword -> RELATES_TO; chunk2: "import" -> USES
        chunk1 = _chunk("FastAPI and Redis are here.")
        chunk2 = _chunk("FastAPI import Redis here.")

        rels = extractor._nlp_extract([chunk1, chunk2], entities)

        types = {r.relationship_type for r in rels}
        assert len(rels) == 2
        assert "RELATES_TO" in types
        assert "USES" in types

    def test_identical_type_across_chunks_deduplicated(self, extractor):
        entities = [_entity("FastAPI"), _entity("Redis")]
        chunk1 = _chunk("FastAPI and Redis co-occur here.")
        chunk2 = _chunk("FastAPI and Redis co-occur here.")

        rels = extractor._nlp_extract([chunk1, chunk2], entities)

        # Same type (RELATES_TO) -> deduplicated to 1
        assert len(rels) == 1

    def test_three_entities_produce_three_pairs(self, extractor):
        entities = [_entity("A"), _entity("B"), _entity("C")]
        chunk = _chunk("A B C are all mentioned here.")

        rels = extractor._nlp_extract([chunk], entities)

        # combinations(3, 2) = 3 pairs
        assert len(rels) == 3

    def test_source_chunk_id_recorded(self, extractor):
        chunk = _chunk("FastAPI and Redis co-occur.")
        entities = [_entity("FastAPI"), _entity("Redis")]

        rels = extractor._nlp_extract([chunk], entities)

        assert len(rels) == 1
        assert chunk.id in rels[0].source_chunk_ids
