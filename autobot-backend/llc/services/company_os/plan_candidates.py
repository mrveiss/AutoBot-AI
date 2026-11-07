# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Rank the steps of a plan as One Number candidates (#20037, FR-3.1).

Pure over ``CompanyWorkflowPlan``: nothing is read from or written to a store, so asking for the candidates
can never create a ``OneNumber``; the owner still picks one (``PUT .../one-number``, an admin action).

The score of a measured step is ``frequency x duration``: how often it happens per week times how long it takes
from landing to done, in hours. The requirement names the owner's return kind as a second input but gives it no
weight, so the formula takes the simplest reading: every return kind weighs a step the same, and the kind is
carried in the result so the screen shows what the ranking was asked for. A weight per kind is a one-line change
here once the owner states one. A step with no metric, or a zero frequency or duration, has no real score:
it is listed apart, never ranked.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from .plan_types import CompanyWorkflowPlan, ReturnKind, Unit

HOURS_PER_DAY = 24.0
_HOURS = {Unit.MINUTES: 1.0 / 60.0, Unit.HOURS: 1.0, Unit.DAYS: HOURS_PER_DAY}


@dataclass(frozen=True)
class OneNumberCandidate:
    rank: int
    step_key: str
    label: str
    lane_key: str
    frequency_per_week: float
    duration_hours: float
    score: float


@dataclass(frozen=True)
class OneNumberRanking:
    return_kind: ReturnKind
    ranked: List[OneNumberCandidate]
    unmeasured: List[str]


def rank_candidates(plan: CompanyWorkflowPlan, return_kind: ReturnKind) -> OneNumberRanking:
    """Measured steps by descending score (ties: authoring order); steps without a metric in ``unmeasured``."""
    metrics: Dict[str, Tuple[float, float]] = {
        m.step_key: (m.frequency.value, m.duration.value * _HOURS[m.duration.unit]) for m in plan.step_metrics
    }
    measured = [s for s in plan.steps if s.key in metrics and metrics[s.key][0] * metrics[s.key][1] > 0]
    ordered = sorted(measured, key=lambda s: (-metrics[s.key][0] * metrics[s.key][1], s.position, s.key))
    ranked = [
        OneNumberCandidate(
            i, s.key, s.label, s.lane_key, metrics[s.key][0], metrics[s.key][1], metrics[s.key][0] * metrics[s.key][1]
        )
        for i, s in enumerate(ordered, start=1)
    ]
    return OneNumberRanking(return_kind, ranked, [s.key for s in plan.steps if s not in measured])
