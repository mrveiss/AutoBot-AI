# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Read model of a company's AI lines: what is set, and what each action really resolves to (#18430).

Read-only. The EFFECTIVE line comes from the same ``resolve_line`` rule the enforcement point
applies, so the screen cannot say one thing while the seam does another: an action stored as
autonomous in a baseline category is shown as line 2, with the reason.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.ai_lines import SCOPE_COMPANY, AiLine, LineResolution, is_mutating, parse_line, resolve_line
from autobot_shared.tool_catalogue import ToolEffect, approval_category_for, tools_with
from llc.services.ai_lines import list_lines
from services.ai_line_enforcement import gated_categories


@dataclass(frozen=True)
class AiLineView:
    action_key: str
    stored: Optional[AiLine]
    resolution: LineResolution
    approval_id: Optional[uuid.UUID]
    decided_by: Optional[str]


async def describe_lines(session: AsyncSession, company_id: uuid.UUID, kind: str = SCOPE_COMPANY) -> List[AiLineView]:
    """Every action with a stored line, plus every mutating catalogue tool (which counts as line 2 unset)."""
    rows = await list_lines(session, company_id, kind)
    categories = await gated_categories(())
    keys = sorted(set(rows) | set(tools_with(ToolEffect.MUTATING, include_aliases=False)))
    views = []
    for key in keys:
        row = rows.get(key)
        # An unreadable stored value is shown as never, exactly as the enforcement point reads it.
        stored = (parse_line(row.line) or AiLine.NEVER) if row else None
        tool = key.split(":", 1)[0]
        resolution = resolve_line(
            key,
            stored=stored,
            mutating=is_mutating(tool),
            baseline_category=approval_category_for(tool, categories),
        )
        views.append(
            AiLineView(key, stored, resolution, row.approval_id if row else None, row.decided_by if row else None)
        )
    return views
