# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Threat Detection Learner

Adaptive learning layer for threat detection that tracks detection accuracy and
mitigation effectiveness over time. Reduces false positives by weighting confidence
scores by historical precision, and prioritises mitigations proven most effective.

Issue #2110 - Adaptive threat detection: learn from detection outcomes.

Design overview
---------------
Pattern precision (tp/fp counters)
  Redis hash  security:detection_outcomes:{pattern_id}
  fields: tp, fp, last_seen (ISO-8601 timestamp)

Mitigation effectiveness (EMA per action)
  Redis hash  security:mitigation_scores:{threat_type}
  fields: <action>  (float string, 0.0-1.0 EMA score)

Consolidation
  - Patterns inactive for > INACTIVE_DAYS days are pruned.
  - Patterns with precision < HIGH_FP_THRESHOLD are flagged at WARNING level so
    operators can review detection rules.
"""

from datetime import datetime, timedelta
from typing import Dict

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_redis_client
from autobot_shared.time_utils import now_utc, parse_utc_iso, utc_timestamp

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
_OUTCOME_KEY_PREFIX = "security:detection_outcomes:"
_MITIGATION_KEY_PREFIX = "security:mitigation_scores:"

# Exponential moving-average smoothing factor (higher = react faster to recent data)
_EMA_ALPHA: float = 0.2

# Precision at or below this value flags a pattern as high-FP during consolidation
_HIGH_FP_THRESHOLD: float = 0.30

# Patterns with no activity for this many days are pruned in consolidate()
_INACTIVE_DAYS: int = 90

# Minimum number of observations before precision is trusted
_MIN_OBSERVATIONS: int = 5


class ThreatDetectionLearner:
    """
    Adaptive learning layer for the threat detection engine.

    Tracks per-pattern true/false-positive counts and per-mitigation EMA
    effectiveness scores in Redis so learning persists across restarts and
    scales across multiple engine instances.

    All Redis operations are synchronous (async_client=False) to match the
    engine's synchronous initialisation path; individual methods are called
    from async context via normal awaited coroutines in the engine.
    """

    def __init__(self) -> None:
        self._redis = get_redis_client(async_client=False, database="main")
        logger.info("ThreatDetectionLearner initialised")

    # ── Outcome recording ──────────────────────────────────────────────────────

    def record_outcome(self, pattern_id: str, is_true_positive: bool) -> None:
        """
        Record a detection outcome for a pattern.

        Args:
            pattern_id: Stable identifier for the detection pattern (e.g. analyser
                        name + rule index such as ``"brute_force:0"``).
            is_true_positive: True when the detection was confirmed malicious;
                              False when it was a false positive.
        """
        key = _OUTCOME_KEY_PREFIX + pattern_id
        field = "tp" if is_true_positive else "fp"
        try:
            self._redis.hincrby(key, field, 1)
            self._redis.hset(key, "last_seen", utc_timestamp())
            logger.debug("Recorded outcome pattern=%s tp=%s", pattern_id, is_true_positive)
        except Exception as exc:
            logger.error("Failed to record outcome for pattern %s: %s", pattern_id, exc)

    # ── Precision calculation ──────────────────────────────────────────────────

    def get_pattern_precision(self, pattern_id: str) -> float | None:
        """
        Return the historical precision (tp / (tp + fp)) for a pattern.

        Returns None when fewer than ``_MIN_OBSERVATIONS`` have been recorded
        (insufficient data to trust the estimate).
        """
        key = _OUTCOME_KEY_PREFIX + pattern_id
        try:
            data = self._redis.hmget(key, "tp", "fp")
            tp = int(data[0] or 0)
            fp = int(data[1] or 0)
            total = tp + fp
            if total < _MIN_OBSERVATIONS:
                return None
            return tp / total
        except Exception as exc:
            logger.error("Failed to get precision for pattern %s: %s", pattern_id, exc)
            return None

    def adjust_confidence(self, base_score: float, pattern_id: str) -> float:
        """
        Return a confidence score adjusted by historical pattern precision.

        When there are insufficient observations the base score is returned
        unchanged so new patterns are treated neutrally until enough data
        accumulates.

        Args:
            base_score: Raw confidence score produced by the analyser (0.0-1.0).
            pattern_id: Pattern identifier whose precision is used as weight.

        Returns:
            Adjusted confidence in [0.0, 1.0].
        """
        precision = self.get_pattern_precision(pattern_id)
        if precision is None:
            return base_score
        adjusted = base_score * precision
        logger.debug(
            "Adjusted confidence pattern=%s base=%.3f precision=%.3f adjusted=%.3f",
            pattern_id,
            base_score,
            precision,
            adjusted,
        )
        return min(1.0, max(0.0, adjusted))

    # ── Mitigation effectiveness ───────────────────────────────────────────────

    def record_mitigation_outcome(self, threat_type: str, action: str, success: bool) -> None:
        """
        Update the EMA effectiveness score for a mitigation action.

        Uses exponential moving average so recent outcomes have more influence
        than distant history without requiring unbounded storage.

        Args:
            threat_type: Threat category string (e.g. ``"brute_force"``).
            action: Mitigation action taken (e.g. ``"block_ip"``).
            success: True when the mitigation successfully contained the threat.
        """
        key = _MITIGATION_KEY_PREFIX + threat_type
        outcome_value = 1.0 if success else 0.0
        try:
            raw = self._redis.hget(key, action)
            if raw is not None:
                current_ema = float(raw)
                new_ema = _EMA_ALPHA * outcome_value + (1.0 - _EMA_ALPHA) * current_ema
            else:
                # First observation: initialise directly from outcome
                new_ema = outcome_value
            self._redis.hset(key, action, str(new_ema))
            logger.debug(
                "Updated mitigation EMA threat_type=%s action=%s ema=%.3f",
                threat_type,
                action,
                new_ema,
            )
        except Exception as exc:
            logger.error(
                "Failed to record mitigation outcome threat_type=%s action=%s: %s",
                threat_type,
                action,
                exc,
            )

    def get_best_mitigation(self, threat_type: str) -> str | None:
        """
        Return the action with the highest EMA effectiveness for a threat type.

        Returns None when no mitigation history exists for the threat type.

        Args:
            threat_type: Threat category string (e.g. ``"brute_force"``).
        """
        key = _MITIGATION_KEY_PREFIX + threat_type
        try:
            scores: Dict[bytes, bytes] = self._redis.hgetall(key)
            if not scores:
                return None
            best_action = max(scores, key=lambda k: float(scores[k]))
            # Redis may return bytes or str depending on decode_responses setting
            action_str = best_action.decode() if isinstance(best_action, bytes) else best_action
            best_score = float(scores[best_action])
            logger.debug(
                "Best mitigation threat_type=%s action=%s ema=%.3f",
                threat_type,
                action_str,
                best_score,
            )
            return action_str
        except Exception as exc:
            logger.error("Failed to get best mitigation for threat_type %s: %s", threat_type, exc)
            return None

    # ── Maintenance ────────────────────────────────────────────────────────────

    def consolidate(self) -> Dict[str, int]:
        """
        Prune inactive patterns and flag high-FP patterns for operator review.

        - Patterns not seen for more than ``_INACTIVE_DAYS`` days are deleted.
        - Patterns with precision below ``_HIGH_FP_THRESHOLD`` (and enough
          observations) are logged at WARNING level.

        Returns a summary dict with counts ``pruned`` and ``flagged``.
        """
        pruned = 0
        flagged = 0
        cutoff = now_utc() - timedelta(days=_INACTIVE_DAYS)

        try:
            pattern_keys = self._redis.keys(_OUTCOME_KEY_PREFIX + "*")
        except Exception as exc:
            logger.error("consolidate: failed to list pattern keys: %s", exc)
            return {"pruned": pruned, "flagged": flagged}

        for raw_key in pattern_keys:
            key = raw_key.decode() if isinstance(raw_key, bytes) else raw_key
            pattern_id = key[len(_OUTCOME_KEY_PREFIX) :]
            pruned_this, flagged_this = self._consolidate_pattern(key, pattern_id, cutoff)
            pruned += pruned_this
            flagged += flagged_this

        logger.info("Consolidation complete: pruned=%d flagged=%d", pruned, flagged)
        return {"pruned": pruned, "flagged": flagged}

    def _consolidate_pattern(self, redis_key: str, pattern_id: str, cutoff: datetime) -> tuple:
        """
        Evaluate a single pattern key for pruning or flagging.

        Returns (pruned_count, flagged_count) — each 0 or 1.

        Issue #2110 — extracted helper to keep consolidate() within line limits.
        """
        try:
            data = self._redis.hmget(redis_key, "tp", "fp", "last_seen")
        except Exception as exc:
            logger.error("consolidate: failed to read key %s: %s", redis_key, exc)
            return 0, 0

        last_seen_raw = data[2]
        if last_seen_raw:
            try:
                last_seen = parse_utc_iso(last_seen_raw.decode() if isinstance(last_seen_raw, bytes) else last_seen_raw)
                if last_seen < cutoff:
                    self._redis.delete(redis_key)
                    logger.debug(
                        "Pruned inactive pattern %s (last_seen=%s)",
                        pattern_id,
                        last_seen,
                    )
                    return 1, 0
            except ValueError:
                pass  # Malformed timestamp — skip pruning for this key

        tp = int(data[0] or 0)
        fp = int(data[1] or 0)
        total = tp + fp
        if total >= _MIN_OBSERVATIONS:
            precision = tp / total
            if precision < _HIGH_FP_THRESHOLD:
                logger.warning(
                    "High false-positive pattern detected: pattern_id=%s precision=%.2f "
                    "(tp=%d fp=%d) — review detection rule",
                    pattern_id,
                    precision,
                    tp,
                    fp,
                )
                return 0, 1

        return 0, 0
