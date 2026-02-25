# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Integration tests for PipelineRunner with mock tasks.

Issue #1075: Test coverage for knowledge pipeline runner.
"""

import logging
from typing import Any
from uuid import uuid4

import pytest
from knowledge.pipeline.base import (
    BaseCognifier,
    BaseExtractor,
    BaseLoader,
    PipelineContext,
    PipelineResult,
)
from knowledge.pipeline.models.chunk import ProcessedChunk
from knowledge.pipeline.models.entity import Entity
from knowledge.pipeline.registry import TaskRegistry
from knowledge.pipeline.runner import PipelineRunner

logger = logging.getLogger(__name__)


# --- Mock Tasks ---


class MockExtractor(BaseExtractor):
    """Test extractor that yields fixed chunks."""

    def __init__(self, chunk_count: int = 3) -> None:
        self.chunk_count = chunk_count

    async def process(self, input_data: Any, context: PipelineContext):
        doc_id = context.document_id or uuid4()
        for i in range(self.chunk_count):
            yield ProcessedChunk(
                content=f"Chunk {i}: {input_data}",
                document_id=doc_id,
                chunk_index=i,
            )


class MockCognifier(BaseCognifier):
    """Test cognifier that creates an entity per chunk."""

    async def process(self, context: PipelineContext) -> PipelineContext:
        doc_id = context.document_id or uuid4()
        for chunk in context.chunks:
            context.entities.append(
                Entity(
                    name=f"Entity from {chunk.chunk_index}",
                    canonical_name=f"entity_{chunk.chunk_index}",
                    entity_type="CONCEPT",
                    source_document_id=doc_id,
                    source_chunk_ids=[chunk.id],
                )
            )
        return context


class MockLoader(BaseLoader):
    """Test loader that records load calls."""

    loaded_contexts: list = []

    async def load(self, context: PipelineContext) -> None:
        MockLoader.loaded_contexts.append(context)


class FailingExtractor(BaseExtractor):
    """Extractor that raises an error."""

    async def process(self, input_data: Any, context: PipelineContext):
        raise RuntimeError("Extract failed")
        yield  # noqa: F811 — needed to make this an async generator


# --- Fixtures ---


@pytest.fixture(autouse=True)
def register_mock_tasks():
    """Register mock tasks and clean up after each test."""
    TaskRegistry._extractors["mock_extract"] = MockExtractor
    TaskRegistry._cognifiers["mock_cognify"] = MockCognifier
    TaskRegistry._loaders["mock_load"] = MockLoader
    TaskRegistry._extractors["failing_extract"] = FailingExtractor
    MockLoader.loaded_contexts = []
    yield
    TaskRegistry._extractors.pop("mock_extract", None)
    TaskRegistry._cognifiers.pop("mock_cognify", None)
    TaskRegistry._loaders.pop("mock_load", None)
    TaskRegistry._extractors.pop("failing_extract", None)


@pytest.fixture
def pipeline_config():
    return {
        "name": "test_pipeline",
        "batch_size": 10,
        "extract": [{"task": "mock_extract", "params": {"chunk_count": 2}}],
        "cognify": [{"task": "mock_cognify", "params": {}}],
        "load": [{"task": "mock_load", "params": {}}],
    }


# --- Tests ---


class TestPipelineRunnerInit:
    """Tests for PipelineRunner initialization."""

    def test_default_batch_size(self):
        runner = PipelineRunner({"name": "test"})
        assert runner.batch_size == 10

    def test_custom_batch_size(self):
        runner = PipelineRunner({"name": "test", "batch_size": 25})
        assert runner.batch_size == 25


class TestPipelineRunnerExecution:
    """Tests for PipelineRunner.run end-to-end."""

    @pytest.mark.asyncio
    async def test_full_pipeline(self, pipeline_config):
        runner = PipelineRunner(pipeline_config)
        context = PipelineContext()
        context.document_id = uuid4()
        result = await runner.run("Test document text", context)

        assert isinstance(result, PipelineResult)
        assert result.chunks_processed == 2
        assert result.entities_extracted == 2
        assert result.errors == []
        assert result.duration_seconds > 0
        assert result.completed_at is not None

    @pytest.mark.asyncio
    async def test_loader_receives_data(self, pipeline_config):
        runner = PipelineRunner(pipeline_config)
        context = PipelineContext()
        context.document_id = uuid4()
        await runner.run("Test input", context)

        assert len(MockLoader.loaded_contexts) == 1
        loaded_ctx = MockLoader.loaded_contexts[0]
        assert len(loaded_ctx.entities) == 2

    @pytest.mark.asyncio
    async def test_extract_stage_only(self):
        config = {
            "name": "extract_only",
            "extract": [{"task": "mock_extract", "params": {"chunk_count": 5}}],
            "cognify": [],
            "load": [],
        }
        runner = PipelineRunner(config)
        context = PipelineContext()
        context.document_id = uuid4()
        result = await runner.run("text", context)

        assert result.chunks_processed == 5
        assert result.entities_extracted == 0
        assert result.errors == []

    @pytest.mark.asyncio
    async def test_unknown_extractor_raises(self):
        config = {
            "name": "bad",
            "extract": [{"task": "nonexistent_task", "params": {}}],
        }
        runner = PipelineRunner(config)
        context = PipelineContext()
        result = await runner.run("text", context)

        assert len(result.errors) == 1
        assert "nonexistent_task" in result.errors[0]

    @pytest.mark.asyncio
    async def test_unknown_cognifier_raises(self):
        config = {
            "name": "bad",
            "extract": [{"task": "mock_extract", "params": {"chunk_count": 1}}],
            "cognify": [{"task": "nonexistent_cognify", "params": {}}],
        }
        runner = PipelineRunner(config)
        context = PipelineContext()
        result = await runner.run("text", context)

        assert len(result.errors) == 1

    @pytest.mark.asyncio
    async def test_unknown_loader_raises(self):
        config = {
            "name": "bad",
            "extract": [{"task": "mock_extract", "params": {"chunk_count": 1}}],
            "cognify": [],
            "load": [{"task": "nonexistent_loader", "params": {}}],
        }
        runner = PipelineRunner(config)
        context = PipelineContext()
        result = await runner.run("text", context)

        assert len(result.errors) == 1

    @pytest.mark.asyncio
    async def test_extract_error_captured(self):
        config = {
            "name": "failing",
            "extract": [{"task": "failing_extract", "params": {}}],
        }
        runner = PipelineRunner(config)
        context = PipelineContext()
        result = await runner.run("text", context)

        assert len(result.errors) == 1
        assert "Extract failed" in result.errors[0]


class TestPipelineResultProperties:
    """Tests for PipelineResult computed properties."""

    def test_aliases(self):
        result = PipelineResult(document_id=uuid4())
        result.entities_extracted = 5
        result.relationships_extracted = 3
        result.events_extracted = 2
        result.summaries_generated = 1
        result.chunks_processed = 10

        assert result.entities_count == 5
        assert result.relationships_count == 3
        assert result.events_count == 2
        assert result.summaries_count == 1
        assert result.chunks_count == 10

    def test_stages_completed_all(self):
        result = PipelineResult()
        result.chunks_processed = 10
        result.entities_extracted = 5
        assert result.stages_completed == ["extract", "cognify", "load"]

    def test_stages_completed_extract_only(self):
        result = PipelineResult()
        result.chunks_processed = 10
        assert result.stages_completed == ["extract", "load"]

    def test_stages_completed_with_errors(self):
        result = PipelineResult()
        result.chunks_processed = 10
        result.entities_extracted = 5
        result.errors.append("oops")
        assert "load" not in result.stages_completed
        assert "extract" in result.stages_completed
