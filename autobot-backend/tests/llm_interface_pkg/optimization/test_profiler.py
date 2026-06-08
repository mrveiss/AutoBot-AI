# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for the layered inference profiler. Issue #1956."""

import json
import time
from unittest.mock import MagicMock, patch

from llm_shared.optimization.profiler import (
    INFERENCE_STAGES,
    LayeredProfiler,
    _StageAccumulator,
    _VRAMTracker,
)


class TestStageAccumulator:
    """Test the per-stage timing accumulator."""

    def test_empty_accumulator(self):
        acc = _StageAccumulator()
        assert acc.total_ns == 0
        assert acc.call_count == 0
        assert acc.avg_ns == 0.0

    def test_single_record(self):
        acc = _StageAccumulator()
        acc.record(1_000_000)  # 1ms
        assert acc.total_ns == 1_000_000
        assert acc.call_count == 1
        assert acc.min_ns == 1_000_000
        assert acc.max_ns == 1_000_000

    def test_multiple_records(self):
        acc = _StageAccumulator()
        acc.record(1_000_000)
        acc.record(3_000_000)
        acc.record(2_000_000)
        assert acc.total_ns == 6_000_000
        assert acc.call_count == 3
        assert acc.min_ns == 1_000_000
        assert acc.max_ns == 3_000_000
        assert acc.avg_ns == 2_000_000

    def test_avg_ns_zero_calls(self):
        acc = _StageAccumulator()
        assert acc.avg_ns == 0.0


class TestVRAMTracker:
    """Test the VRAM tracker (mocked — no GPU in test env)."""

    def test_no_cuda(self):
        tracker = _VRAMTracker()
        tracker._cuda_available = False
        tracker.sample()
        assert tracker.peak_allocated_bytes == 0

    @patch(
        "llm_shared.optimization.profiler._VRAMTracker._check_cuda",
        return_value=True,
    )
    def test_cuda_sampling(self, mock_check):
        tracker = _VRAMTracker()
        with patch(
            "torch.cuda.mem_get_info",
            return_value=(2_000_000_000, 8_000_000_000),
        ):
            tracker.sample()
        assert tracker.peak_allocated_bytes == 6_000_000_000
        assert tracker.total_bytes == 8_000_000_000

    def test_to_dict(self):
        tracker = _VRAMTracker()
        tracker.peak_allocated_bytes = 4_294_967_296  # 4GB
        tracker.total_bytes = 8_589_934_592  # 8GB
        d = tracker.to_dict()
        assert d["peak_allocated_bytes"] == 4_294_967_296
        assert d["peak_allocated_mb"] == 4096.0
        assert d["total_bytes"] == 8_589_934_592


class TestLayeredProfilerDisabled:
    """Test profiler behavior when disabled — must have zero overhead."""

    def test_disabled_by_default(self):
        profiler = LayeredProfiler("test-model")
        assert not profiler.enabled

    def test_disabled_stage_is_noop(self):
        profiler = LayeredProfiler("test-model", enabled=False)
        with profiler.stage("compute"):
            pass
        report = profiler.summary()
        assert report["enabled"] is False
        assert "stages" not in report

    def test_disabled_log_summary_noop(self):
        profiler = LayeredProfiler("test-model", enabled=False)
        profiler.log_summary()  # Should not raise

    def test_disabled_export_noop(self):
        profiler = LayeredProfiler("test-model", enabled=False)
        profiler.export_to_prometheus()  # Should not raise

    def test_disabled_save_history_returns_none(self):
        profiler = LayeredProfiler("test-model", enabled=False)
        assert profiler.save_history() is None


