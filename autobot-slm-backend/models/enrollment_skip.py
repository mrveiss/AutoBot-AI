# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A fleet node left out of an update because its last enrollment failed (#21036).

Its own module, free of ORM imports, so the API job model and the node-event service share one type.
"""

from pydantic import BaseModel

ENROLLMENT_SKIP_REASON = "skipped: enrollment incomplete (last enrollment failed)"


class EnrollmentSkip(BaseModel):
    """One skipped node and why."""

    node_id: str
    reason: str = ENROLLMENT_SKIP_REASON
