# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A fleet node left out of an update because it is not fully enrolled (#21036).

Its own module, free of ORM imports, so the API job model and the node-event service share one type. The
definition of "fully enrolled" lives in ``services.node_events``.
"""

from pydantic import BaseModel

#: Why a node is not fully enrolled. The value is the state named in the skip reason.
STATE_FAILED = "failed"
STATE_PENDING = "pending"
STATE_DEGRADED = "degraded"


def skip_reason(state: str) -> str:
    """The reason string naming the not-fully-enrolled *state* that caused the skip."""
    return f"skipped: not fully enrolled ({state})"


class EnrollmentSkip(BaseModel):
    """One skipped node and why (the reason names the state)."""

    node_id: str
    reason: str
