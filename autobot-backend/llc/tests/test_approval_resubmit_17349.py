# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Resubmit may not rewrite what a human reviewed, and only the requester may resubmit (#17349, #18430).

``POST /approval-gates/{id}/resubmit`` took any ``context`` and wrote it verbatim. After a revision request that
let the requester swap the target (or the action, or an AI-line change's scope, key or line) between the
reviewer's look and the reviewer's approval, and let anyone resubmit someone else's request. The create-route
refusal of server-only actions was routed around by exactly this.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from llc.tests.test_ai_lines_api_18430 import (  # noqa: F401  (fixtures + helpers shared with the AI-line suite)
    AGENT_USER,
    MEMBER,
    OWNER,
    Approval,
    _gates_client,
    _me_client,
    _outside_world,
    _propose_mine,
    _rows,
    factory,
)

SET_LINE = {"action": "ai_line.set_line", "action_key": "write_file", "line": "autonomous"}


async def _seed(maker, requester, context, status="revision_requested"):
    async with maker() as session:
        row = Approval(
            title="x", approval_type="workflow_gate", status=status, requested_by_agent=str(requester), context=context
        )
        session.add(row)
        await session.commit()
        return str(row.id)


def _resubmit(client, approval_id, context=None, description=None):
    body = {"description": description, "context": context}
    return client.post(f"/api/approval-gates/{approval_id}/resubmit", json=body)


async def _status(maker, approval_id):
    return (await _rows(maker, Approval))[0].status if approval_id else None


@pytest.mark.asyncio
async def test_a_harmless_approval_cannot_be_resubmitted_as_a_set_line_proposal(factory):  # noqa: F811
    """The attack: create something harmless, request revision, resubmit naming ai_line.set_line, decide it."""
    approval_id = await _seed(factory, OWNER, {"note": "harmless"})
    resp = _resubmit(_gates_client(factory, OWNER), approval_id, SET_LINE)
    assert resp.status_code == 403
    assert "set_line" not in str((await _rows(factory, Approval))[0].context)
    assert await _status(factory, approval_id) == "revision_requested"  # no state transition was recorded


@pytest.mark.asyncio
async def test_resubmitting_a_real_set_line_proposal_with_a_changed_line_or_key_is_refused(factory):  # noqa: F811
    approval_id = _propose_mine(_me_client(factory, MEMBER)).json()["approval_id"]
    async with factory() as session:
        await session.execute(sa.update(Approval).values(status="revision_requested"))
        await session.commit()
    mine = _gates_client(factory, MEMBER)
    original = (await _rows(factory, Approval))[0].context
    for field, value in (("line", "never"), ("action_key", "execute_command"), ("scope_id", str(uuid.uuid4()))):
        resp = _resubmit(mine, approval_id, {**original, field: value})
        assert resp.status_code == 403 and f"context.{field}" in str(resp.json()), field
    assert (await _rows(factory, Approval))[0].context == original
    # Contrast: the same context with only a new description is a benign resubmit and works.
    assert _resubmit(mine, approval_id, dict(original), description="clearer reason").status_code == 200


@pytest.mark.asyncio
async def test_only_the_requester_can_resubmit(factory):  # noqa: F811
    approval_id = await _seed(factory, OWNER, {"note": "a"})
    assert _resubmit(_gates_client(factory, AGENT_USER), approval_id, {"note": "b"}).status_code == 403
    assert (await _rows(factory, Approval))[0].context == {"note": "a"}
    assert _resubmit(_gates_client(factory, OWNER), approval_id, {"note": "b"}).status_code == 200


@pytest.mark.asyncio
async def test_a_request_with_no_recorded_requester_can_be_resubmitted_by_nobody(factory):  # noqa: F811
    approval_id = await _seed(factory, "", {"note": "a"})
    assert _resubmit(_gates_client(factory, OWNER), approval_id, {"note": "b"}).status_code == 403


@pytest.mark.asyncio
async def test_an_unregistered_action_is_refused_on_resubmit_as_on_create(factory):  # noqa: F811
    approval_id = await _seed(factory, OWNER, {"note": "a"})
    resp = _resubmit(_gates_client(factory, OWNER), approval_id, {"action": "no.such.action"})
    assert resp.status_code == 400 and "no registered post-approval handler" in str(resp.json())


@pytest.mark.asyncio
async def test_a_registered_destructive_action_cannot_have_its_target_swapped(factory):  # noqa: F811
    """#17349 AC4: the reviewer looked at one candidate and must not be able to approve another."""
    import services.knowledge.collection_space_stamp_action  # noqa: F401  (registers its action)
    from services.approval_execution import registered_action_proposers

    action = "stamp_collection_embedding_space"
    assert action in registered_action_proposers()
    reviewed = {"action": action, "collection": "kb_a", "model": "m", "dim": 384}
    approval_id = await _seed(factory, OWNER, reviewed)
    mine = _gates_client(factory, OWNER)
    assert _resubmit(mine, approval_id, {**reviewed, "collection": "kb_other"}).status_code == 403
    assert (await _rows(factory, Approval))[0].context == reviewed


@pytest.mark.asyncio
async def test_an_ordinary_approval_still_resubmits_with_a_new_context(factory):  # noqa: F811
    approval_id = await _seed(factory, OWNER, {"note": "a"})
    resp = _resubmit(_gates_client(factory, OWNER), approval_id, {"note": "b", "extra": 1}, description="d")
    assert resp.status_code == 200
    row = (await _rows(factory, Approval))[0]
    assert row.status == "pending" and row.context == {"note": "b", "extra": 1}
