# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
IDE Integration Tests (Issue #906)

Tests for code completion endpoint.
"""

from unittest.mock import MagicMock, patch

import pytest

from api.ide_integration import (
    CompletionItem,
    CompletionItemKind,
    CompletionRequest,
    IDEIntegrationEngine,
)
from models.completion_context import CompletionContext

# ---------------------------------------------------------------------------
# Deterministic clock for the ML latency gate (#15861)
# ---------------------------------------------------------------------------
#
# `_gather_completions` keeps ML completions only when the call returned within
# `_ML_LATENCY_BUDGET_MS` of wall clock. A test that asserts on the ML path
# while letting the real clock run is asserting that this machine was fast
# enough at that instant -- which is why `test_ml_completions` failed on a PR
# whose diff touched neither this module nor anything it imports: `-n auto
# --dist loadscope` put enough load on the worker to cross the threshold.
#
# So the clock is controlled rather than raced. `time.time` reads a value this
# test moves, and the mocked prediction advances it by exactly the elapsed time
# under test. Extra `time.time()` calls elsewhere in the path read the same
# value and cannot perturb the measurement.

_ML_LATENCY_BUDGET_MS = 50


class _ControlledClock:
    """A `time.time` replacement whose value only moves when a test moves it."""

    def __init__(self) -> None:
        self.now = 1_000_000.0

    def __call__(self) -> float:
        return self.now

    def advance_ms(self, milliseconds: float) -> None:
        self.now += milliseconds / 1000.0


def _ml_model_taking_ms(clock: _ControlledClock, elapsed_ms: float) -> MagicMock:
    """A model whose prediction 'takes' `elapsed_ms` on the controlled clock."""
    model = MagicMock()

    def _predict(_features):
        clock.advance_ms(elapsed_ms)
        return [
            {"text": "result = func()", "score": 0.95},
            {"text": "data = load_data()", "score": 0.85},
        ]

    model.predict.side_effect = _predict
    return model


@pytest.fixture
def engine():
    """Create IDE integration engine for testing."""
    return IDEIntegrationEngine()


@pytest.fixture
def sample_request():
    """Create sample completion request."""
    return CompletionRequest(
        file_path="test.py",
        content="import logging\n\nlogger = get_logger(__name__)\n\ndef test():\n    x = ",
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
@patch("api.ide_integration._get_context_analyzer")
@patch("api.ide_integration._get_redis_client")
async def test_completion_caching(mock_get_redis, mock_get_analyzer, engine, sample_request, sample_context):
    """Test completion result caching."""
    # Setup mocks — the module reaches Redis and the analyzer through lazy
    # singleton accessors, so the accessor is patched and its return value
    # is the client the engine actually talks to.
    mock_redis = mock_get_redis.return_value
    mock_analyzer = mock_get_analyzer.return_value
    mock_redis.get.return_value = None
    mock_analyzer.analyze.return_value = sample_context

    # First request - not cached
    response1 = await engine.complete(sample_request)
    assert not response1.cached
    assert mock_redis.setex.called

    # Second request - cached
    import json as json_lib

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
    mock_redis.get.return_value = json_lib.dumps(cached_data).encode()
    mock_redis.reset_mock()

    response2 = await engine.complete(sample_request)
    assert response2.cached
    assert not mock_redis.setex.called


@pytest.mark.anyio
@patch("api.ide_integration.HAS_ML", True)
@patch("api.ide_integration._get_context_analyzer")
@patch("api.ide_integration._get_redis_client")
@patch("api.ide_integration._get_trainer")
async def test_ml_completions(
    mock_get_trainer, mock_get_redis, mock_get_analyzer, engine, sample_request, sample_context
):
    """Test ML-based completions."""
    # Setup mocks
    mock_trainer = mock_get_trainer.return_value
    mock_redis = mock_get_redis.return_value
    mock_analyzer = mock_get_analyzer.return_value
    mock_redis.get.return_value = None
    mock_analyzer.analyze.return_value = sample_context

    # #15861: inside the budget, on a clock this test controls. Previously this
    # raced the real clock and failed whenever the worker was loaded enough to
    # cross 50ms -- which reads exactly like a test-ordering bug and is not one.
    clock = _ControlledClock()
    mock_trainer.load_model.return_value = _ml_model_taking_ms(clock, _ML_LATENCY_BUDGET_MS - 10)

    with patch("time.time", clock):
        response = await engine.complete(sample_request)

    # Should use ML if available and model returns results
    assert len(response.completions) >= 2
    completion_texts = [c.label for c in response.completions]
    assert any("result = func()" in text or "result" in text for text in completion_texts)
    assert response.source == "ml"


@pytest.mark.anyio
@patch("api.ide_integration.HAS_ML", True)
@patch("api.ide_integration._get_context_analyzer")
@patch("api.ide_integration._get_redis_client")
@patch("api.ide_integration._get_trainer")
async def test_ml_completions_over_the_latency_budget_are_dropped(
    mock_get_trainer, mock_get_redis, mock_get_analyzer, engine, sample_request, sample_context
):
    """The contrast case, and the behaviour that made #15861 look like pollution.

    A prediction that took longer than the budget is discarded even though it
    succeeded. Without this test the gate is untested in the direction it
    actually fires, and `test_ml_completions` above would pass just as happily
    against code with no gate at all.
    """
    mock_trainer = mock_get_trainer.return_value
    mock_redis = mock_get_redis.return_value
    mock_analyzer = mock_get_analyzer.return_value
    mock_redis.get.return_value = None
    mock_analyzer.analyze.return_value = sample_context

    clock = _ControlledClock()
    mock_trainer.load_model.return_value = _ml_model_taking_ms(clock, _ML_LATENCY_BUDGET_MS + 10)

    with patch("time.time", clock):
        response = await engine.complete(sample_request)

    completion_texts = [c.label for c in response.completions]
    assert not any("result = func()" in text for text in completion_texts), (
        "an ML completion over the latency budget was kept; the gate at "
        "ide_integration.py:705 is what this test exists to pin"
    )
    assert response.source == "patterns"


@pytest.mark.anyio
@patch("api.ide_integration._get_context_analyzer")
@patch("api.ide_integration._get_redis_client")
async def test_pattern_completions(mock_get_redis, mock_get_analyzer, engine, sample_request, sample_context):
    """Test pattern-based completions."""
    # Setup mocks
    mock_redis = mock_get_redis.return_value
    mock_analyzer = mock_get_analyzer.return_value
    mock_redis.get.return_value = None

    # Context with logging import to trigger logging completions
    context_with_logging = CompletionContext(
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
    mock_analyzer.analyze.return_value = context_with_logging

    response = await engine.complete(sample_request)

    # Should get pattern-based completions (logging patterns)
    assert len(response.completions) > 0
    # Check for logging completions
    labels = [c.label for c in response.completions]
    assert any("logger" in label.lower() for label in labels)


def test_completion_kind_inference(engine, sample_context):
    """Test completion kind inference."""
    assert engine._infer_completion_kind("def test():", sample_context) == CompletionItemKind.FUNCTION
    assert engine._infer_completion_kind("class MyClass:", sample_context) == CompletionItemKind.CLASS
    assert engine._infer_completion_kind("import os", sample_context) == CompletionItemKind.MODULE
    assert engine._infer_completion_kind("MAX_SIZE", sample_context) == CompletionItemKind.CONSTANT


def test_completion_ranking(engine):
    """Test completion ranking by score."""
    completions = [
        CompletionItem(label="low", kind=CompletionItemKind.TEXT, score=0.3),
        CompletionItem(label="high", kind=CompletionItemKind.TEXT, score=0.9),
        CompletionItem(label="medium", kind=CompletionItemKind.TEXT, score=0.6),
    ]

    from models.completion_context import CompletionContext

    context = CompletionContext(context_id="test", language="python")
    ranked = engine._rank_completions(completions, context)

    assert ranked[0].label == "high"
    assert ranked[1].label == "medium"
    assert ranked[2].label == "low"


@pytest.mark.anyio
@patch("api.ide_integration._get_context_analyzer")
@patch("api.ide_integration._get_redis_client")
async def test_completion_max_limit(mock_get_redis, mock_get_analyzer, engine, sample_context):
    """Test completion result limit."""
    # Setup mocks
    mock_redis = mock_get_redis.return_value
    mock_analyzer = mock_get_analyzer.return_value
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
@patch("api.ide_integration._get_context_analyzer")
@patch("api.ide_integration._get_redis_client")
@patch("api.ide_integration._get_trainer")
async def test_ml_timeout_fallback(
    mock_get_trainer, mock_get_redis, mock_get_analyzer, engine, sample_request, sample_context
):
    """Test fallback to patterns when ML times out."""
    import time

    # Setup mocks
    mock_trainer = mock_get_trainer.return_value
    mock_redis = mock_get_redis.return_value
    mock_analyzer = mock_get_analyzer.return_value
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
    """Test completion filtering by context."""
    from models.completion_context import CompletionContext

    # Test FastAPI completions are returned when fastapi in frameworks
    context_with_fastapi = CompletionContext(context_id="test", language="python", detected_frameworks={"fastapi"})

    fastapi_completions = engine._get_fastapi_completions(context_with_fastapi)
    assert len(fastapi_completions) > 0
    assert any("@router" in c.label for c in fastapi_completions)

    # Test logging completions are context-aware
    context_with_logging = CompletionContext(
        context_id="test",
        language="python",
        imports=["import logging"],
        detected_frameworks=set(),
    )

    logging_completions = engine._get_logging_completions(context_with_logging)
    assert len(logging_completions) > 0
    assert any("logger" in c.label.lower() for c in logging_completions)


@pytest.mark.anyio
@patch("api.ide_integration._get_context_analyzer")
@patch("api.ide_integration._get_redis_client")
async def test_completion_performance(mock_get_redis, mock_get_analyzer, engine, sample_request, sample_context):
    """Test completion response time."""
    # Setup mocks
    mock_redis = mock_get_redis.return_value
    mock_analyzer = mock_get_analyzer.return_value
    mock_redis.get.return_value = None
    mock_analyzer.analyze.return_value = sample_context

    response = await engine.complete(sample_request)

    # Should complete within reasonable time (< 200ms)
    assert response.completion_time_ms < 200
