# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for pipeline data models.

Issue #759: Knowledge Pipeline Foundation - Extract, Cognify, Load (ECL).
"""

from uuid import uuid4

import pytest

from backend.knowledge.pipeline.models.chunk import ProcessedChunk
from backend.knowledge.pipeline.models.entity import Entity
from backend.knowledge.pipeline.models.event import TemporalEvent
from backend.knowledge.pipeline.models.relationship import Relationship
from backend.knowledge.pipeline.models.summary import Summary


class TestProcessedChunk:
    """Tests for ProcessedChunk model."""

    def test_create_chunk(self):
        doc_id = uuid4()
        chunk = ProcessedChunk(
            content="Test content",
            document_id=doc_id,
            chunk_index=0,
        )
        assert chunk.content == "Test content"
        assert chunk.document_id == doc_id
        assert chunk.chunk_index == 0
        assert chunk.id is not None

    def test_chunk_defaults(self):
        chunk = ProcessedChunk(
            content="Test",
            document_id=uuid4(),
            chunk_index=0,
        )
        assert chunk.metadata == {}
        assert chunk.document_type == "unknown"
        assert chunk.start_offset == 0
        assert chunk.end_offset == 0

    def test_chunk_serialization(self):
        chunk = ProcessedChunk(
            content="Hello",
            document_id=uuid4(),
            chunk_index=1,
            document_type="technical",
        )
        data = chunk.model_dump(mode="json")
        assert data["content"] == "Hello"
        assert data["chunk_index"] == 1
        assert data["document_type"] == "technical"


class TestEntity:
    """Tests for Entity model."""

    def test_create_entity(self):
        doc_id = uuid4()
        entity = Entity(
            name="Python",
            canonical_name="python",
            entity_type="TECHNOLOGY",
            source_document_id=doc_id,
        )
        assert entity.name == "Python"
        assert entity.canonical_name == "python"
        assert entity.entity_type == "TECHNOLOGY"

    def test_entity_defaults(self):
        entity = Entity(
            name="Test",
            canonical_name="test",
            entity_type="CONCEPT",
            source_document_id=uuid4(),
        )
        assert entity.confidence == 1.0
        assert entity.extraction_count == 1
        assert entity.description == ""
        assert entity.properties == {}
        assert entity.source_chunk_ids == []

    def test_entity_confidence_bounds(self):
        entity = Entity(
            name="Test",
            canonical_name="test",
            entity_type="PERSON",
            source_document_id=uuid4(),
            confidence=0.95,
        )
        assert entity.confidence == 0.95

    def test_entity_confidence_invalid_high(self):
        with pytest.raises(Exception):
            Entity(
                name="Test",
                canonical_name="test",
                entity_type="PERSON",
                source_document_id=uuid4(),
                confidence=1.5,
            )

    def test_entity_serialization(self):
        entity = Entity(
            name="AutoBot",
            canonical_name="autobot",
            entity_type="TECHNOLOGY",
            source_document_id=uuid4(),
        )
        data = entity.model_dump(mode="json")
        assert data["name"] == "AutoBot"
        assert data["entity_type"] == "TECHNOLOGY"
        assert "id" in data


class TestRelationship:
    """Tests for Relationship model."""

    def test_create_relationship(self):
        rel = Relationship(
            source_entity_id=uuid4(),
            target_entity_id=uuid4(),
            relationship_type="USES",
        )
        assert rel.relationship_type == "USES"
        assert rel.id is not None

    def test_relationship_defaults(self):
        rel = Relationship(
            source_entity_id=uuid4(),
            target_entity_id=uuid4(),
            relationship_type="RELATES_TO",
        )
        assert rel.confidence == 1.0
        assert rel.bidirectional is False
        assert rel.description == ""

    def test_bidirectional_relationship(self):
        rel = Relationship(
            source_entity_id=uuid4(),
            target_entity_id=uuid4(),
            relationship_type="SIMILAR_TO",
            bidirectional=True,
        )
        assert rel.bidirectional is True


class TestTemporalEvent:
    """Tests for TemporalEvent model."""

    def test_create_event(self):
        event = TemporalEvent(
            name="Release v1.0",
            description="First stable release",
            source_document_id=uuid4(),
        )
        assert event.name == "Release v1.0"
        assert event.id is not None

    def test_event_defaults(self):
        event = TemporalEvent(
            name="Test",
            source_document_id=uuid4(),
        )
        assert event.temporal_type == "point"
        assert event.event_type == "occurrence"
        assert event.participants == []
        assert event.confidence == 1.0

    def test_event_with_timestamp(self):
        from datetime import datetime

        now = datetime.utcnow()
        event = TemporalEvent(
            name="Test",
            source_document_id=uuid4(),
            timestamp=now,
        )
        assert event.timestamp == now


class TestSummary:
    """Tests for Summary model."""

    def test_create_summary(self):
        summary = Summary(
            content="Test summary text",
            level="document",
            source_document_id=uuid4(),
        )
        assert summary.content == "Test summary text"
        assert summary.level == "document"

    def test_summary_defaults(self):
        summary = Summary(
            content="Test",
            level="chunk",
            source_document_id=uuid4(),
        )
        assert summary.key_topics == []
        assert summary.key_entities == []
        assert summary.source_chunk_ids == []
        assert summary.parent_summary_id is None
        assert summary.child_summary_ids == []

    def test_summary_hierarchy(self):
        parent_id = uuid4()
        child_id = uuid4()
        summary = Summary(
            content="Section summary",
            level="section",
            source_document_id=uuid4(),
            parent_summary_id=parent_id,
            child_summary_ids=[child_id],
        )
        assert summary.parent_summary_id == parent_id
        assert child_id in summary.child_summary_ids
