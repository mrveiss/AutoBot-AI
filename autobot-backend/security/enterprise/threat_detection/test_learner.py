# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for ThreatDetectionLearner

Issue #2110 - Adaptive threat detection: learn from detection outcomes.

All Redis calls are patched so the suite runs without a live Redis instance.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest

from autobot_shared.time_utils import now_utc, utc_timestamp
from security.enterprise.threat_detection.learner import (
    _EMA_ALPHA,
    _INACTIVE_DAYS,
    _MITIGATION_KEY_PREFIX,
    _OUTCOME_KEY_PREFIX,
    ThreatDetectionLearner,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_redis():
    """Return a MagicMock that stands in for the synchronous Redis client."""
    redis = MagicMock()
    # Default: keys() returns empty list so consolidate() is a no-op
    redis.keys.return_value = []
    return redis


@pytest.fixture()
def learner(mock_redis):
    """Return a ThreatDetectionLearner with its Redis client mocked."""
    with patch(
        "security.enterprise.threat_detection.learner.get_redis_client",
        return_value=mock_redis,
    ):
        return ThreatDetectionLearner()


# ---------------------------------------------------------------------------
# record_outcome
# ---------------------------------------------------------------------------


class TestRecordOutcome:
    def test_true_positive_increments_tp(self, learner, mock_redis):
        learner.record_outcome("brute_force:0", is_true_positive=True)

        mock_redis.hincrby.assert_called_once_with(_OUTCOME_KEY_PREFIX + "brute_force:0", "tp", 1)

    def test_false_positive_increments_fp(self, learner, mock_redis):
        learner.record_outcome("brute_force:0", is_true_positive=False)

        mock_redis.hincrby.assert_called_once_with(_OUTCOME_KEY_PREFIX + "brute_force:0", "fp", 1)

    def test_last_seen_updated(self, learner, mock_redis):
        learner.record_outcome("cmd_injection:1", is_true_positive=True)

        hset_args = mock_redis.hset.call_args
        assert hset_args is not None
        key, field, _ = hset_args[0]
        assert key == _OUTCOME_KEY_PREFIX + "cmd_injection:1"
        assert field == "last_seen"

    def test_redis_error_does_not_raise(self, learner, mock_redis):
        mock_redis.hincrby.side_effect = ConnectionError("Redis down")
        # Should log error but not propagate exception
        learner.record_outcome("pattern:x", is_true_positive=True)


# ---------------------------------------------------------------------------
# get_pattern_precision
# ---------------------------------------------------------------------------


class TestGetPatternPrecision:
    def _setup_redis_counts(self, mock_redis, tp: int, fp: int):
        mock_redis.hmget.return_value = [str(tp).encode(), str(fp).encode()]

    def test_returns_none_when_insufficient_observations(self, learner, mock_redis):
        # Only 4 observations — below _MIN_OBSERVATIONS (5)
        self._setup_redis_counts(mock_redis, tp=3, fp=1)
        result = learner.get_pattern_precision("some_pattern")
        assert result is None

    def test_calculates_precision_correctly(self, learner, mock_redis):
        # 8 tp, 2 fp → precision = 0.8
        self._setup_redis_counts(mock_redis, tp=8, fp=2)
        result = learner.get_pattern_precision("some_pattern")
        assert result == pytest.approx(0.8)

    def test_perfect_precision(self, learner, mock_redis):
        self._setup_redis_counts(mock_redis, tp=10, fp=0)
        result = learner.get_pattern_precision("some_pattern")
        assert result == pytest.approx(1.0)

    def test_zero_precision(self, learner, mock_redis):
        self._setup_redis_counts(mock_redis, tp=0, fp=10)
        result = learner.get_pattern_precision("some_pattern")
        assert result == pytest.approx(0.0)

    def test_redis_error_returns_none(self, learner, mock_redis):
        mock_redis.hmget.side_effect = ConnectionError("Redis down")
        result = learner.get_pattern_precision("some_pattern")
        assert result is None


# ---------------------------------------------------------------------------
# adjust_confidence
# ---------------------------------------------------------------------------


class TestAdjustConfidence:
    def test_returns_base_score_when_insufficient_data(self, learner, mock_redis):
        # hmget returns only 4 total observations — not enough
        mock_redis.hmget.return_value = [b"3", b"1"]
        result = learner.adjust_confidence(0.9, "pattern:x")
        assert result == pytest.approx(0.9)

    def test_scales_confidence_by_precision(self, learner, mock_redis):
        # 8 tp, 2 fp → precision 0.8; base 0.9 → adjusted 0.72
        mock_redis.hmget.return_value = [b"8", b"2"]
        result = learner.adjust_confidence(0.9, "pattern:x")
        assert result == pytest.approx(0.72)

    def test_result_capped_at_1(self, learner, mock_redis):
        mock_redis.hmget.return_value = [b"10", b"0"]
        # Even with base > 1 (shouldn't happen but guards edge case)
        result = learner.adjust_confidence(1.5, "pattern:x")
        assert result <= 1.0

    def test_result_floored_at_0(self, learner, mock_redis):
        mock_redis.hmget.return_value = [b"0", b"10"]
        result = learner.adjust_confidence(0.9, "pattern:x")
        assert result >= 0.0


# ---------------------------------------------------------------------------
# record_mitigation_outcome (EMA)
# ---------------------------------------------------------------------------


class TestRecordMitigationOutcome:
    def test_first_success_stores_1(self, learner, mock_redis):
        mock_redis.hget.return_value = None  # No prior score

        learner.record_mitigation_outcome("brute_force", "block_ip", success=True)

        mock_redis.hset.assert_called_once_with(_MITIGATION_KEY_PREFIX + "brute_force", "block_ip", "1.0")

    def test_first_failure_stores_0(self, learner, mock_redis):
        mock_redis.hget.return_value = None

        learner.record_mitigation_outcome("brute_force", "block_ip", success=False)

        mock_redis.hset.assert_called_once_with(_MITIGATION_KEY_PREFIX + "brute_force", "block_ip", "0.0")

    def test_ema_update_on_success(self, learner, mock_redis):
        # Current EMA = 0.5; outcome = 1.0
        mock_redis.hget.return_value = b"0.5"
        expected_ema = _EMA_ALPHA * 1.0 + (1.0 - _EMA_ALPHA) * 0.5

        learner.record_mitigation_outcome("api_abuse", "rate_limit_user", success=True)

        hset_call = mock_redis.hset.call_args
        stored_value = float(hset_call[0][2])
        assert stored_value == pytest.approx(expected_ema)

    def test_ema_update_on_failure(self, learner, mock_redis):
        mock_redis.hget.return_value = b"0.8"
        expected_ema = _EMA_ALPHA * 0.0 + (1.0 - _EMA_ALPHA) * 0.8

        learner.record_mitigation_outcome("brute_force", "block_ip", success=False)

        hset_call = mock_redis.hset.call_args
        stored_value = float(hset_call[0][2])
        assert stored_value == pytest.approx(expected_ema)

    def test_redis_error_does_not_raise(self, learner, mock_redis):
        mock_redis.hget.side_effect = ConnectionError("Redis down")
        learner.record_mitigation_outcome("brute_force", "block_ip", success=True)


# ---------------------------------------------------------------------------
# get_best_mitigation
# ---------------------------------------------------------------------------


class TestGetBestMitigation:
    def test_returns_none_when_no_history(self, learner, mock_redis):
        mock_redis.hgetall.return_value = {}
        result = learner.get_best_mitigation("brute_force")
        assert result is None

    def test_returns_action_with_highest_ema(self, learner, mock_redis):
        mock_redis.hgetall.return_value = {
            b"block_ip": b"0.9",
            b"rate_limit_user": b"0.6",
            b"alert_security_team": b"0.4",
        }
        result = learner.get_best_mitigation("brute_force")
        assert result == "block_ip"

    def test_decodes_bytes_key(self, learner, mock_redis):
        mock_redis.hgetall.return_value = {b"quarantine_file": b"0.7"}
        result = learner.get_best_mitigation("malicious_upload")
        assert isinstance(result, str)
        assert result == "quarantine_file"

    def test_redis_error_returns_none(self, learner, mock_redis):
        mock_redis.hgetall.side_effect = ConnectionError("Redis down")
        result = learner.get_best_mitigation("brute_force")
        assert result is None


# ---------------------------------------------------------------------------
# consolidate / pruning / flagging
# ---------------------------------------------------------------------------


class TestConsolidate:
    def _make_key(self, pattern_id: str) -> bytes:
        return (_OUTCOME_KEY_PREFIX + pattern_id).encode()

    def test_prunes_inactive_pattern(self, learner, mock_redis):
        key = self._make_key("old_pattern")
        mock_redis.keys.return_value = [key]

        old_ts = (now_utc() - timedelta(days=_INACTIVE_DAYS + 1)).isoformat()
        mock_redis.hmget.return_value = [b"5", b"0", old_ts.encode()]

        summary = learner.consolidate()

        mock_redis.delete.assert_called_once_with(key.decode())
        assert summary["pruned"] == 1
        assert summary["flagged"] == 0

    def test_does_not_prune_active_pattern(self, learner, mock_redis):
        key = self._make_key("recent_pattern")
        mock_redis.keys.return_value = [key]

        recent_ts = utc_timestamp()
        mock_redis.hmget.return_value = [b"10", b"0", recent_ts.encode()]

        summary = learner.consolidate()

        mock_redis.delete.assert_not_called()
        assert summary["pruned"] == 0

    def test_flags_high_fp_pattern(self, learner, mock_redis):
        key = self._make_key("noisy_pattern")
        mock_redis.keys.return_value = [key]

        recent_ts = utc_timestamp()
        # 2 tp, 8 fp → precision 0.2, below _HIGH_FP_THRESHOLD
        mock_redis.hmget.return_value = [b"2", b"8", recent_ts.encode()]

        summary = learner.consolidate()

        mock_redis.delete.assert_not_called()
        assert summary["flagged"] == 1

    def test_no_flag_when_insufficient_observations(self, learner, mock_redis):
        key = self._make_key("sparse_pattern")
        mock_redis.keys.return_value = [key]

        recent_ts = utc_timestamp()
        # Only 4 observations total — below _MIN_OBSERVATIONS
        mock_redis.hmget.return_value = [b"1", b"3", recent_ts.encode()]

        summary = learner.consolidate()

        assert summary["flagged"] == 0

    def test_returns_counts_for_multiple_patterns(self, learner, mock_redis):
        keys = [self._make_key("p1"), self._make_key("p2"), self._make_key("p3")]
        mock_redis.keys.return_value = keys

        old_ts = (now_utc() - timedelta(days=_INACTIVE_DAYS + 5)).isoformat()
        recent_ts = utc_timestamp()

        # p1 → inactive (prune); p2 → high FP (flag); p3 → healthy
        mock_redis.hmget.side_effect = [
            [b"5", b"0", old_ts.encode()],  # p1 pruned
            [b"2", b"8", recent_ts.encode()],  # p2 flagged
            [b"9", b"1", recent_ts.encode()],  # p3 healthy
        ]

        summary = learner.consolidate()

        assert summary["pruned"] == 1
        assert summary["flagged"] == 1

    def test_redis_keys_error_returns_zeros(self, learner, mock_redis):
        mock_redis.keys.side_effect = ConnectionError("Redis down")
        summary = learner.consolidate()
        assert summary == {"pruned": 0, "flagged": 0}
