# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#20046: a lost race on the one-pending-per-node index returns the winner's proposal, not a 500."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

from api import internal_slm_credential_proposals as route
from api.schemas_slm_credential_proposals import SshPasswordDeletionProposal


def _body() -> SshPasswordDeletionProposal:
    return SshPasswordDeletionProposal(node_id="node-1")


async def _propose(list_approvals, create):
    gate = MagicMock()
    gate.return_value.list_approvals = list_approvals
    gate.return_value.create_approval = create
    db = MagicMock()
    db.rollback = AsyncMock()
    with patch.object(route, "ApprovalGateService", gate):
        # service_opt_in wraps the handler; the undecorated coroutine is what the route runs.
        handler = getattr(route.propose_ssh_password_deletion, "__wrapped__", route.propose_ssh_password_deletion)
        return await handler(_body(), db), db


async def test_a_lost_insert_race_returns_the_winning_proposal() -> None:
    winner = SimpleNamespace(id="w1", status="pending")
    lost = AsyncMock(side_effect=IntegrityError("insert", {}, Exception("unique")))
    reply, db = await _propose(AsyncMock(side_effect=[[], [winner]]), lost)
    assert (reply.approval_id, reply.created) == ("w1", False)
    db.rollback.assert_awaited_once()


async def test_a_conflict_with_no_winner_is_not_swallowed() -> None:
    lost = AsyncMock(side_effect=IntegrityError("insert", {}, Exception("other")))
    with pytest.raises(IntegrityError):
        await _propose(AsyncMock(side_effect=[[], []]), lost)


async def test_contrast_no_conflict_creates() -> None:
    created = AsyncMock(return_value=SimpleNamespace(id="n1", status="pending"))
    reply, _ = await _propose(AsyncMock(return_value=[]), created)
    assert (reply.approval_id, reply.created) == ("n1", True)
