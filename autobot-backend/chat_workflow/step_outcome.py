# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Which recorded steps actually ran (#21959).

The continuation prompt tells the model what was executed. A step that is still waiting for a person, was
refused, was denied or timed out did not run, so it is neither counted nor described as executed.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable

#: Statuses a step record carries when the action never ran.
NOT_RUN_STATUSES = frozenset(
    {
        "pending_approval",
        "approval_required",
        "outcome_unknown",
        "denied",
        "denied_by_user",
        "refused",
        "timeout",
        "gated",
        "queued",
    }
)


def did_execute(step: Dict[str, Any]) -> bool:
    """Whether *step* ran: a status in :data:`NOT_RUN_STATUSES` is a step that did not."""
    return str(step.get("status", "")).lower() not in NOT_RUN_STATUSES


def executed_count(steps: Iterable[Dict[str, Any]]) -> int:
    """How many of *steps* actually ran."""
    return sum(1 for step in steps if did_execute(step))


def not_run_note(step: Dict[str, Any]) -> str:
    """The line that tells the model a step did not run; empty for a step that did."""
    if did_execute(step):
        return ""
    return "\n- NOT RUN: this step did not execute (it is not complete; do not report it as done)"
