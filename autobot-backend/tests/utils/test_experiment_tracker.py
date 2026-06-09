# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for experiment tracking. Inspired by flash-moe results.tsv."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from utils.experiment_tracker import ExperimentRecord, ExperimentTracker


def _async_return(value):
    """Create a coroutine that returns value (for mocking async functions)."""

    async def _coro(*args, **kwargs):
        return value

    return _coro


class TestExperimentRecord:
    """Test experiment record creation and serialization."""

    def test_create_record(self):
        record = ExperimentRecord(
            experiment_id="exp-001",
            name="FMA dequant kernel",
            hypothesis="Rearranging math enables GPU FMA units",
            area="inference",
            measurement={"tok_per_sec_before": 3.90, "tok_per_sec_after": 4.36},
            result="kept",
            rationale="12% throughput improvement",
        )
        assert record.experiment_id == "exp-001"
        assert record.result == "kept"

    def test_to_dict_has_all_fields(self):
        record = ExperimentRecord(
            experiment_id="exp-002",
            name="LZ4 compression",
            hypothesis="Compress experts to reduce SSD reads",
            area="storage",
            measurement={"impact_pct": -13},
            result="discarded",
            rationale="Decompression overhead exceeded savings",
        )
        d = record.to_dict()
        assert d["name"] == "LZ4 compression"
        assert d["result"] == "discarded"
        assert "timestamp" in d
        assert "experiment_id" in d


class TestExperimentTracker:
    """Test tracker stores and retrieves experiments via Redis."""

    @pytest.fixture
    def tracker(self):
        return ExperimentTracker()

    @patch("utils.experiment_tracker.get_async_redis_client")
    @pytest.mark.asyncio
    async def test_log_experiment(self, mock_redis_factory, tracker):
        mock_client = AsyncMock()
        mock_redis_factory.side_effect = _async_return(mock_client)
        record = await tracker.log(
            name="Test experiment",
            hypothesis="Testing works",
            area="testing",
            measurement={"pass_rate": 100},
            result="kept",
            rationale="Tests pass",
        )
        mock_client.rpush.assert_called_once()
        assert record.name == "Test experiment"
        assert record.experiment_id.startswith("exp-")

    @patch("utils.experiment_tracker.get_async_redis_client")
    @pytest.mark.asyncio
    async def test_list_experiments(self, mock_redis_factory, tracker):
        mock_client = AsyncMock()
        mock_client.lrange.return_value = [json.dumps({"name": "exp1", "result": "kept"}).encode()]
        mock_redis_factory.side_effect = _async_return(mock_client)
        results = await tracker.list_experiments()
        assert len(results) == 1

    @patch("utils.experiment_tracker.get_async_redis_client")
    @pytest.mark.asyncio
    async def test_list_by_area(self, mock_redis_factory, tracker):
        mock_client = AsyncMock()
        mock_client.lrange.return_value = [
            json.dumps({"name": "e1", "area": "inference", "result": "kept"}).encode(),
            json.dumps({"name": "e2", "area": "cache", "result": "discarded"}).encode(),
        ]
        mock_redis_factory.side_effect = _async_return(mock_client)
        results = await tracker.list_experiments(area="inference")
        assert len(results) == 1
        assert results[0]["area"] == "inference"

    @patch("utils.experiment_tracker.get_async_redis_client")
    @pytest.mark.asyncio
    async def test_log_with_no_redis(self, mock_redis_factory, tracker):
        mock_redis_factory.side_effect = _async_return(None)
        record = await tracker.log(
            name="No redis",
            hypothesis="Works without redis",
            area="testing",
            measurement={},
            result="kept",
            rationale="Graceful degradation",
        )
        assert record.name == "No redis"
