# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A fleet node left out of an update because it is not fully enrolled (#21036).

Its own module, free of ORM imports, so the API job model and the node-event service share one type. The
definition of "fully enrolled" is ``services.node_events.unenrolled_state``: the latest enrollment event plus
``status_enums.NOT_FULLY_ENROLLED_STATUSES``, where ``degraded`` counts only for a node with no evidence that
enrollment completed.
"""

from pydantic import BaseModel

#: Why a node is not fully enrolled. The value is the state named in the skip reason.
STATE_FAILED = "failed"
STATE_PENDING = "pending"
STATE_DEGRADED = "degraded"


def enrollment_skip_reason(state: str) -> str:
    """The reason string naming the not-fully-enrolled *state* that caused the skip."""
    return f"skipped: not fully enrolled ({state})"


class EnrollmentSkip(BaseModel):
    """One skipped node and why (the reason names the state)."""

    node_id: str
    reason: str
