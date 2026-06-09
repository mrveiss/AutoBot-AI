# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
AutoResearch Unit Tests

Issue #2597: Tests for parser, models, config, store, and runner.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from services.autoresearch.config import AutoResearchConfig
from services.autoresearch.models import (
    Experiment,
    ExperimentResult,
    ExperimentState,
    ExperimentStats,
    HyperParams,
)
from services.autoresearch.parser import ExperimentOutputParser
from services.autoresearch.store import ExperimentStore

# ---------------------------------------------------------------------------
# Parser tests
# ---------------------------------------------------------------------------


class TestExperimentOutputParser:
    """Tests for training output parsing."""

    def setup_method(self):
        self.parser = ExperimentOutputParser()

    def test_parse_standard_output(self):
        output = (
            "step 1000 | train loss 4.5000 | val loss 4.6000 | val_bpb 6.500\n"
            "step 2000 | train loss 4.2000 | val loss 4.3000 | val_bpb 6.200\n"
            "step 5000 | train loss 4.0191 | val loss 4.0540 | val_bpb 5.846\n"
            "tokens/sec: 12345.67\n"
        )
        result = self.parser.parse(output, wall_time=300.0)

        assert result.success
        assert result.val_bpb == 5.846
        assert result.train_loss == 4.0191
        assert result.val_loss == 4.0540
        assert result.steps_completed == 5000
        assert result.tokens_per_second == 12345.67
        assert result.wall_time_seconds == 300.0
        assert result.error_message is None

    def test_parse_empty_output(self):
        result = self.parser.parse("")
        assert not result.success
        assert result.error_message == "Empty training output"

    def test_parse_error_output(self):
        output = (
            "step 100 | train loss 5.0000 | val loss 5.1000 | val_bpb 7.000\n"
            "CUDA out of memory. Tried to allocate 2.00 GiB\n"
        )
        result = self.parser.parse(output)
        assert result.error_message is not None
        assert "CUDA out of memory" in result.error_message
        # Still parses the step data before the error
        assert result.val_bpb == 7.0
        assert result.steps_completed == 100

    def test_parse_no_step_lines(self):
        output = "Loading data...\nPreparing model...\n"
        result = self.parser.parse(output)
        assert result.val_bpb is None
        assert result.steps_completed == 0

    def test_parse_only_last_step(self):
        """Parser should use the final step line for metrics."""
        output = (
            "step 100 | train loss 5.0 | val loss 5.1 | val_bpb 7.0\n"
            "step 200 | train loss 4.5 | val loss 4.6 | val_bpb 6.5\n"
        )
        result = self.parser.parse(output)
        assert result.val_bpb == 6.5
        assert result.steps_completed == 200

    def test_parse_exception_pattern(self):
        output = "Traceback (most recent call last):\n  File train.py\n"
        result = self.parser.parse(output)
        assert result.error_message is not None
        assert "Traceback" in result.error_message


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


class TestHyperParams:
    """Tests for HyperParams dataclass."""

    def test_default_values(self):
        hp = HyperParams()
        assert hp.learning_rate == 3e-4
        assert hp.batch_size == 64
        assert hp.max_steps == 5000

    def test_roundtrip(self):
        hp = HyperParams(learning_rate=1e-3, extra={"custom_flag": True})
        data = hp.to_dict()
        restored = HyperParams.from_dict(data)
        assert restored.learning_rate == 1e-3
        assert restored.extra == {"custom_flag": True}

    def test_extra_params_preserved(self):
        data = {"learning_rate": 1e-3, "my_custom_param": 42}
        hp = HyperParams.from_dict(data)
        assert hp.extra == {"my_custom_param": 42}
        assert hp.to_dict()["my_custom_param"] == 42


class TestExperimentResult:
    """Tests for ExperimentResult dataclass."""

    def test_success_when_val_bpb_present(self):
        result = ExperimentResult(val_bpb=5.5)
        assert result.success

    def test_failure_when_error(self):
        result = ExperimentResult(val_bpb=5.5, error_message="OOM")
        assert not result.success

    def test_failure_when_no_val_bpb(self):
        result = ExperimentResult()
        assert not result.success

    def test_roundtrip(self):
        result = ExperimentResult(
            val_bpb=5.5,
            train_loss=4.0,
            val_loss=4.1,
            steps_completed=5000,
        )
        data = result.to_dict()
        restored = ExperimentResult.from_dict(data)
        assert restored.val_bpb == 5.5
        assert restored.steps_completed == 5000


