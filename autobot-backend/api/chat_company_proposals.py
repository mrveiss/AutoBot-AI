# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Admin trigger for the legacy Company OS chat backfill, as a proposer (#16905, #17038).

``POST /api/chat-company-proposals/propose`` runs the backfill's dry run and files one approval-queue proposal
per legacy chat whose title names a real company. It writes no chat: a person approves each proposal in the
Approvals inbox, and only then is the company assigned through the audited assign path (#21997). Re-running it
raises nothing twice.
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, Request

from auth_middleware import check_admin_permission
from autobot_shared.logging_manager import get_logger
from services.chat_company_proposals import propose_company_assignments
from utils.chat_utils import get_chat_history_manager

logger = get_logger(__name__)

router = APIRouter(prefix="/chat-company-proposals", dependencies=[Depends(check_admin_permission)])


@router.post("/propose")
async def propose_assignments(request: Request) -> Dict[str, Any]:
    """Raise a proposal for each unassigned legacy CEO chat; counts say what was found and what was filed."""
    result = await propose_company_assignments(get_chat_history_manager(request))
    logger.info("Chat company backfill proposed %d assignment(s) for review", len(result["proposed"]))
    return result
