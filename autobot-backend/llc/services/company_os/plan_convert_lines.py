# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Filing a converted plan's AI-line proposals, after the conversion is committed (#19936).

A proposal files an approval in the approvals store's own session, so it cannot join the conversion's
transaction. It therefore runs only once the rows and ``converted`` are durable: a rollback can never leave a
proposal behind. A failure is recorded on the proposal and logged, never raised; a filed one is skipped, so
running this again files only what is still missing.
"""

from __future__ import annotations

import uuid
from typing import List, Optional

from autobot_shared.ai_lines import SCOPE_COMPANY, AiLine, LineScope
from autobot_shared.logging_manager import get_logger
from models.approval import ApprovalStatus
from services.ai_line_change_proposal import propose_line_change

from .plan_types import AiLineProposal, ProposalOutcome

logger = get_logger(__name__)

#: A filed or declined proposal is never filed again; a new revision of the plan is the way forward (#19937).
_SETTLED = (ProposalOutcome.FILED, ProposalOutcome.DECLINED)
#: Statuses of a request a person turned down or sent back: the line did not change.
_DECLINED = (ApprovalStatus.REJECTED.value, ApprovalStatus.REVISION_REQUESTED.value)


async def file_proposals(
    company_id: uuid.UUID, plan_key: str, revision: int, proposals: List[AiLineProposal], actor: Optional[uuid.UUID]
) -> None:
    """Update each not-yet-filed proposal in place with its outcome.

    The request's identity is the plan revision, so a retry after a person decided it finds that request
    and records it, rather than filing a second one (#20115). An approved or pending request is ``filed``; a
    rejected one, or one sent back for revision, is ``declined`` and keeps its approval id. That is the
    request's status judged by the plan's identity, not by the line's current state: the line may have been
    changed since by someone else.
    """
    for prop in proposals:
        if prop.outcome in _SETTLED:
            continue
        try:
            approval = await propose_line_change(
                scope=LineScope(SCOPE_COMPANY, company_id),
                key=prop.tool_action,
                line=AiLine(prop.line),
                requested_by=str(actor),
                reason=f"Workflow plan {plan_key!r}, sub-step {prop.sub_step_key!r}",
                plan_ref=f"workflow-plan:{plan_key}:{revision}",
                legacy_plan_refs=(f"workflow-plan:{plan_key}",) if revision == 1 else (),
            )
        except Exception as exc:  # noqa: BLE001 -- recorded on the proposal and logged; the conversion stands
            prop.outcome, prop.approval_id, prop.error = ProposalOutcome.FAILED, None, type(exc).__name__
            logger.warning("workflow_plan.ai_line_failed plan=%s action=%s", plan_key, prop.tool_action, exc_info=True)
            continue
        declined = approval.status in _DECLINED
        prop.outcome = ProposalOutcome.DECLINED if declined else ProposalOutcome.FILED
        prop.approval_id, prop.error = str(approval.id), None
        logger.info("workflow_plan.ai_line_proposed plan=%s action=%s line=%s", plan_key, prop.tool_action, prop.line)
