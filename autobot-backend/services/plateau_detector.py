# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shared "N consecutive non-improving rounds" plateau predicate (#12624).

Extracted from ``AutoResearchAgent._should_continue``
(``services/autoresearch/auto_research_agent.py:959``) rather than duplicated
(design doc §4.1/§6). The ML-experiment loop's "improved" signal
(``ImprovementMetrics.improved``) and the research Planner's "found new
facts this round" signal are both just booleans over a rolling window — this
module is the pure, dependency-free leaf that both callers reduce to.
"""

from __future__ import annotations

from typing import Sequence


def plateau_reached(recent_flags: Sequence[bool], window: int) -> bool:
    """Return True when the last *window* flags all indicate no progress.

    Args:
        recent_flags: Chronological progress flags, one per round/iteration
            (``True`` = this round improved / found something new).
        window: Number of trailing consecutive flags required to declare a
            plateau. Fewer than *window* flags collected so far is never a
            plateau (not enough data to conclude the search is exhausted).

    Returns:
        True if a plateau is detected (caller should stop), False otherwise.
    """
    if len(recent_flags) < window:
        return False
    return not any(recent_flags[-window:])