class TestLayeredProfilerEnabled:
    """Test profiler with explicit enabled=True."""

    def test_enabled_explicit(self):
        profiler = LayeredProfiler("test-model", enabled=True)
        assert profiler.enabled

    def test_model_name(self):
        profiler = LayeredProfiler("llama-7b", enabled=True)
        assert profiler.model_name == "llama-7b"

    def test_single_stage_timing(self):
        profiler = LayeredProfiler("test-model", enabled=True)
        with profiler.stage("compute"):
            time.sleep(0.01)
        report = profiler.summary()
        assert report["enabled"] is True
        assert "compute" in report["stages"]
        assert report["stages"]["compute"]["total_ms"] >= 9.0
        assert report["stages"]["compute"]["calls"] == 1

    def test_multiple_stages(self):
        profiler = LayeredProfiler("test-model", enabled=True)
        with profiler.stage("load_safetensor"):
            time.sleep(0.01)
        with profiler.stage("compute"):
            time.sleep(0.01)
        report = profiler.summary()
        assert len(report["stages"]) == 2
        assert report["stage_order"] == ["load_safetensor", "compute"]
        assert report["total_ms"] >= 18.0

    def test_stage_percentage_breakdown(self):
        profiler = LayeredProfiler("test-model", enabled=True)
        with profiler.stage("fast"):
            pass
        with profiler.stage("slow"):
            time.sleep(0.02)
        report = profiler.summary()
        # slow stage should dominate percentage
        assert report["stages"]["slow"]["percentage"] > 50.0

    def test_repeated_stage_accumulates(self):
        profiler = LayeredProfiler("test-model", enabled=True)
        for _ in range(3):
            with profiler.stage("compute"):
                time.sleep(0.005)
        report = profiler.summary()
        assert report["stages"]["compute"]["calls"] == 3
        assert report["stages"]["compute"]["total_ms"] >= 12.0

    def test_wall_clock_timing(self):
        profiler = LayeredProfiler("test-model", enabled=True)
        profiler.start()
        with profiler.stage("compute"):
            time.sleep(0.01)
        profiler.stop()
        report = profiler.summary()
        assert report["wall_clock_ms"] >= 9.0

    def test_reset_clears_data(self):
        profiler = LayeredProfiler("test-model", enabled=True)
        with profiler.stage("compute"):
            pass
        profiler.reset()
        report = profiler.summary()
        assert report["stages"] == {}
        assert report["total_ms"] == 0.0

    def test_summary_vram_structure(self):
        profiler = LayeredProfiler("test-model", enabled=True)
        report = profiler.summary()
        assert "vram" in report
        assert "peak_allocated_bytes" in report["vram"]
        assert "total_bytes" in report["vram"]


class TestLayeredProfilerEnvironment:
    """Test environment-based enable/disable."""

    @patch.dict("os.environ", {"AUTOBOT_INFERENCE_PROFILING": "1"})
    def test_enabled_via_env(self):
        profiler = LayeredProfiler("test-model")
        assert profiler.enabled

    @patch.dict("os.environ", {"AUTOBOT_INFERENCE_PROFILING": "true"})
    def test_enabled_via_env_true(self):
        profiler = LayeredProfiler("test-model")
        assert profiler.enabled

    @patch.dict("os.environ", {"AUTOBOT_INFERENCE_PROFILING": "0"})
    def test_disabled_via_env(self):
        profiler = LayeredProfiler("test-model")
        assert not profiler.enabled

    @patch.dict("os.environ", {}, clear=True)
    def test_disabled_by_default_no_env(self):
        profiler = LayeredProfiler("test-model")
        assert not profiler.enabled


class TestLayeredProfilerHistory:
    """Test profiling history persistence."""

    def test_save_history_creates_file(self, tmp_path):
        with patch(
            "llm_shared.optimization.profiler._get_history_dir",
            return_value=tmp_path,
        ):
            profiler = LayeredProfiler("test-model", enabled=True)
            with profiler.stage("compute"):
                pass
            filepath = profiler.save_history()
            assert filepath is not None
            assert filepath.exists()
            data = json.loads(filepath.read_text(encoding="utf-8"))
            assert data["model"] == "test-model"
            assert "timestamp" in data
            assert "stages" in data


class TestLayeredProfilerPrometheus:
    """Test Prometheus export integration."""

    def test_export_calls_metrics_manager(self):
        profiler = LayeredProfiler("test-model", enabled=True)
        with profiler.stage("compute"):
            time.sleep(0.005)
        mock_manager = MagicMock()
        with patch(
            "autobot_shared.monitoring.prometheus_metrics.get_metrics_manager",
            return_value=mock_manager,
        ):
            profiler.export_to_prometheus()
        mock_manager.record_inference_stage_duration.assert_called()
        mock_manager.record_inference_session_complete.assert_called_once()


class TestInferenceStages:
    """Test the default INFERENCE_STAGES list."""

    def test_stages_defined(self):
        assert len(INFERENCE_STAGES) > 0
        assert "load_safetensor" in INFERENCE_STAGES
        assert "compute" in INFERENCE_STAGES
        assert "pin_memory" in INFERENCE_STAGES

    def test_stages_are_strings(self):
        for stage in INFERENCE_STAGES:
            assert isinstance(stage, str)
