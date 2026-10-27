# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The controlled vocabulary check for ``requires_approval_before`` (GH#11206).

Moved out of ``work_item_service`` (#19582) so that file could take its wake calls
without raising its size ceiling; ``work_item_service`` re-exports it under its old
private name.
"""

from typing import List, Optional


def validated_approval_categories(values: Optional[List[str]], existing: Optional[List[str]] = None) -> List[str]:
    """Validate ``requires_approval_before`` entries against the controlled vocabulary (GH#11206).

    A typo'd category matches no tools at the seam and silently disables the gate,
    so reject unknown *newly-added* values (fail-fast) rather than let governance
    no-op. Values already present in *existing* are exempt, so re-sending a
    pre-controlled-vocabulary (legacy free-text) value while editing an item does
    not block the edit.
    """
    from autobot_shared.tool_catalogue import valid_approval_categories

    vals = list(values or [])
    allowed = valid_approval_categories() | set(existing or [])
    unknown = [v for v in vals if v not in allowed]
    if unknown:
        raise ValueError(f"unknown approval categories: {unknown} (valid: {sorted(valid_approval_categories())})")
    return vals
