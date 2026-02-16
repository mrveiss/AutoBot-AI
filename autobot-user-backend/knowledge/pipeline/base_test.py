# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for pipeline base classes and models.

Issue #759: Knowledge Pipeline Foundation - Extract, Cognify, Load (ECL).
"""

from datetime import datetime
from uuid import uuid4

import pytest

from backend.knowledge.pipeline.base import (
    BaseCognifier,
    BaseExtractor,
    BaseLoader,
    PipelineContext,
    PipelineResult,
)


class TestPipelineContext:
    """Tests for PipelineContext."""

    def test_init_defaults(self):
        ctx = PipelineContext()
        assert ctx.chunks == []
        assert ctx.entities == []
        assert ctx.relationships == []
        assert ctx.events == []
        assert ctx.summaries == []
        assert ctx.metadata == {}
        assert ctx.document_id is None

    def test_set_document_id(self):
        ctx = PipelineContext()
        doc_id = uuid4()
        ctx.document_id = doc_id
        assert ctx.document_id == doc_id

    def test_add_chunks(self):
        ctx = PipelineContext()
        ctx.chunks.append({"id": "c1", "content": "test"})
        assert len(ctx.chunks) == 1

    def test_metadata_mutable(self):
        ctx = PipelineContext()
        ctx.metadata["key"] = "value"
        assert ctx.metadata["key"] == "value"


class TestPipelineResult:
    """Tests for PipelineResult."""

    def test_init_defaults(self):
        result = PipelineResult()
        assert result.document_id is None
        assert result.chunks_processed == 0
        assert result.entities_extracted == 0
        assert result.relationships_extracted == 0
        assert result.events_extracted == 0
        assert result.summaries_generated == 0
        assert result.errors == []
        assert result.duration_seconds == 0.0

    def test_init_with_params(self):
        doc_id = uuid4()
        now = datetime.utcnow()
        result = PipelineResult(document_id=doc_id, started_at=now)
        assert result.document_id == doc_id
        assert result.started_at == now

    def test_entities_count_alias(self):
        result = PipelineResult()
        result.entities_extracted = 42
        assert result.entities_count == 42

    def test_relationships_count_alias(self):
        result = PipelineResult()
        result.relationships_extracted = 15
        assert result.relationships_count == 15

    def test_events_count_alias(self):
        result = PipelineResult()
        result.events_extracted = 8
        assert result.events_count == 8

    def test_summaries_count_alias(self):
        result = PipelineResult()
        result.summaries_generated = 3
        assert result.summaries_count == 3

    def test_chunks_count_alias(self):
        result = PipelineResult()
        result.chunks_processed = 20
        assert result.chunks_count == 20

    def test_stages_completed_none(self):
        result = PipelineResult()
        assert result.stages_completed == []

    def test_stages_completed_extract_only(self):
        result = PipelineResult()
        result.chunks_processed = 5
        stages = result.stages_completed
        assert "extract" in stages

    def test_stages_completed_all(self):
        result = PipelineResult()
        result.chunks_processed = 5
        result.entities_extracted = 3
        stages = result.stages_completed
        assert "extract" in stages
        assert "cognify" in stages
        assert "load" in stages

    def test_stages_with_errors_no_load(self):
        result = PipelineResult()
        result.chunks_processed = 5
        result.entities_extracted = 3
        result.errors.append("Load failed")
        stages = result.stages_completed
        assert "extract" in stages
        assert "cognify" in stages
        assert "load" not in stages

    def test_error_accumulation(self):
        result = PipelineResult()
        result.errors.append("Error 1")
        result.errors.append("Error 2")
        assert len(result.errors) == 2


class TestBaseClasses:
    """Tests for abstract base classes."""

    def test_base_extractor_is_abstract(self):
        with pytest.raises(TypeError):
            BaseExtractor()

    def test_base_cognifier_is_abstract(self):
        with pytest.raises(TypeError):
            BaseCognifier()

    def test_base_loader_is_abstract(self):
        with pytest.raises(TypeError):
            BaseLoader()

    def test_extractor_subclass(self):
        class TestExtractor(BaseExtractor):
            async def process(self, input_data, context):
                return [input_data]

        ext = TestExtractor()
        assert isinstance(ext, BaseExtractor)

    def test_cognifier_subclass(self):
        class TestCognifier(BaseCognifier):
            async def process(self, context):
                return context

        cog = TestCognifier()
        assert isinstance(cog, BaseCognifier)

    def test_loader_subclass(self):
        class TestLoader(BaseLoader):
            async def load(self, context):
                pass

        ldr = TestLoader()
        assert isinstance(ldr, BaseLoader)