class TestExperiment:
    """Tests for Experiment dataclass."""

    def test_improvement_calculation(self):
        exp = Experiment(
            baseline_val_bpb=6.0,
            result=ExperimentResult(val_bpb=5.5),
        )
        assert exp.improvement == 0.5
        assert abs(exp.improvement_pct - 8.333) < 0.01

    def test_no_improvement_without_baseline(self):
        exp = Experiment(result=ExperimentResult(val_bpb=5.5))
        assert exp.improvement is None

    def test_roundtrip(self):
        exp = Experiment(
            hypothesis="Test learning rate",
            tags=["lr_sweep"],
            hyperparams=HyperParams(learning_rate=1e-2),
            result=ExperimentResult(val_bpb=5.5),
            state=ExperimentState.KEPT,
        )
        data = exp.to_dict()
        restored = Experiment.from_dict(data)
        assert restored.hypothesis == "Test learning rate"
        assert restored.tags == ["lr_sweep"]
        assert restored.state == ExperimentState.KEPT
        assert restored.result.val_bpb == 5.5
        assert restored.hyperparams.learning_rate == 1e-2


class TestExperimentStats:
    """Tests for ExperimentStats dataclass."""

    def test_to_dict(self):
        stats = ExperimentStats(
            total_experiments=10,
            completed=5,
            kept=3,
            best_val_bpb=5.2,
        )
        data = stats.to_dict()
        assert data["total_experiments"] == 10
        assert data["best_val_bpb"] == 5.2


# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------


class TestAutoResearchConfig:
    """Tests for AutoResearchConfig."""

    def test_default_config(self):
        cfg = AutoResearchConfig()
        assert cfg.default_training_timeout == 600
        assert cfg.default_max_steps == 5000
        assert cfg.improvement_threshold == 0.01
        assert cfg.redis_prefix == "autoresearch"

    def test_train_script_path(self):
        cfg = AutoResearchConfig(autoresearch_dir=Path("/opt/autoresearch"))
        assert cfg.train_script == Path("/opt/autoresearch/train.py")

    def test_python_bin_default(self):
        cfg = AutoResearchConfig(autoresearch_dir=Path("/nonexistent"))
        assert cfg.python_bin == "python3"

    def test_python_bin_explicit(self):
        cfg = AutoResearchConfig(python_executable="/usr/bin/python3.12")
        assert cfg.python_bin == "/usr/bin/python3.12"


# ---------------------------------------------------------------------------
# Store tests
# ---------------------------------------------------------------------------


class TestExperimentStore:
    """Tests for ExperimentStore with mocked Redis and ChromaDB."""

    @pytest.fixture()
    def mock_redis(self):
        redis = AsyncMock()
        redis.hset = AsyncMock()
        redis.hget = AsyncMock(return_value=None)
        redis.hlen = AsyncMock(return_value=0)
        redis.zadd = AsyncMock()
        redis.zrevrange = AsyncMock(return_value=[])
        redis.sadd = AsyncMock()
        redis.srem = AsyncMock()
        redis.scard = AsyncMock(return_value=0)
        redis.smembers = AsyncMock(return_value=set())
        redis.get = AsyncMock(return_value=None)
        redis.set = AsyncMock()
        return redis

    @pytest.fixture()
    def store(self, mock_redis):
        s = ExperimentStore()
        s._redis = mock_redis
        return s

    @pytest.mark.asyncio
    async def test_save_experiment(self, store, mock_redis):
        exp = Experiment(hypothesis="test", state=ExperimentState.PENDING)
        await store.save_experiment(exp)
        mock_redis.hset.assert_called_once()
        mock_redis.zadd.assert_called_once()
        mock_redis.sadd.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_experiment(self, store, mock_redis):
        exp = Experiment(id="test-123", hypothesis="test")
        mock_redis.hget.return_value = json.dumps(exp.to_dict())
        result = await store.get_experiment("test-123")
        assert result is not None
        assert result.id == "test-123"

    @pytest.mark.asyncio
    async def test_get_experiment_not_found(self, store, mock_redis):
        mock_redis.hget.return_value = None
        result = await store.get_experiment("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_set_and_get_baseline(self, store, mock_redis):
        await store.set_baseline(6.0)
        mock_redis.set.assert_called_once()

        mock_redis.get.return_value = "6.0"
        val = await store.get_baseline()
        assert val == 6.0

    @pytest.mark.asyncio
    async def test_get_stats_empty(self, store, mock_redis):
        stats = await store.get_stats()
        assert stats.total_experiments == 0
        assert stats.best_val_bpb is None

    @pytest.mark.asyncio
    async def test_save_tracks_best_val_bpb(self, store, mock_redis):
        """Best val_bpb should be updated when a better result arrives."""
        exp = Experiment(
            state=ExperimentState.COMPLETED,
            result=ExperimentResult(val_bpb=5.5),
        )
        mock_redis.get.return_value = None  # no existing best
        await store.save_experiment(exp)
        # Should set best since none existed
        mock_redis.set.assert_called()

    @pytest.mark.asyncio
    async def test_update_experiment_state(self, store, mock_redis):
        await store.update_experiment_state(
            "exp-1",
            ExperimentState.COMPLETED,
            ExperimentState.KEPT,
        )
        mock_redis.srem.assert_called_once()
        mock_redis.sadd.assert_called()
