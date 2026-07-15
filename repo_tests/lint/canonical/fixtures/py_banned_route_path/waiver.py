# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Waiver fixture: era-marker route suppressed via inline waiver."""

router = object()


@router.post("/goal/enhanced")  # canonical: ignore py-banned-route-path — legacy alias (#10746)
async def goal_enhanced():
    pass
