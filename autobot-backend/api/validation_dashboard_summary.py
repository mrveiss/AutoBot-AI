# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Pure summaries behind the /validation-dashboard/metrics and /trends routes (#20523)."""

# A phase at or above this figure is complete; below ``_IN_PROGRESS_FROM`` it has not started.
_COMPLETE_FROM = 95.0
_IN_PROGRESS_FROM = 50.0


def has_trend_history(trend_data: dict) -> bool:
    """True when at least one trend series carries a point; stored history is what fills them (#20523)."""
    return any(trend_data.values())


def summarise_phases(phase_details: list[dict]) -> dict[str, int]:
    """Count phases by completion band. A phase with no score is counted on its own (#20523).

    The generator publishes ``completion_percentage: None`` for a phase that defers to dedicated
    gates (#17089); that phase is neither complete nor failing, so it joins no band.
    """
    scored = [p["completion_percentage"] for p in phase_details if p.get("completion_percentage") is not None]
    return {
        "total_phases": len(phase_details),
        "completed_phases": len([v for v in scored if v >= _COMPLETE_FROM]),
        "phases_in_progress": len([v for v in scored if _IN_PROGRESS_FROM <= v < _COMPLETE_FROM]),
        "phases_not_started": len([v for v in scored if v < _IN_PROGRESS_FROM]),
        "phases_unscored": len(phase_details) - len(scored),
    }
