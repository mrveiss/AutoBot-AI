# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Write one `post_sync_action_runs` row per executed post-sync action (#17455).

Recording must never fail the sync: every error is caught and logged, and the
sync carries on. `command` and `output_tail` pass through `redact_text` before
they are stored -- a remote command's output can echo a credential, and this
table is readable after the fact (a raw log line -> `secret_redaction.redact_text`,
docs/developer/REDACTION_BOUNDARY.md:125).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from autobot_shared.secret_redaction import redact_text
from models.post_sync_action_run import PostSyncActionRun
from services.database import db_service

logger = logging.getLogger(__name__)

OUTPUT_TAIL_MAX = 800


@dataclass(frozen=True)
class ActionOutcome:
    """What one executed action produced. `exit_code` is None when none was obtained."""

    success: bool | None  # None: issued, outcome unknown
    exit_code: int | None
    output_tail: str
    error: str | None
    started_at: datetime
    finished_at: datetime
    row: dict | None = None  # the recorded (redacted) row, once written


@dataclass(frozen=True)
class RunContext:
    """Which sync run, node and role an action belongs to."""

    run_id: str
    node_id: str
    role_name: str


def build_row(ctx: RunContext, category: str, label: str, command: str | None, units: str | None, out: ActionOutcome):
    """The (redacted) row for *out*; separate from the write so it is testable without a database."""
    return PostSyncActionRun(
        run_id=ctx.run_id,
        node_id=ctx.node_id,
        role_name=ctx.role_name,
        category=category,
        label=label,
        command=redact_text(command) if command else None,
        units=units,
        started_at=out.started_at,
        finished_at=out.finished_at,
        exit_code=out.exit_code,
        success=out.success,
        output_tail=redact_text(out.output_tail or "")[-OUTPUT_TAIL_MAX:],
        error=redact_text(out.error) if out.error else None,
    )


_VIEW_FIELDS = (
    "run_id",
    "node_id",
    "role_name",
    "category",
    "label",
    "command",
    "units",
    "started_at",
    "finished_at",
    "exit_code",
    "success",
    "output_tail",
    "error",
)


def row_view(row) -> dict:
    """The row's (already redacted) fields as a plain dict -- what a response carries."""
    return {name: getattr(row, name) for name in _VIEW_FIELDS}


async def record_action_run(
    ctx: RunContext, category: str, label: str, command: str | None, units: str | None, out: ActionOutcome
) -> dict | None:
    """Persist one row and return its redacted view; never raises (None if it could not even be built)."""
    try:
        row = build_row(ctx, category, label, command, units, out)
        view = row_view(row)
    except Exception:
        logger.exception("Could not build post-sync record %r for run %s", label, ctx.run_id)
        return None
    try:
        async with db_service.session() as db:
            db.add(row)
            await db.commit()
    except Exception:
        logger.exception("Could not record post-sync action %r for run %s", label, ctx.run_id)
    return view
