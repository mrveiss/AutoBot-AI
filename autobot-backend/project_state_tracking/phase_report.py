# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Reading the phase-validation report without inventing numbers (#17089).

`PhaseValidator.validate_all_phases()` omits `completion_percentage` entirely
when a check group was skipped, and omits any figure for a phase whose verdict
comes from dedicated workflows. Consumers therefore cannot subscript it, and
must not default it to 0 -- 0 reads as "measured and found empty", which is the
confusion #17089 removed from the report in the first place.

Its own module rather than helpers inside `tracker.py`: adding them there took
that file from 571 to 604 lines, past the 600 ceiling, and the standing rule is
to split rather than raise it.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


def phase_figure(phase_data: Dict[str, Any]) -> Optional[float]:
    """A phase's reported figure, or ``None`` when it publishes none.

    Reads the pre-#17089 key first so this works against either report shape,
    then the structural figure. Returns ``None`` rather than 0 when neither is
    present, so a caller has to decide what "no measurement" means rather than
    being handed a number that looks like one.
    """
    if "completion_percentage" in phase_data:
        return float(phase_data["completion_percentage"])
    value = phase_data.get("structural_presence_percentage")
    return float(value) if isinstance(value, (int, float)) else None


def validation_figure(assessment: Dict[str, Any]) -> float:
    """The run's headline figure, under whichever key carries it.

    #17089 renamed `system_maturity_score` to `structural_presence_score`,
    because a `--ci-mode` run measures presence and not maturity. Both are read
    so this works against either shape.
    """
    for key in ("structural_presence_score", "system_maturity_score"):
        value = assessment.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    return 0.0
