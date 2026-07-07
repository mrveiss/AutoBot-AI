# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Proposal-only remediation loop for anti-pattern health-score improvement (#11196, #11199).

This module is STRICTLY READ-ONLY with respect to source code.  It NEVER
modifies source files, writes patches, opens PRs, shells out to external
commands, or dispatches automated fixes.  It only:

  1. Snapshots the current health state from an ``AntiPatternReport``.
  2. Selects the top-N ranked findings as a structured proposal.
  3. Records before/after deltas as a trend row in Redis.
  4. (Gated, default OFF) Prepares work-item descriptors for external filing.

Dispatch gate (#11199):
  ``dispatch_proposal`` is guarded by ``REMEDIATION_DISPATCH_ENABLED`` (default
  false).  When false the method is a pure no-op.  When true it prepares
  structured work-item payloads ``[{title, body, labels}]`` for external filing
  — it does NOT invoke external commands, write files, or open GitHub issues
  directly.  No first-class GitHub issue-creation client exists in app code
  without external commands; callers or an external process consume the payloads.

Guardrail constants (all env-backed with safe defaults):
  REMEDIATION_MAX_BATCH       — max findings per proposal batch (default 5).
  REMEDIATION_MIN_CONFIDENCE  — reserved for a future dispatch confidence gate
                                (default 0.0, unused here).
  REMEDIATION_DISPATCH_ENABLED — enable work-item preparation (default false).
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
# dispatch_proposal also defensively re-caps at this limit.
REMEDIATION_MAX_BATCH: int = int(os.environ.get("REMEDIATION_MAX_BATCH", "5"))

# Minimum confidence threshold reserved for a future dispatch approval gate.
# Currently unused — recorded here so the constant is discoverable when
# the gate is implemented.  At 0.0 all proposals pass (no filtering).
REMEDIATION_MIN_CONFIDENCE: float = float(os.environ.get("REMEDIATION_MIN_CONFIDENCE", "0.0"))

# Master gate for dispatch_proposal.  Default is false — the safe path is
# always the disabled one.  Set REMEDIATION_DISPATCH_ENABLED=true to enable
# work-item preparation.  This never enables code mutation; it only controls
# whether structured work-item payloads are returned for external filing.
REMEDIATION_DISPATCH_ENABLED: bool = os.environ.get("REMEDIATION_DISPATCH_ENABLED", "false").lower() == "true"

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

    def dispatch_proposal(
        self,
        proposal: list[dict[str, Any]],
        report: "AntiPatternReport | None" = None,
    ) -> dict[str, Any]:
        """Prepare work-item payloads for external filing (gated by REMEDIATION_DISPATCH_ENABLED).

        When REMEDIATION_DISPATCH_ENABLED is false (the default), this method is
        a pure no-op and returns immediately with status "disabled".  No I/O,
        no side effects, no code mutation occurs on this path.

        When enabled, proposal entries are defensively re-capped at
        REMEDIATION_MAX_BATCH and deduped by (file, pattern_type) — within-batch
        only.  No first-class GitHub issue-creation client exists in app code
        without invoking external commands; therefore this method returns the
        prepared work-item payloads for the caller or an external process to file.

        Args:
            proposal: List of target dicts from select_targets().
            report:   Unused; accepted for forward-compatibility only.

        Returns:
            {"status": "disabled", "dispatched": 0} when the gate is off.
            {"status": "prepared", "dispatched": N, "items": [...]} when on.
        """
        if not REMEDIATION_DISPATCH_ENABLED:
            return {"status": "disabled", "dispatched": 0}

        return _prepare_work_items(proposal)

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


def _prepare_work_items(proposal: list[dict[str, Any]]) -> dict[str, Any]:
    """Build work-item payloads from a proposal, capped and deduped by (file, pattern_type).

    Deduplication is within-batch only.  Callers or an external process are
    responsible for filing the returned payloads; this function never performs
    network I/O or shell calls.
    """
    capped = proposal[:REMEDIATION_MAX_BATCH]
    seen: set[tuple[str, str]] = set()
    items: list[dict[str, Any]] = []
    for target in capped:
        key = (target.get("file", ""), target.get("pattern_type", ""))
        if key in seen:
            continue
        seen.add(key)
        items.append(_build_work_item(target))
    logger.info("dispatch_proposal: prepared %d work-item(s) for external filing", len(items))
    return {"status": "prepared", "dispatched": len(items), "items": items}


def _build_work_item(target: dict[str, Any]) -> dict[str, Any]:
    """Render one proposal target as a {title, body, labels} work-item payload."""
    title = f"[anti-pattern] {target.get('pattern_type', 'unknown')} in {target.get('file', 'unknown')}"
    body = (
        f"**File:** `{target.get('file', 'unknown')}` (line {target.get('line', '?')})\n"
        f"**Pattern:** {target.get('pattern_type', 'unknown')}\n"
        f"**Severity:** {target.get('severity', 'unknown')}\n"
        f"**Runtime risk:** {target.get('runtime_risk', 0.0):.2f}\n\n"
        f"**Suggestion:** {target.get('suggestion', 'No suggestion provided.')}"
    )
    labels = ["anti-pattern", f"severity:{target.get('severity', 'unknown')}"]
    return {"title": title, "body": body, "labels": labels}


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
