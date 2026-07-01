# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Positive fixture: era-marker route paths — two violations."""

router = object()  # placeholder; only decorators are parsed


@router.post("/goal/enhanced")
async def goal_enhanced():
    pass


@router.get("/search/unified")
def search_unified():
    pass
