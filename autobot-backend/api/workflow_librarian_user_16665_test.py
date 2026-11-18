# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The workflow librarian step reads the KB as the user who started the workflow, else nothing (#16665)."""

from unittest.mock import patch

import pytest

from agents.kb_librarian_agent import KBLibrarianAgent
from api.workflow import _handle_librarian_step, _prepare_workflow_data
from knowledge.read_path_fakes_16665 import PRIVATE_A, FakeKB
from models.task_context import WorkflowStepContext


def _ctx(user_id):
    return WorkflowStepContext(
        workflow_id="w1", step={}, orchestrator=None, action="Search Knowledge Base x", user_id=user_id
    )


async def _run(user_id):
    ctx = _ctx(user_id)

    def make_agent():
        agent = object.__new__(KBLibrarianAgent)
        agent.knowledge_base, agent.enabled = FakeKB(), True
        agent.max_results, agent.similarity_threshold, agent.auto_summarize = 5, 0.0, False
        return agent

    with patch("agents.kb_librarian_agent.KBLibrarianAgent", side_effect=make_agent):
        await _handle_librarian_step(ctx)
    return ctx.step["result"]


@pytest.mark.asyncio
async def test_the_step_reads_as_the_triggering_user():
    assert "alice private fact" in await _run("alice")
    assert PRIVATE_A not in await _run("bob")


@pytest.mark.asyncio
async def test_a_workflow_with_no_user_is_denied_not_read_as_anyone():
    assert PRIVATE_A not in await _run(None)


def test_the_workflow_record_carries_the_triggering_user():
    data = _prepare_workflow_data("w1", "msg", {}, False, user_id="alice")

    assert data["user_id"] == "alice"
