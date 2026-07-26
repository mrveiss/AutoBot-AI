# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Background worker tasks for periodic audit daemons (GH#7356)."""

from .audit_tasks import audit_claims, audit_dead_code, audit_testgaps
from .consolidate_tasks import consolidate_facts, consolidate_trajectories  # GH#11263, A3 #12554

__all__ = [
    "audit_testgaps",
    "audit_dead_code",
    "audit_claims",
    "consolidate_trajectories",
    "consolidate_facts",
]
