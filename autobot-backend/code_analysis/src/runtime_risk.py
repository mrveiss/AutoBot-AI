# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Runtime failure risk resolver for anti-pattern ranking (#11183).

Aggregates ``FailurePattern`` records from Redis into a per-file risk score
that the anti-pattern ranking can use as an additive boost.

Attribution model (blame-frame):
    Each pattern's ``failure_locations`` list is attributed to the innermost
    (last) entry only — ``locations[-1]`` — rather than all frames.  This
    avoids over-counting shared infrastructure frames that appear in many
    patterns: e.g., a common dispatcher that shows up in every traceback
    would otherwise inflate *its* risk far beyond its actual culpability.
    The trade-off is that utility functions deep in a call stack are not
    credited; the call-site is.  This is the intended behaviour.

Risk formula:
    raw_risk[f] = sum(occurrence_count * (1 - resolution_success_rate))
                  over all patterns whose blame frame is file f

    runtime_risk[f] = 1 - exp(-raw_risk[f] / K)

where K is a module-level constant (env var ``AUTOBOT_RISK_K``, default 5.0).
The output is bounded to [0, 1).
"""

from __future__ import annotations

import math
import os

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

# Decay constant K: controls how steeply risk saturates toward 1.
# A file with raw_risk == K gets runtime_risk ≈ 0.63.
# Override via env var when tuning sensitivity.
_RISK_K: float = float(os.environ.get("AUTOBOT_RISK_K", "5.0"))


async def build_runtime_risk_map() -> dict[str, float]:
    """Return a mapping from repo-relative file path to runtime_risk in [0, 1).

    Reads all known ``FailurePattern`` objects from the shared
    ``FailurePatternDetector`` singleton (reuses its ``list_known_patterns``
    method, which already handles Redis connection, timeout, and error
    graceful-degradation).

    Returns an empty dict when Redis is unavailable or no patterns are stored.
    """
    try:
        from services.failure_pattern_detector import get_pattern_detector

        detector = get_pattern_detector()
        patterns = await detector.list_known_patterns(limit=10000)
    except Exception as exc:
        logger.warning("runtime_risk: could not load failure patterns: %s", exc)
        return {}

    return _aggregate_risk(patterns)


def _blame_file(pattern) -> str | None:
    """Return the repo-relative blame-frame file for a pattern, or None."""
    from autobot_shared.repo_path import to_repo_relative

    locs = getattr(pattern, "failure_locations", None) or []
    if not locs:
        return None
    # Blame the innermost (last) frame — see module docstring.
    blame = locs[-1].get("file", "") if isinstance(locs[-1], dict) else ""
    return to_repo_relative(blame) if blame else None


def _aggregate_risk(patterns) -> dict[str, float]:
    """Accumulate raw risk per file then apply bounded-exp normalization."""
    raw: dict[str, float] = {}
    for pattern in patterns:
        blame = _blame_file(pattern)
        if blame is None:
            continue
        weight = pattern.occurrence_count * (1.0 - pattern.resolution_success_rate)
        raw[blame] = raw.get(blame, 0.0) + weight

    return {f: _bounded_exp(r) for f, r in raw.items()}


def _bounded_exp(raw_risk: float) -> float:
    """Apply 1 - exp(-raw_risk / K) bounding to [0, 1)."""
    k = _RISK_K if _RISK_K > 0 else 5.0
    return 1.0 - math.exp(-raw_risk / k)
