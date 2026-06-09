# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for root cause analysis API endpoint and RootCauseAnalyzer service.

Issue #4068: Tests root cause analysis via causal chain traversal.

Tests cover:
- RootCauseAnalyzer.analyze_task_failure() with mocked TemporalSearchService
- CausalEvent and RootCauseReport dataclass serialization
- Confounder detection (multi-factor failures)
- Confidence score calculation
- API endpoint /api/analytics/root-cause/{task_id}
- Error handling (missing task, failed analysis, etc.)
"""

from unittest.mock import AsyncMock, patch

import pytest

from services.root_cause_analyzer import (
    CausalEvent,
    RootCauseAnalyzer,
    RootCauseReport,
)


class TestCausalEvent:
    """Tests for CausalEvent dataclass."""

    def test_creation_with_required_fields(self):
        """CausalEvent should be creatable with required fields."""
        event = CausalEvent(
            event_id="test-event-1",
            event_type="error",
            name="Database connection failed",
            description="Unable to connect to PostgreSQL",
            timestamp="2026-04-10T12:00:00Z",
        )
        assert event.event_id == "test-event-1"
        assert event.event_type == "error"
        assert event.confidence == 1.0
        assert event.depth == 0
        assert event.participants == []

    def test_creation_with_all_fields(self):
        """CausalEvent should accept all optional fields."""
        event = CausalEvent(
            event_id="test-event-2",
            event_type="warning",
            name="High memory usage",
            description="Memory exceeded threshold",
            timestamp="2026-04-10T11:50:00Z",
            confidence=0.8,
            depth=2,
            participants=["service-a", "service-b"],
        )
        assert event.depth == 2
        assert event.confidence == 0.8
        assert len(event.participants) == 2


class TestRootCauseReport:
    """Tests for RootCauseReport dataclass."""

    def test_empty_report_creation(self):
        """Empty report should be valid."""
        report = RootCauseReport(task_id="task-123")
        assert report.task_id == "task-123"
        assert report.root_event is None
        assert report.causal_chain == []
        assert report.confidence == 0.0
        assert report.analysis_status == "success"

    def test_report_to_dict_serialization(self):
        """Report should serialize to dict for API response."""
        root = CausalEvent(
            event_id="root-1",
            event_type="failure",
            name="Root cause",
            description="Initial failure",
            timestamp="2026-04-10T12:00:00Z",
        )
        event = CausalEvent(
            event_id="event-1",
            event_type="error",
            name="Connection failed",
            description="Consequence of root",
            timestamp="2026-04-10T12:01:00Z",
            depth=1,
        )
        report = RootCauseReport(
            task_id="task-123",
            root_event=root,
            causal_chain=[event, root],
            confidence=0.85,
            explanations=[
                "Root cause: Root cause",
                "Causal path: Root cause → Connection failed",
            ],
            analysis_status="success",
        )
        result = report.to_dict()

        assert isinstance(result, dict)
        assert result["task_id"] == "task-123"
        assert result["confidence"] == 0.85
        assert len(result["causal_chain"]) == 2
        assert result["root_event"]["event_id"] == "root-1"
        assert result["analysis_status"] == "success"

    def test_report_with_none_root_event(self):
        """Report with None root_event should serialize without error."""
        report = RootCauseReport(task_id="task-456", root_event=None)
        result = report.to_dict()
        assert result["root_event"] is None


class TestRootCauseAnalyzerConfounderDetection:
    """Tests for confounder detection logic."""

    @pytest.mark.asyncio
    async def test_no_confounders_single_chain(self):
        """Single linear chain should have no confounders."""
        analyzer = RootCauseAnalyzer()
        chain = [
            CausalEvent(
                event_id="e1",
                event_type="error",
                name="E1",
                description="Event 1",
                timestamp="2026-04-10T12:00:00Z",
                depth=0,
            ),
            CausalEvent(
                event_id="e2",
                event_type="error",
                name="E2",
                description="Event 2",
                timestamp="2026-04-10T12:01:00Z",
                depth=1,
            ),
        ]
        confounders = analyzer._detect_confounders(chain)
        assert confounders == []

    @pytest.mark.asyncio
    async def test_multiple_causes_at_same_depth_detected(self):
        """Multiple events at depth 1 should be detected as confounders (when root is deeper)."""
        analyzer = RootCauseAnalyzer()
        chain = [
            CausalEvent(
                event_id="e1",
                event_type="error",
                name="E1",
                description="Event 1",
                timestamp="2026-04-10T12:00:00Z",
                depth=0,
            ),
            CausalEvent(
                event_id="e2",
                event_type="error",
                name="E2",
                description="Event 2",
                timestamp="2026-04-10T12:01:00Z",
                depth=1,
            ),
            CausalEvent(
                event_id="e3",
                event_type="error",
                name="E3",
                description="Event 3",
                timestamp="2026-04-10T12:02:00Z",
                depth=1,
            ),
            CausalEvent(
                event_id="e4",
                event_type="error",
                name="E4",
                description="Event 4",
                timestamp="2026-04-10T12:03:00Z",
                depth=2,
            ),
        ]
        confounders = analyzer._detect_confounders(chain)
        assert len(confounders) == 1
        assert confounders[0].event_id == "e3"

    @pytest.mark.asyncio
    async def test_root_events_not_confounders(self):
        """Root events (highest depth) should not be marked as confounders."""
        analyzer = RootCauseAnalyzer()
        chain = [
            CausalEvent(
                event_id="e1",
                event_type="error",
                name="E1",
                description="Event 1",
                timestamp="2026-04-10T12:00:00Z",
                depth=0,
            ),
            CausalEvent(
                event_id="e2",
                event_type="error",
                name="E2",
                description="Event 2",
                timestamp="2026-04-10T12:01:00Z",
                depth=1,
            ),
            CausalEvent(
                event_id="e3",
                event_type="error",
                name="E3",
                description="Event 3",
                timestamp="2026-04-10T12:02:00Z",
                depth=2,
            ),
            CausalEvent(
                event_id="e4",
                event_type="error",
                name="E4",
                description="Event 4",
                timestamp="2026-04-10T12:03:00Z",
                depth=2,
            ),
        ]
        confounders = analyzer._detect_confounders(chain)
        # Root depth events (max_depth=2) should not be confounders
        assert len(confounders) == 0


class TestRootCauseAnalyzerExplanations:
    """Tests for explanation generation."""

    @pytest.mark.asyncio
    async def test_empty_chain_explanation(self):
        """Empty chain should generate default explanation."""
        analyzer = RootCauseAnalyzer()
        explanations = analyzer._generate_explanations([], [])
        assert "No causal chain found" in explanations

    @pytest.mark.asyncio
    async def test_single_event_explanation(self):
        """Single event chain should mention root cause."""
        analyzer = RootCauseAnalyzer()
        chain = [
            CausalEvent(
                event_id="e1",
                event_type="error",
                name="Database failure",
                description="DB unavailable",
                timestamp="2026-04-10T12:00:00Z",
                depth=0,
            ),
        ]
        explanations = analyzer._generate_explanations(chain, [])
        assert any("Root cause" in exp for exp in explanations)
        assert any("Database failure" in exp for exp in explanations)

    @pytest.mark.asyncio
    async def test_two_event_chain_explanation(self):
        """Two-event chain should explain cause-effect relationship."""
        analyzer = RootCauseAnalyzer()
        chain = [
            CausalEvent(
                event_id="e1",
                event_type="error",
                name="API timeout",
                description="Request timeout",
                timestamp="2026-04-10T12:00:00Z",
                depth=0,
            ),
            CausalEvent(
                event_id="e2",
                event_type="error",
                name="Resource exhaustion",
                description="Out of memory",
                timestamp="2026-04-10T11:59:00Z",
                depth=1,
            ),
        ]
        explanations = analyzer._generate_explanations(chain, [])
        assert any("Root cause" in exp for exp in explanations)
        assert any("Resource exhaustion" in exp for exp in explanations)

    @pytest.mark.asyncio
    async def test_confounder_explanation(self):
        """Confounders should be mentioned in explanation."""
        analyzer = RootCauseAnalyzer()
        chain = [
            CausalEvent(
                event_id="e1",
                event_type="error",
                name="Task failed",
                description="Task exec failed",
                timestamp="2026-04-10T12:00:00Z",
                depth=0,
            ),
        ]
        confounders = [
            CausalEvent(
                event_id="c1",
                event_type="warning",
                name="High latency",
                description="Network slow",
                timestamp="2026-04-10T11:59:00Z",
                depth=1,
            ),
        ]
        explanations = analyzer._generate_explanations(chain, confounders)
        assert any("Contributing factors" in exp for exp in explanations)
        assert any("High latency" in exp for exp in explanations)

    @pytest.mark.asyncio
    async def test_confidence_level_explanation(self):
        """Explanations should include confidence level."""
        analyzer = RootCauseAnalyzer()
        # Single event = low confidence
        chain_1 = [
            CausalEvent(
                event_id="e1",
                event_type="error",
                name="E1",
                description="Event",
                timestamp="2026-04-10T12:00:00Z",
                depth=0,
            ),
        ]
        expl_1 = analyzer._generate_explanations(chain_1, [])
        assert any("Low confidence" in exp for exp in expl_1)

        # Two events = medium confidence
        chain_2 = [
            CausalEvent(
                event_id="e1",
                event_type="error",
                name="E1",
                description="Event",
                timestamp="2026-04-10T12:00:00Z",
                depth=0,
            ),
            CausalEvent(
                event_id="e2",
                event_type="error",
                name="E2",
                description="Event",
                timestamp="2026-04-10T11:59:00Z",
                depth=1,
            ),
        ]
        expl_2 = analyzer._generate_explanations(chain_2, [])
        assert any("Medium confidence" in exp for exp in expl_2)

        # Three+ events = high confidence
        chain_3 = [
            CausalEvent(
                event_id=f"e{i}",
                event_type="error",
                name=f"E{i}",
                description=f"Event {i}",
                timestamp="2026-04-10T12:00:00Z",
                depth=i,
            )
            for i in range(3)
        ]
        expl_3 = analyzer._generate_explanations(chain_3, [])
        assert any("High confidence" in exp for exp in expl_3)


class TestRootCauseAnalyzerConfidence:
    """Tests for confidence score calculation."""

    @pytest.mark.asyncio
    async def test_empty_chain_zero_confidence(self):
        """Empty chain should yield zero confidence."""
        analyzer = RootCauseAnalyzer()
        confidence = analyzer._calculate_confidence([])
        assert confidence == 0.0

    @pytest.mark.asyncio
    async def test_single_event_partial_confidence(self):
        """Single event should yield partial confidence."""
        analyzer = RootCauseAnalyzer()
        chain = [
            CausalEvent(
                event_id="e1",
                event_type="error",
                name="E1",
                description="Event",
                timestamp="2026-04-10T12:00:00Z",
                confidence=1.0,
            ),
        ]
        confidence = analyzer._calculate_confidence(chain)
        assert 0.0 < confidence < 1.0

    @pytest.mark.asyncio
    async def test_longer_chain_higher_confidence(self):
        """Longer chain should yield higher confidence."""
        analyzer = RootCauseAnalyzer()
        chain_2 = [
            CausalEvent(
                event_id=f"e{i}",
                event_type="error",
                name=f"E{i}",
                description=f"Event {i}",
                timestamp="2026-04-10T12:00:00Z",
                confidence=1.0,
                depth=i,
            )
            for i in range(2)
        ]
        chain_5 = [
            CausalEvent(
                event_id=f"e{i}",
                event_type="error",
                name=f"E{i}",
                description=f"Event {i}",
                timestamp="2026-04-10T12:00:00Z",
                confidence=1.0,
                depth=i,
            )
            for i in range(5)
        ]
        confidence_2 = analyzer._calculate_confidence(chain_2)
        confidence_5 = analyzer._calculate_confidence(chain_5)
        assert confidence_5 > confidence_2

    @pytest.mark.asyncio
    async def test_low_event_confidence_reduces_score(self):
        """Low event confidence should reduce overall score."""
        analyzer = RootCauseAnalyzer()
        chain_high = [
            CausalEvent(
                event_id="e1",
                event_type="error",
                name="E1",
                description="Event",
                timestamp="2026-04-10T12:00:00Z",
                confidence=1.0,
            ),
        ]
        chain_low = [
            CausalEvent(
                event_id="e1",
                event_type="error",
                name="E1",
                description="Event",
                timestamp="2026-04-10T12:00:00Z",
                confidence=0.3,
            ),
        ]
        conf_high = analyzer._calculate_confidence(chain_high)
        conf_low = analyzer._calculate_confidence(chain_low)
        assert conf_low < conf_high


class TestRootCauseAnalyzerIntegration:
    """Integration tests for full analyze_task_failure flow."""

    @pytest.mark.asyncio
    async def test_analyze_task_failure_not_found(self):
        """Analyzing non-existent task should return failed status."""
        with patch("services.root_cause_analyzer.get_async_redis_client") as mock_redis:
            mock_client = AsyncMock()
            mock_redis.return_value = mock_client
            mock_client.get.return_value = None

            analyzer = RootCauseAnalyzer()
            report = await analyzer.analyze_task_failure("nonexistent-task")

            assert report.analysis_status == "failed"
            assert "error event" in report.error_message.lower()

    @pytest.mark.asyncio
    async def test_analyze_task_failure_with_chain(self):
        """Analyzing task with causal chain should return report."""
        with (
            patch("services.root_cause_analyzer.get_async_redis_client") as mock_redis,
            patch("services.root_cause_analyzer.TemporalSearchService") as mock_temporal,
        ):
            mock_client = AsyncMock()
            mock_redis.return_value = mock_client
            # Return error event ID as UUID string
            mock_client.get.return_value = "550e8400-e29b-41d4-a716-446655440000"

            # Mock temporal service
            mock_service = AsyncMock()
            mock_temporal.return_value = mock_service

            # Return causal chain
            chain = [
                {
                    "id": "550e8400-e29b-41d4-a716-446655440001",
                    "event_type": "error",
                    "name": "API failed",
                    "description": "API timeout",
                    "timestamp": "2026-04-10T12:00:00Z",
                    "confidence": 1.0,
                    "participants": [],
                },
                {
                    "id": "550e8400-e29b-41d4-a716-446655440002",
                    "event_type": "error",
                    "name": "Resource exhausted",
                    "description": "OOM",
                    "timestamp": "2026-04-10T11:59:00Z",
                    "confidence": 0.9,
                    "participants": [],
                },
            ]
            mock_service.find_causal_chain.return_value = chain

            analyzer = RootCauseAnalyzer()
            report = await analyzer.analyze_task_failure("task-123")

            assert report.analysis_status == "success"
            assert report.task_id == "task-123"
            assert len(report.causal_chain) == 2
            assert report.root_event is not None
            assert report.confidence > 0.0
            assert len(report.explanations) > 0


class TestRootCauseAnalyzerErrorHandling:
    """Tests for error handling and edge cases."""

    @pytest.mark.asyncio
    async def test_redis_connection_failure(self):
        """Redis connection errors should be handled gracefully."""

        async def raise_error(*args, **kwargs):
            raise Exception("Redis connection failed")

        with patch(
            "services.root_cause_analyzer.get_async_redis_client",
            side_effect=raise_error,
        ):
            analyzer = RootCauseAnalyzer()
            report = await analyzer.analyze_task_failure("task-123")

            assert report.analysis_status == "failed"
            assert "Analysis error" in report.error_message

    @pytest.mark.asyncio
    async def test_causal_chain_traversal_failure(self):
        """Causal chain traversal errors should be handled gracefully."""
        with (
            patch("services.root_cause_analyzer.get_async_redis_client") as mock_redis,
            patch("services.root_cause_analyzer.TemporalSearchService") as mock_temporal,
        ):
            mock_client = AsyncMock()
            mock_redis.return_value = mock_client
            # Return valid UUID
            mock_client.get.return_value = "550e8400-e29b-41d4-a716-446655440000"

            mock_service = AsyncMock()
            mock_temporal.return_value = mock_service
            mock_service.find_causal_chain.side_effect = Exception("Traversal failed")

            analyzer = RootCauseAnalyzer()
            report = await analyzer.analyze_task_failure("task-123")

            assert report.analysis_status == "failed"
            assert "Traversal failed" in report.error_message


class TestRootCauseAPIEndpoint:
    """Tests for FastAPI endpoint integration."""

    @pytest.mark.asyncio
    async def test_endpoint_success_response(self):
        """Endpoint should return serialized RootCauseReport."""
        from api.analytics import analyze_root_cause

        with patch("api.analytics._root_cause_analyzer.analyze_task_failure") as mock_analyze:
            root = CausalEvent(
                event_id="root-1",
                event_type="failure",
                name="Root cause",
                description="Initial",
                timestamp="2026-04-10T12:00:00Z",
            )
            report = RootCauseReport(
                task_id="task-123",
                root_event=root,
                causal_chain=[root],
                confidence=0.9,
                explanations=["Root cause identified"],
                analysis_status="success",
            )
            mock_analyze.return_value = report

            mock_user = {"user_id": "user-1"}
            result = await analyze_root_cause(
                task_id="task-123",
                current_user=mock_user,
            )

            assert isinstance(result, dict)
            assert result["task_id"] == "task-123"
            assert result["confidence"] == 0.9

    @pytest.mark.asyncio
    async def test_endpoint_not_found_response(self):
        """Endpoint should raise 404 for missing task."""
        from fastapi import HTTPException

        from api.analytics import analyze_root_cause

        with patch("api.analytics._root_cause_analyzer.analyze_task_failure") as mock_analyze:
            report = RootCauseReport(
                task_id="missing-task",
                analysis_status="failed",
                error_message="Task not found",
            )
            mock_analyze.return_value = report

            mock_user = {"user_id": "user-1"}

            with pytest.raises(HTTPException) as exc_info:
                await analyze_root_cause(
                    task_id="missing-task",
                    current_user=mock_user,
                )
            assert exc_info.value.status_code == 404
