# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
IDE Integration Tests (Issue #906)

Tests for code completion endpoint.
"""

from unittest.mock import MagicMock, patch

import pytest

from backend.api.ide_integration import (
    CompletionItem,
    CompletionItemKind,
    CompletionRequest,
    IDEIntegrationEngine,
)
from backend.models.completion_context import CompletionContext


@pytest.fixture
def engine():
    """Create IDE integration engine for testing."""
    return IDEIntegrationEngine()


@pytest.fixture
def sample_request():
    """Create sample completion request."""
    return CompletionRequest(
        file_path="test.py",
        content="import logging\n\nlogger = logging.getLogger(__name__)\n\ndef test():\n    x = ",
        cursor_line=4,
        cursor_position=8,
        language="python",
        max_completions=10,
    )


@pytest.fixture
def sample_context():
    """Create sample completion context."""
    return CompletionContext(
        context_id="test_ctx",
        file_path="test.py",
        language="python",
        imports=["import logging"],
        current_function="test",
        cursor_line="    x = ",
        cursor_position=8,
        partial_statement="    x = ",
        detected_frameworks=set(),
    )


@pytest.mark.anyio
@patch("backend.api.ide_integration.context_analyzer")
@patch("backend.api.ide_integration.redis_client")
async def test_completion_caching(
    mock_redis, mock_analyzer, engine, sample_request, sample_context
):
    """Test completion result caching."""
    # Setup mocks
    mock_redis.get.return_value = None
    mock_analyzer.analyze.return_value = sample_context

    # First request - not cached
    response1 = await engine.complete(sample_request)
    assert not response1.cached
    assert mock_redis.setex.called

    # Second request - cached
    cached_data = [
        {
            "label": "cached_item",
            "kind": "Text",
            "detail": None,
            "documentation": None,
            "insert_text": None,
            "sort_text": None,
            "score": 0.5,
        }
    ]
    mock_redis.get.return_value = str(cached_data).encode()
    mock_redis.reset_mock()

    response2 = await engine.complete(sample_request)
    assert response2.cached
    assert not mock_redis.setex.called


@pytest.mark.anyio
@patch("backend.api.ide_integration.context_analyzer")
@patch("backend.api.ide_integration.redis_client")
@patch("backend.api.ide_integration.trainer")
async def test_ml_completions(
    mock_trainer, mock_redis, mock_analyzer, engine, sample_request, sample_context
):
    """Test ML-based completions."""
    # Setup mocks
    mock_redis.get.return_value = None
    mock_analyzer.analyze.return_value = sample_context

    mock_model = MagicMock()
    mock_model.predict.return_value = [
        {"text": "result = func()", "score": 0.95},
        {"text": "data = load_data()", "score": 0.85},
    ]
    mock_trainer.load_model.return_value = mock_model

    response = await engine.complete(sample_request)

    assert response.source == "ml"
    assert len(response.completions) >= 2
    assert response.completions[0].label == "result = func()"
    assert response.completions[0].score == 0.95


@pytest.mark.anyio
@patch("backend.api.ide_integration.context_analyzer")
@patch("backend.api.ide_integration.redis_client")
@patch("backend.api.ide_integration.pattern_extractor")
async def test_pattern_completions(
    mock_extractor, mock_redis, mock_analyzer, engine, sample_request, sample_context
):
    """Test pattern-based completions."""
    # Setup mocks
    mock_redis.get.return_value = None
    mock_analyzer.analyze.return_value = sample_context

    from backend.models.code_pattern import CodePattern, PatternCategory

    mock_patterns = [
        CodePattern(
            pattern_id="p1",
            language="python",
            category=PatternCategory.FUNCTION_CALL,
            pattern_text="logger.info('message')",
            frequency=50,
        ),
        CodePattern(
            pattern_id="p2",
            language="python",
            category=PatternCategory.VARIABLE_ASSIGNMENT,
            pattern_text="result = calculate()",
            frequency=30,
        ),
    ]
    mock_extractor.extract_patterns.return_value = mock_patterns

    response = await engine.complete(sample_request)

    assert len(response.completions) >= 2
    assert any("logger.info" in c.label for c in response.completions)


def test_completion_kind_inference(engine, sample_context):
    """Test completion kind inference."""
    assert (
        engine._infer_completion_kind("def test():", sample_context)
        == CompletionItemKind.FUNCTION
    )
    assert (
        engine._infer_completion_kind("class MyClass:", sample_context)
        == CompletionItemKind.CLASS
    )
    assert (
        engine._infer_completion_kind("import os", sample_context)
        == CompletionItemKind.MODULE
    )
    assert (
        engine._infer_completion_kind("MAX_SIZE", sample_context)
        == CompletionItemKind.CONSTANT
    )


def test_completion_ranking(engine):
    """Test completion ranking by score."""
    completions = [
        CompletionItem(label="low", kind=CompletionItemKind.TEXT, score=0.3),
        CompletionItem(label="high", kind=CompletionItemKind.TEXT, score=0.9),
        CompletionItem(label="medium", kind=CompletionItemKind.TEXT, score=0.6),
    ]

    from backend.models.completion_context import CompletionContext

    context = CompletionContext(context_id="test", language="python")
    ranked = engine._rank_completions(completions, context)

    assert ranked[0].label == "high"
    assert ranked[1].label == "medium"
    assert ranked[2].label == "low"


@pytest.mark.anyio
@patch("backend.api.ide_integration.context_analyzer")
@patch("backend.api.ide_integration.redis_client")
async def test_completion_max_limit(mock_redis, mock_analyzer, engine, sample_context):
    """Test completion result limit."""
    # Setup mocks
    mock_redis.get.return_value = None
    mock_analyzer.analyze.return_value = sample_context

    request = CompletionRequest(
        file_path="test.py",
        content="def test():\n    x = ",
        cursor_line=1,
        cursor_position=8,
        max_completions=5,
    )

    response = await engine.complete(request)

    # Should respect max_completions limit
    assert len(response.completions) <= 5


@pytest.mark.anyio
@patch("backend.api.ide_integration.context_analyzer")
@patch("backend.api.ide_integration.redis_client")
@patch("backend.api.ide_integration.trainer")
async def test_ml_timeout_fallback(
    mock_trainer, mock_redis, mock_analyzer, engine, sample_request, sample_context
):
    """Test fallback to patterns when ML times out."""
    import time

    # Setup mocks
    mock_redis.get.return_value = None
    mock_analyzer.analyze.return_value = sample_context

    # Simulate slow ML model
    def slow_predict(features):
        time.sleep(0.06)  # 60ms - exceeds 50ms timeout
        return []

    mock_model = MagicMock()
    mock_model.predict = slow_predict
    mock_trainer.load_model.return_value = mock_model

    response = await engine.complete(sample_request)

    # Should fall back to patterns
    assert response.source == "patterns"


def test_pattern_relevance_filtering(engine):
    """Test pattern filtering by relevance."""
    from backend.models.code_pattern import CodePattern, PatternCategory
    from backend.models.completion_context import CompletionContext

    pattern_python = CodePattern(
        pattern_id="p1",
        language="python",
        category=PatternCategory.FUNCTION_CALL,
        pattern_text="test()",
        frequency=10,
    )

    pattern_javascript = CodePattern(
        pattern_id="p2",
        language="javascript",
        category=PatternCategory.FUNCTION_CALL,
        pattern_text="test()",
        frequency=10,
    )

    context_python = CompletionContext(context_id="test", language="python")

    # Python pattern should be relevant
    assert engine._is_pattern_relevant(pattern_python, context_python)

    # JavaScript pattern should not be relevant
    assert not engine._is_pattern_relevant(pattern_javascript, context_python)


@pytest.mark.anyio
@patch("backend.api.ide_integration.context_analyzer")
@patch("backend.api.ide_integration.redis_client")
async def test_completion_performance(
    mock_redis, mock_analyzer, engine, sample_request, sample_context
):
    """Test completion response time."""
    # Setup mocks
    mock_redis.get.return_value = None
    mock_analyzer.analyze.return_value = sample_context

    response = await engine.complete(sample_request)

    # Should complete within reasonable time (< 200ms)
    assert response.completion_time_ms < 200
