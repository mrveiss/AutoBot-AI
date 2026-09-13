# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for pipeline profiler. Inspired by flash-moe per-layer timing."""

import asyncio

import pytest

from utils.pipeline_profiler import PipelineProfiler


class TestPipelineProfiler:
    """Test profiler measures pipeline stage durations."""

    @pytest.mark.asyncio
    async def test_profile_records_stage_timing(self):
        profiler = PipelineProfiler("test-pipeline")
        async with profiler.stage("embedding"):
            # fixed sleep on purpose (#16255): duration_ms below is the value under test
            await asyncio.sleep(0.01)
        async with profiler.stage("retrieval"):
            # fixed sleep on purpose (#16255): paired with the "embedding" stage above
            await asyncio.sleep(0.01)
        report = profiler.report()
        assert "embedding" in report["stages"]
        assert "retrieval" in report["stages"]
        assert report["stages"]["embedding"]["duration_ms"] >= 9.0

    @pytest.mark.asyncio
    async def test_total_duration(self):
        profiler = PipelineProfiler("test")
        async with profiler.stage("a"):
            # fixed sleep on purpose (#16255): total_ms below is the value under test
            await asyncio.sleep(0.01)
        async with profiler.stage("b"):
            # fixed sleep on purpose (#16255): paired with the "a" stage above
            await asyncio.sleep(0.01)
        report = profiler.report()
        assert report["total_ms"] >= 18.0

    @pytest.mark.asyncio
    async def test_empty_profiler_report(self):
        profiler = PipelineProfiler("empty")
        report = profiler.report()
        assert report["stages"] == {}
        assert report["total_ms"] == 0.0

    @pytest.mark.asyncio
    async def test_stage_records_exception(self):
        profiler = PipelineProfiler("test")
        with pytest.raises(ValueError):
            async with profiler.stage("fail"):
                raise ValueError("boom")
        report = profiler.report()
        assert report["stages"]["fail"]["error"] == "boom"
        assert report["stages"]["fail"]["duration_ms"] >= 0.0

    @pytest.mark.asyncio
    async def test_stage_order_preserved(self):
        profiler = PipelineProfiler("order-test")
        async with profiler.stage("first"):
            pass
        async with profiler.stage("second"):
            pass
        async with profiler.stage("third"):
            pass
        report = profiler.report()
        assert report["stage_order"] == ["first", "second", "third"]

    @pytest.mark.asyncio
    async def test_pipeline_name_in_report(self):
        profiler = PipelineProfiler("my-pipeline")
        report = profiler.report()
        assert report["pipeline"] == "my-pipeline"
