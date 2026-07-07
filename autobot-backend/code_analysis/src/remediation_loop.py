# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Proposal-only remediation loop for anti-pattern health-score improvement (#11196).

This module is STRICTLY READ-ONLY.  It NEVER modifies source files, writes
patches, opens PRs, or dispatches automated fixes.  It only:

  1. Snapshots the current health state from an ``AntiPatternReport``.
  2. Selects the top-N ranked findings as a structured proposal.
  3. Records before/after deltas as a trend row in Redis.

Dispatch of any remediation action is DEFERRED behind a future approval gate
and is explicitly out of scope for this module.  There is no entry point here
that mutates code.

Guardrail constants (all env-backed with safe defaults):
  REMEDIATION_MAX_BATCH     — max findings per proposal batch (default 5).
  REMEDIATION_MIN_CONFIDENCE — reserved for a future dispatch confidence gate
                               (default 0.0, unused here).
"""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING, Any

from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import now_utc, utc_timestamp

if TYPE_CHECKING:
    from code_analysis.src.anti_pattern_detector import AntiPatternReport

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Guardrail constants — env-backed, module-level (see chat_history/cache.py
# for the canonical pattern used across this codebase).
# ---------------------------------------------------------------------------

# Maximum number of findings returned by select_targets() per batch.
# Dispatch gate (deferred) must also respect this limit before acting.
REMEDIATION_MAX_BATCH: int = int(os.environ.get("REMEDIATION_MAX_BATCH", "5"))

# Minimum confidence threshold reserved for a future dispatch approval gate.
# Currently unused — recorded here so the constant is discoverable when
# the gate is implemented.  At 0.0 all proposals pass (no filtering).
REMEDIATION_MIN_CONFIDENCE: float = float(os.environ.get("REMEDIATION_MIN_CONFIDENCE", "0.0"))

# Redis sorted-set key for persisting remediation deltas (analytics DB).
# Score = timestamp-ms; value = JSON-encoded delta record.
_DELTA_HISTORY_KEY = "remediation:delta:history"
# Maximum delta rows to retain in the sorted set (~2 years of daily runs).
_MAX_DELTA_ROWS = 730


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class RemediationLoop:
    """Proposal-only remediation loop.

    Instantiate and call its three async methods in sequence to measure,
    propose, and record health improvements.  This class never writes source
    files or dispatches automated fixes.
    """

    async def snapshot(self, report: "AntiPatternReport") -> dict[str, Any]:
        """Capture a health snapshot from *report*.

        Accepts an injected ``AntiPatternReport`` so callers control when the
        (potentially expensive) analysis runs and tests can inject stubs.

        Returns a dict with:
          health_score, per-severity counts, total_findings, timestamp (ISO).
        """
        return {
            "health_score": report.health_score,
            "critical": report.critical_count,
            "high": report.high_count,
            "medium": report.medium_count,
            "low": report.low_count,
            "total_findings": report.total_issues,
            "timestamp": utc_timestamp(),
        }

    def select_targets(
        self,
        report: "AntiPatternReport",
        n: int | None = None,
    ) -> list[dict[str, Any]]:
        """Return a structured proposal from the top-N ranked findings.

        The report's ``anti_patterns`` list is already ranked by the detector
        (severity * frequency * runtime_risk boost).  This method does NOT
        re-rank — it preserves the detector's order exactly.

        Args:
            report: ``AntiPatternReport`` from ``AntiPatternDetector.analyze()``.
            n:      Override for the batch cap; capped to REMEDIATION_MAX_BATCH
                    when larger.  Pass None to use REMEDIATION_MAX_BATCH.

        Returns:
            List of proposal dicts, each with file, line, pattern_type,
            severity, runtime_risk, and suggestion fields.
        """
        cap = min(n, REMEDIATION_MAX_BATCH) if n is not None else REMEDIATION_MAX_BATCH
        targets = report.anti_patterns[:cap]
        return [
            {
                "file": ap.file_path,
                "line": ap.line_number,
                "pattern_type": ap.pattern_type.value,
                "severity": ap.severity.value,
                "runtime_risk": ap.runtime_risk,
                "suggestion": ap.suggestion,
            }
            for ap in targets
        ]

    async def record_delta(
        self,
        before: dict[str, Any],
        after: dict[str, Any],
    ) -> dict[str, Any]:
        """Compute and persist health delta between two snapshots.

        Persists one row to the ``remediation:delta:history`` Redis sorted set
        (analytics DB, score = timestamp-ms) using the same zadd/zremrangebyrank
        pattern as ``analytics_bug_prediction._persist_prediction_to_redis``.

        If Redis is unavailable the delta is computed and returned without
        raising — a warning is logged instead.

        Args:
            before: Snapshot dict returned by ``snapshot()`` before changes.
            after:  Snapshot dict returned by ``snapshot()`` after changes.

        Returns:
            Delta dict: health_delta, findings_delta, source, timestamp.
        """
        delta = _build_delta_record(before, after)
        await _persist_delta(delta)
        return delta


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _build_delta_record(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Compute delta fields from two snapshots."""
    return {
        "health_delta": after.get("health_score", 0.0) - before.get("health_score", 0.0),
        "findings_delta": after.get("total_findings", 0) - before.get("total_findings", 0),
        "before_health": before.get("health_score", 0.0),
        "after_health": after.get("health_score", 0.0),
        "source": "remediation_delta",
        "timestamp": utc_timestamp(),
    }


async def _persist_delta(delta: dict[str, Any]) -> None:
    """Write one delta record to the Redis analytics sorted set."""
    try:
        from autobot_shared.redis_client import get_async_redis_client

        redis = await get_async_redis_client(database="analytics")
        ts_ms = int(now_utc().timestamp() * 1000)
        payload = json.dumps(delta)
        await redis.zadd(_DELTA_HISTORY_KEY, {payload: ts_ms})
        await redis.zremrangebyrank(_DELTA_HISTORY_KEY, 0, -(_MAX_DELTA_ROWS + 1))
        logger.debug("remediation_delta persisted (ts_ms=%d)", ts_ms)
    except Exception as exc:
        logger.warning("remediation_delta: Redis unavailable, skipping persist: %s", exc)
