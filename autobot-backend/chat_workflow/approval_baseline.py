# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Server-wide baseline of approval-gated action categories (#18294).

Owner decision 2026-10-11: every mutating tool is gated by an approval category. The
categories are the existing ones (``autobot_shared.tool_catalogue.APPROVAL_CATEGORY_TOOLS``) and
the existing seam enforces them (``_approval_category_for`` over ``ctx.requires_approval_before``).
This module only decides WHICH categories a run starts with: all of them, minus the ones an
administrator relaxed in the SLM's server-wide settings.

Trust model: the relaxation lives ONLY in the SLM setting. A session or work item can add
categories (union), never remove one, so a user cannot lift a gate. If the SLM is unreachable
or its value is malformed the relaxation is empty -- every category stays gated (fail closed).
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from autobot_shared.logging_manager import get_logger
from autobot_shared.tool_catalogue import valid_approval_categories
from llc.services.slm_policy import fetch_slm_policy_json

logger = get_logger(__name__)

#: SLM server-wide setting naming the approval categories an administrator has relaxed.
RELAXED_CATEGORIES_SETTING_KEY = "chat.relaxed_approval_categories"

#: SLM server-wide setting an administrator turns on to stop attachment turns (and the later turns of a chat that
#: used one) asking for every tool call (#20195). Off unless it reads exactly ``true`` / ``{"enabled": true}``;
#: written only through the SLM settings API, which needs the admin config-write permission.
AUTO_APPROVE_ATTACHMENTS_SETTING_KEY = "chat.auto_approve_attachment_turns"


def _categories_from_setting(data: Any) -> frozenset[str]:
    """Accept ``["cat", ...]`` or ``{"categories": [...]}``; anything else relaxes nothing."""
    raw = data.get("categories") if isinstance(data, dict) else data
    if not isinstance(raw, (list, tuple)):
        return frozenset()
    return frozenset(c for c in raw if isinstance(c, str)) & valid_approval_categories()


async def relaxed_approval_categories() -> frozenset[str]:
    """Categories the SLM server-wide setting relaxes; empty on any failure (fail closed)."""
    return _categories_from_setting(await fetch_slm_policy_json(RELAXED_CATEGORIES_SETTING_KEY))


async def attachment_auto_approve_enabled() -> bool:
    """Whether the admin setting lifts the attachment floor; False when unset, malformed or unreadable (asks)."""
    data = await fetch_slm_policy_json(AUTO_APPROVE_ATTACHMENTS_SETTING_KEY)
    return (data.get("enabled") if isinstance(data, dict) else data) is True


async def baseline_approval_categories() -> List[str]:
    """Every valid category except the ones the SLM setting relaxes (sorted, stable)."""
    return sorted(valid_approval_categories() - await relaxed_approval_categories())


def union_categories(*groups: Optional[Iterable[str]]) -> List[str]:
    """Add-only merge: a caller's categories extend the baseline, never shrink it."""
    merged: set[str] = set()
    for group in groups:
        merged.update(c for c in (group or ()) if isinstance(c, str))
    return sorted(merged)


async def with_baseline_categories(
    context: Optional[Dict[str, Any]], session_categories: Iterable[str]
) -> Dict[str, Any]:
    """Return *context* with ``requires_approval_before`` = baseline ∪ session ∪ already-declared."""
    base = dict(context or {})
    declared = base.get("requires_approval_before")
    base["requires_approval_before"] = union_categories(
        await baseline_approval_categories(),
        session_categories,
        declared if isinstance(declared, (list, tuple)) else (),
    )
    return base
