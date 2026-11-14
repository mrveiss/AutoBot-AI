# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Files the approval that asks a person to back-fill a company's work item projects (#18978, #17038).

The request carries only the company: the numbers a person is shown come from
``llc.services.project_backfill.preview_project_backfill`` and the action recounts when it runs.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from models.approval import Approval, ApprovalStatus, ApprovalType
from services.approval_gate_service import ApprovalGateService
from services.project_backfill_action import ACTION
from user_management.database import get_async_session_factory

REQUESTER_PREFIX = "project-backfill"


def _describe(preview: dict) -> str:
    """What the reviewer reads in the inbox."""
    return (
        f"{preview.get('missing', 0)} work item(s) have no project: {preview.get('from_ancestor', 0)} take "
        f"an ancestor's project, {preview.get('to_default', 0)} go to the default project. "
        f"{preview.get('foreign_ancestor_project_skipped', 0)} have an ancestor in another company's project, "
        "which is never used. "
        f"{preview.get('conflicts', 0)} have a child already in another project and are left as they are. "
        "Nothing changes until approved."
    )


async def propose_project_backfill(*, company_id: uuid.UUID, requested_by: str, preview: dict) -> Approval:
    """File (or reuse) the pending backfill request for *company_id*; *preview* is stored for the reviewer."""
    requester = f"{REQUESTER_PREFIX}:{requested_by}"
    context = {"action": ACTION, "company_id": str(company_id), "preview": preview}
    async with get_async_session_factory()() as session:
        pending = await session.execute(
            select(Approval).where(
                Approval.status == ApprovalStatus.PENDING.value,
                Approval.approval_type == ApprovalType.WORKFLOW_GATE.value,
                Approval.company_id == company_id,
            )
        )
        for existing in pending.scalars().all():
            if (existing.context or {}).get("action") == ACTION:
                # The reviewer reads the current counts, the same ones this request's caller is shown.
                existing.context = {**existing.context, "preview": preview}
                existing.description = _describe(preview)
                await session.commit()
                await session.refresh(existing)
                return existing
        return await ApprovalGateService(session).create_approval(
            title="Give the work items without a project a project",
            approval_type=ApprovalType.WORKFLOW_GATE.value,
            requested_by_agent=requester,
            description=_describe(preview),
            context=context,
            company_id=company_id,
        )
