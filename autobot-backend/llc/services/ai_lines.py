# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The per-company store of AI lines (#18430).

Reads are open to the enforcement point and the API. There is exactly ONE writer,
:func:`record_approved_line`, and its only caller is the post-approval handler
(``services.ai_line_change_action``): an agent cannot change a line because no path an agent
reaches calls it, and a person changes a line only by approving a request in Approvals.
"""

from __future__ import annotations

import re
import uuid
from typing import Dict

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.ai_lines import SCOPE_COMPANY, AiLine, fallback_keys, parse_line
from autobot_shared.logging_manager import get_logger

from ..models.ai_line import ACTION_KEY_LENGTH, LLCAiLine

logger = get_logger(__name__)

_KEY_SHAPE = re.compile(r"^[a-z0-9_.\-]+(:[a-z0-9_.\-]+)?$")


def normalise_key(raw: str) -> str:
    """The canonical stored key, or ``ValueError`` -- a typo would silently set a line nobody reads."""
    key = (raw or "").strip().lower()
    if not key or len(key) > ACTION_KEY_LENGTH or not _KEY_SHAPE.match(key):
        raise ValueError("an action key is '<tool>' or '<tool>:<action>' (letters, digits, _ . -)")
    return key


async def list_lines(session: AsyncSession, company_id: uuid.UUID, kind: str = SCOPE_COMPANY) -> Dict[str, LLCAiLine]:
    """Every line this scope has set, keyed by action key (``kind`` ``company``, or ``user`` for personal lines)."""
    rows = await session.execute(
        sa.select(LLCAiLine).where(LLCAiLine.company_id == company_id, LLCAiLine.scope_kind == kind)
    )
    return {row.action_key: row for row in rows.scalars().all()}


async def stored_line(
    session: AsyncSession, company_id: uuid.UUID, key: str, kind: str = SCOPE_COMPANY
) -> AiLine | None:
    """The line set for *key*, falling back from ``tool:action`` to ``tool``; ``None`` when unset.

    A stored value that is not one of the three lines is treated as ``never`` rather than ignored:
    an unreadable decision must not become a looser one.
    """
    keys = fallback_keys(key)
    rows = await session.execute(
        sa.select(LLCAiLine.action_key, LLCAiLine.line).where(
            LLCAiLine.company_id == company_id, LLCAiLine.scope_kind == kind, LLCAiLine.action_key.in_(keys)
        )
    )
    found = {action_key: line for action_key, line in rows.all()}
    for candidate in keys:
        if candidate in found:
            parsed = parse_line(found[candidate])
            if parsed is None:
                logger.error(
                    "Unreadable AI line %r for %s/%s; treating as never", found[candidate], company_id, candidate
                )
            return parsed or AiLine.NEVER
    return None


async def record_approved_line(
    session: AsyncSession,
    *,
    company_id: uuid.UUID,
    key: str,
    line: AiLine,
    approval_id: uuid.UUID,
    decided_by: str,
    kind: str = SCOPE_COMPANY,
) -> LLCAiLine:
    """Write one line. ONLY the post-approval handler calls this; see the module docstring."""
    key = normalise_key(key)
    rows = await session.execute(
        sa.select(LLCAiLine).where(
            LLCAiLine.company_id == company_id, LLCAiLine.scope_kind == kind, LLCAiLine.action_key == key
        )
    )
    row = rows.scalar_one_or_none()
    if row is None:
        row = LLCAiLine(id=uuid.uuid4(), company_id=company_id, scope_kind=kind, action_key=key, line=line.value)
        session.add(row)
    row.line = line.value
    row.approval_id = approval_id
    row.decided_by = decided_by
    await session.flush()
    return row
