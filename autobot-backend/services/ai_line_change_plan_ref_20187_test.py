# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A retry of a plan's AI-line proposal reuses the request by the plan's identity, whoever retries (#20168)."""

# flake8: noqa: F811 -- imported pytest fixtures are redefined as test arguments
from __future__ import annotations

from unittest.mock import patch

import pytest

from autobot_shared.ai_lines import SCOPE_COMPANY, AiLine, LineScope
from services.ai_line_change_proposal import propose_line_change
from services.ai_line_enforcement_test import COMPANY, factory  # noqa: F401 -- fixture by name

pytestmark = pytest.mark.asyncio


async def _propose(factory, requester, plan_ref=None, line=AiLine.AUTONOMOUS):
    with patch("services.ai_line_change_proposal.get_async_session_factory", lambda: factory):
        scope = LineScope(SCOPE_COMPANY, COMPANY)
        return await propose_line_change(
            scope=scope, key="mail:draft", line=line, requested_by=requester, plan_ref=plan_ref
        )


async def test_a_retry_by_another_admin_reuses_the_plans_request(factory):
    first = await _propose(factory, "admin-1", "workflow-plan:intake")
    retry = await _propose(factory, "admin-2", "workflow-plan:intake")
    assert retry.id == first.id


async def test_another_plan_or_a_request_without_a_plan_is_not_merged_with_it(factory):
    first = await _propose(factory, "admin-1", "workflow-plan:intake")
    assert (await _propose(factory, "admin-1", "workflow-plan:other")).id != first.id
    assert (await _propose(factory, "admin-1")).id != first.id  # contrast: a personal proposal keeps its own identity
    assert (await _propose(factory, "admin-1", "workflow-plan:intake", AiLine.NEVER)).id != first.id


async def test_the_conversion_files_every_proposal_under_the_plans_identity(factory):
    import uuid

    from llc.services.company_os import plan_convert_lines as lines
    from llc.services.company_os.plan_types import AiLineProposal

    props = [AiLineProposal(tool_action="mail:draft", line="autonomous", sub_step_key="p1")]
    with patch("services.ai_line_change_proposal.get_async_session_factory", lambda: factory):
        await lines.file_proposals(COMPANY, "intake", props, uuid.uuid4())
        first = props[0].approval_id
        props[0].outcome = None  # the plan save failed after filing: a retry by someone else files it again
        await lines.file_proposals(COMPANY, "intake", props, uuid.uuid4())
    assert props[0].approval_id == first
