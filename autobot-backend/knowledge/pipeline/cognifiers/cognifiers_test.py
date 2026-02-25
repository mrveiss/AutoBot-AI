# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for cognifier _parse_llm_response and conversion logic.

Issue #1075: Test coverage for knowledge pipeline cognifiers.
"""

import json
import sys
from datetime import datetime
from types import ModuleType
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

# Mock llm_interface_pkg before importing cognifiers
_mock_llm = ModuleType("llm_interface_pkg")
_mock_llm.LLMInterface = MagicMock
sys.modules["llm_interface_pkg"] = _mock_llm

from knowledge.pipeline.cognifiers.entity_extractor import EntityExtractor  # noqa: E402
from knowledge.pipeline.cognifiers.event_extractor import EventExtractor  # noqa: E402
from knowledge.pipeline.cognifiers.relationship_extractor import (  # noqa: E402
    SYMMETRIC_RELATIONS,
    RelationshipExtractor,
)
from knowledge.pipeline.cognifiers.summarizer import (  # noqa: E402
    HierarchicalSummarizer,
)
from knowledge.pipeline.models.chunk import ProcessedChunk  # noqa: E402
from knowledge.pipeline.models.entity import Entity  # noqa: E402

# --- Fixtures ---


@pytest.fixture
def entity_extractor():
    return EntityExtractor(batch_size=5)


@pytest.fixture
def relationship_extractor():
    return RelationshipExtractor(batch_size=5)


@pytest.fixture
def event_extractor():
    return EventExtractor(batch_size=5)


@pytest.fixture
def summarizer():
    return HierarchicalSummarizer()


@pytest.fixture
def sample_chunk():
    return ProcessedChunk(
        content="Python is used by Google.",
        document_id=uuid4(),
        chunk_index=0,
    )


@pytest.fixture
def sample_entity():
    doc_id = uuid4()
    return Entity(
        name="Python",
        canonical_name="python",
        entity_type="TECHNOLOGY",
        source_document_id=doc_id,
        source_chunk_ids=[uuid4()],
    )


# --- EntityExtractor Tests ---


class TestEntityExtractorParsing:
    """Tests for EntityExtractor._parse_llm_response."""

    def test_parse_json_array(self, entity_extractor):
        raw = json.dumps([{"name": "Python", "type": "TECHNOLOGY"}])
        result = entity_extractor._parse_llm_response(raw)
        assert len(result) == 1
        assert result[0]["name"] == "Python"

    def test_parse_json_code_block(self, entity_extractor):
        raw = '```json\n[{"name": "Go"}]\n```'
        result = entity_extractor._parse_llm_response(raw)
        assert len(result) == 1
        assert result[0]["name"] == "Go"

    def test_parse_generic_code_block(self, entity_extractor):
        raw = '```\n[{"name": "Rust"}]\n```'
        result = entity_extractor._parse_llm_response(raw)
        assert len(result) == 1
        assert result[0]["name"] == "Rust"

    def test_parse_invalid_json(self, entity_extractor):
        result = entity_extractor._parse_llm_response("not json at all")
        assert result == []

    def test_parse_empty_array(self, entity_extractor):
        result = entity_extractor._parse_llm_response("[]")
        assert result == []


class TestEntityExtractorConversion:
    """Tests for EntityExtractor._convert_to_entities."""

    def test_valid_entity_conversion(self, entity_extractor, sample_chunk):
        raw = [
            {
                "name": "Python",
                "type": "TECHNOLOGY",
                "description": "A language",
                "confidence": 0.9,
            }
        ]
        entities = entity_extractor._convert_to_entities(
            raw, sample_chunk, sample_chunk.document_id
        )
        assert len(entities) == 1
        assert entities[0].name == "Python"
        assert entities[0].entity_type == "TECHNOLOGY"
        assert entities[0].confidence == 0.9

    def test_invalid_type_defaults_concept(self, entity_extractor, sample_chunk):
        raw = [{"name": "X", "type": "INVALID_TYPE"}]
        entities = entity_extractor._convert_to_entities(
            raw, sample_chunk, sample_chunk.document_id
        )
        assert len(entities) == 1
        assert entities[0].entity_type == "CONCEPT"

    def test_missing_name_skipped(self, entity_extractor, sample_chunk):
        raw = [{"type": "PERSON"}]
        entities = entity_extractor._convert_to_entities(
            raw, sample_chunk, sample_chunk.document_id
        )
        assert len(entities) == 0

    def test_default_confidence(self, entity_extractor, sample_chunk):
        raw = [{"name": "Test"}]
        entities = entity_extractor._convert_to_entities(
            raw, sample_chunk, sample_chunk.document_id
        )
        assert len(entities) == 1
        assert entities[0].confidence == 0.8


class TestEntityExtractorMerge:
    """Tests for EntityExtractor._merge_entities."""

    def test_merge_duplicates(self, entity_extractor):
        doc_id = uuid4()
        e1 = Entity(
            name="Python",
            canonical_name="python",
            entity_type="TECHNOLOGY",
            source_document_id=doc_id,
            source_chunk_ids=[uuid4()],
        )
        e2 = Entity(
            name="Python",
            canonical_name="python",
            entity_type="TECHNOLOGY",
            source_document_id=doc_id,
            source_chunk_ids=[uuid4()],
        )
        merged = entity_extractor._merge_entities([e1, e2])
        assert len(merged) == 1
        assert len(merged[0].source_chunk_ids) == 2
        assert merged[0].extraction_count == 2

    def test_no_merge_different_names(self, entity_extractor):
        doc_id = uuid4()
        e1 = Entity(
            name="Python",
            canonical_name="python",
            entity_type="TECHNOLOGY",
            source_document_id=doc_id,
        )
        e2 = Entity(
            name="Go",
            canonical_name="go",
            entity_type="TECHNOLOGY",
            source_document_id=doc_id,
        )
        merged = entity_extractor._merge_entities([e1, e2])
        assert len(merged) == 2

    def test_confidence_increases_on_merge(self, entity_extractor):
        doc_id = uuid4()
        e1 = Entity(
            name="X",
            canonical_name="x",
            entity_type="CONCEPT",
            source_document_id=doc_id,
            confidence=0.8,
        )
        e2 = Entity(
            name="X",
            canonical_name="x",
            entity_type="CONCEPT",
            source_document_id=doc_id,
            confidence=0.8,
        )
        merged = entity_extractor._merge_entities([e1, e2])
        assert merged[0].confidence == 0.9

    def test_confidence_capped_at_1(self, entity_extractor):
        doc_id = uuid4()
        entities = [
            Entity(
                name="X",
                canonical_name="x",
                entity_type="CONCEPT",
                source_document_id=doc_id,
                confidence=0.95,
            )
            for _ in range(5)
        ]
        merged = entity_extractor._merge_entities(entities)
        assert merged[0].confidence <= 1.0


class TestEntityExtractorNormalize:
    """Tests for EntityExtractor._normalize_name."""

    def test_lowercase(self, entity_extractor):
        assert entity_extractor._normalize_name("Python") == "python"

    def test_strip_whitespace(self, entity_extractor):
        assert entity_extractor._normalize_name("  Go  ") == "go"


# --- RelationshipExtractor Tests ---


class TestRelationshipExtractorParsing:
    """Tests for RelationshipExtractor._parse_llm_response."""

    def test_parse_valid_json(self, relationship_extractor):
        raw = json.dumps([{"source": "A", "target": "B", "type": "USES"}])
        result = relationship_extractor._parse_llm_response(raw)
        assert len(result) == 1
        assert result[0]["source"] == "A"

    def test_parse_code_block(self, relationship_extractor):
        raw = '```json\n[{"source": "X", "target": "Y"}]\n```'
        result = relationship_extractor._parse_llm_response(raw)
        assert len(result) == 1

    def test_parse_invalid(self, relationship_extractor):
        result = relationship_extractor._parse_llm_response("bad data")
        assert result == []


class TestRelationshipExtractorConversion:
    """Tests for RelationshipExtractor._convert_to_relationships."""

    def test_valid_conversion(self, relationship_extractor, sample_chunk):
        doc_id = uuid4()
        entity_a = Entity(
            name="FastAPI",
            canonical_name="fastapi",
            entity_type="TECHNOLOGY",
            source_document_id=doc_id,
        )
        entity_b = Entity(
            name="Python",
            canonical_name="python",
            entity_type="TECHNOLOGY",
            source_document_id=doc_id,
        )
        entity_map = {"fastapi": entity_a, "python": entity_b}

        raw = [
            {
                "source": "FastAPI",
                "target": "Python",
                "type": "DEPENDS_ON",
                "confidence": 0.9,
            }
        ]
        rels = relationship_extractor._convert_to_relationships(
            raw, sample_chunk, entity_map
        )
        assert len(rels) == 1
        assert rels[0].relationship_type == "DEPENDS_ON"
        assert rels[0].source_entity_id == entity_a.id

    def test_unknown_entity_skipped(self, relationship_extractor, sample_chunk):
        raw = [{"source": "Unknown", "target": "Also Unknown", "type": "USES"}]
        rels = relationship_extractor._convert_to_relationships(raw, sample_chunk, {})
        assert len(rels) == 0

    def test_invalid_type_defaults(self, relationship_extractor, sample_chunk):
        doc_id = uuid4()
        e = Entity(
            name="A",
            canonical_name="a",
            entity_type="CONCEPT",
            source_document_id=doc_id,
        )
        entity_map = {"a": e, "b": e}
        raw = [{"source": "A", "target": "B", "type": "MADE_UP"}]
        rels = relationship_extractor._convert_to_relationships(
            raw, sample_chunk, entity_map
        )
        assert len(rels) == 1
        assert rels[0].relationship_type == "RELATES_TO"

    def test_symmetric_relation_is_bidirectional(
        self, relationship_extractor, sample_chunk
    ):
        doc_id = uuid4()
        e = Entity(
            name="A",
            canonical_name="a",
            entity_type="CONCEPT",
            source_document_id=doc_id,
        )
        entity_map = {"a": e, "b": e}
        raw = [{"source": "A", "target": "B", "type": "SIMILAR_TO"}]
        rels = relationship_extractor._convert_to_relationships(
            raw, sample_chunk, entity_map
        )
        assert rels[0].bidirectional is True


class TestSymmetricRelations:
    """Tests for SYMMETRIC_RELATIONS constant."""

    def test_contains_expected_types(self):
        assert "SIMILAR_TO" in SYMMETRIC_RELATIONS
        assert "RELATES_TO" in SYMMETRIC_RELATIONS
        assert "CONTRASTS_WITH" in SYMMETRIC_RELATIONS

    def test_non_symmetric_not_included(self):
        assert "CAUSES" not in SYMMETRIC_RELATIONS
        assert "DEPENDS_ON" not in SYMMETRIC_RELATIONS


# --- EventExtractor Tests ---


class TestEventExtractorParsing:
    """Tests for EventExtractor._parse_llm_response."""

    def test_parse_valid_json(self, event_extractor):
        raw = json.dumps([{"name": "Launch", "temporal_expression": "2024-01-15"}])
        result = event_extractor._parse_llm_response(raw)
        assert len(result) == 1
        assert result[0]["name"] == "Launch"

    def test_parse_code_block(self, event_extractor):
        raw = '```json\n[{"name": "Event"}]\n```'
        result = event_extractor._parse_llm_response(raw)
        assert len(result) == 1

    def test_parse_invalid(self, event_extractor):
        result = event_extractor._parse_llm_response("garbage")
        assert result == []


class TestEventExtractorTemporal:
    """Tests for EventExtractor._parse_temporal."""

    def test_iso_date(self, event_extractor):
        result = event_extractor._parse_temporal("2024-01-15")
        assert result == datetime(2024, 1, 15)

    def test_today(self, event_extractor):
        result = event_extractor._parse_temporal("today")
        assert result is not None
        assert result.date() == datetime.now().date()

    def test_yesterday(self, event_extractor):
        result = event_extractor._parse_temporal("yesterday")
        assert result is not None

    def test_empty_expression(self, event_extractor):
        result = event_extractor._parse_temporal("")
        assert result is None

    def test_unparseable(self, event_extractor):
        result = event_extractor._parse_temporal("next quarter")
        assert result is None

    def test_invalid_iso_date(self, event_extractor):
        result = event_extractor._parse_temporal("2024-13-40")
        assert result is None


class TestEventExtractorConversion:
    """Tests for EventExtractor._convert_to_events."""

    def test_valid_event(self, event_extractor, sample_chunk):
        from backend.knowledge.pipeline.base import PipelineContext

        ctx = PipelineContext()
        ctx.document_id = sample_chunk.document_id
        raw = [
            {
                "name": "Launch",
                "description": "Product launch",
                "temporal_expression": "2024-06-01",
                "temporal_type": "point",
                "event_type": "milestone",
                "confidence": 0.95,
            }
        ]
        events = event_extractor._convert_to_events(raw, sample_chunk, {}, ctx)
        assert len(events) == 1
        assert events[0].name == "Launch"
        assert events[0].event_type == "milestone"
        assert events[0].timestamp == datetime(2024, 6, 1)

    def test_invalid_temporal_type_defaults(self, event_extractor, sample_chunk):
        from backend.knowledge.pipeline.base import PipelineContext

        ctx = PipelineContext()
        ctx.document_id = sample_chunk.document_id
        raw = [{"name": "X", "temporal_type": "INVALID"}]
        events = event_extractor._convert_to_events(raw, sample_chunk, {}, ctx)
        assert len(events) == 1
        assert events[0].temporal_type == "point"

    def test_invalid_event_type_defaults(self, event_extractor, sample_chunk):
        from backend.knowledge.pipeline.base import PipelineContext

        ctx = PipelineContext()
        ctx.document_id = sample_chunk.document_id
        raw = [{"name": "X", "event_type": "MADE_UP"}]
        events = event_extractor._convert_to_events(raw, sample_chunk, {}, ctx)
        assert len(events) == 1
        assert events[0].event_type == "occurrence"

    def test_participants_resolved(self, event_extractor, sample_chunk):
        from backend.knowledge.pipeline.base import PipelineContext

        ctx = PipelineContext()
        ctx.document_id = sample_chunk.document_id
        doc_id = uuid4()
        entity = Entity(
            name="Alice",
            canonical_name="alice",
            entity_type="PERSON",
            source_document_id=doc_id,
        )
        entity_map = {"alice": entity}
        raw = [{"name": "Meeting", "participants": ["Alice", "Unknown"]}]
        events = event_extractor._convert_to_events(raw, sample_chunk, entity_map, ctx)
        assert len(events) == 1
        assert entity.id in events[0].participants


# --- Summarizer Tests ---


class TestSummarizerParsing:
    """Tests for HierarchicalSummarizer._parse_llm_response."""

    def test_parse_valid_json(self, summarizer):
        raw = json.dumps(
            {"summary": "Key points", "key_topics": ["AI"], "key_entities": []}
        )
        result = summarizer._parse_llm_response(raw)
        assert result["summary"] == "Key points"
        assert "AI" in result["key_topics"]

    def test_parse_code_block(self, summarizer):
        raw = '```json\n{"summary": "Test"}\n```'
        result = summarizer._parse_llm_response(raw)
        assert result["summary"] == "Test"

    def test_parse_plain_text_fallback(self, summarizer):
        result = summarizer._parse_llm_response("Just a plain summary.")
        assert result["summary"] == "Just a plain summary."
        assert result["key_topics"] == []

    def test_parse_empty(self, summarizer):
        result = summarizer._parse_llm_response("")
        assert result["summary"] == ""


class TestSummarizerGrouping:
    """Tests for HierarchicalSummarizer._group_into_sections."""

    def test_even_groups(self, summarizer):
        summarizer.section_size = 2
        chunks = [
            ProcessedChunk(content=f"Chunk {i}", document_id=uuid4(), chunk_index=i)
            for i in range(4)
        ]
        sections = summarizer._group_into_sections(chunks)
        assert len(sections) == 2
        assert len(sections[0]) == 2

    def test_uneven_groups(self, summarizer):
        summarizer.section_size = 3
        chunks = [
            ProcessedChunk(content=f"Chunk {i}", document_id=uuid4(), chunk_index=i)
            for i in range(5)
        ]
        sections = summarizer._group_into_sections(chunks)
        assert len(sections) == 2
        assert len(sections[0]) == 3
        assert len(sections[1]) == 2

    def test_empty_chunks(self, summarizer):
        sections = summarizer._group_into_sections([])
        assert sections == []


class TestSummarizerEntityResolution:
    """Tests for HierarchicalSummarizer._resolve_entity_ids."""

    def test_resolves_known_entities(self, summarizer):
        doc_id = uuid4()
        entity = Entity(
            name="Redis",
            canonical_name="redis",
            entity_type="TECHNOLOGY",
            source_document_id=doc_id,
        )
        entity_map = {"redis": entity}
        ids = summarizer._resolve_entity_ids(["Redis"], entity_map)
        assert entity.id in ids

    def test_ignores_unknown_entities(self, summarizer):
        ids = summarizer._resolve_entity_ids(["Unknown"], {})
        assert ids == []

    def test_empty_list(self, summarizer):
        ids = summarizer._resolve_entity_ids([], {})
        assert ids == []
