# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#20567: the proposal routes create a PENDING approval, refuse with 409 when there is nothing to remove."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from api import admin_cleanup_proposals as routes
from services import install_cleanup_actions as acts


def _json_arrow_for_old_sqlite(engine) -> None:
    """Some SQLite builds predate ``->>``: run the same statement through ``json_extract`` (same result)."""
    import re

    from sqlalchemy import event

    @event.listens_for(engine.sync_engine, "before_cursor_execute", retval=True)
    def _rewrite(_conn, _cursor, statement, parameters, _context, _many):  # noqa: ANN001
        return re.sub(r"\(?(\w+\.context) ->> \?\)?", r"json_extract(\1, ?)", statement), parameters


def _seed(root: Path) -> None:
    backend = root / "autobot-backend"
    backend.mkdir(parents=True)
    for i in (1, 2):
        path = backend / f".env.{i}~"
        path.write_text("x", encoding="utf-8")
        os.utime(path, (i * 100, i * 100))


async def test_status_counts_and_proposal_does_not_remove(tmp_path: Path) -> None:
    """The REAL approval service over real SQLite: a PENDING row is stored, and nothing is removed."""
    from sqlalchemy import select

    from models.approval import Approval, ApprovalComment, TaskApprovalLink
    from tests.helpers._sqlite_test_engine import real_savepoint_session_factory

    await asyncio.to_thread(_seed, tmp_path)
    async for factory in real_savepoint_session_factory(
        [Approval.__table__, ApprovalComment.__table__, TaskApprovalLink.__table__]
    ):
        _json_arrow_for_old_sqlite(factory.kw["bind"])
        async with factory() as session:
            with patch.object(acts, "install_root", return_value=tmp_path):
                status = await routes.env_copies_status()
                reply = await routes.propose_env_copies_cleanup({"id": "u1"}, session)
                with pytest.raises(HTTPException) as repeat:  # the real pending lookup finds the first one
                    await routes.propose_env_copies_cleanup({"id": "u1"}, session)
        async with factory() as session:
            rows = (await session.execute(select(Approval))).scalars().all()
    assert status.count == 1 and reply.action == acts.ENV_COPIES_ACTION
    assert reply.status == "pending" and repeat.value.status_code == 409
    assert len(rows) == 1 and str(rows[0].id) == reply.approval_id and rows[0].status == "pending"
    assert rows[0].context == {"action": acts.ENV_COPIES_ACTION, "node": acts.node_identity()}
    assert len(await asyncio.to_thread(lambda: list((tmp_path / "autobot-backend").glob(".env.*~")))) == 2


async def test_nothing_to_remove_is_409(tmp_path: Path) -> None:
    with patch.object(acts, "install_root", return_value=tmp_path):
        with pytest.raises(HTTPException) as err:
            await routes.propose_env_copies_cleanup({"id": "u1"}, MagicMock())
    assert err.value.status_code == 409


async def test_a_repeat_proposal_is_409_and_creates_nothing(tmp_path: Path) -> None:
    await asyncio.to_thread(_seed, tmp_path)
    create = AsyncMock()
    service = SimpleNamespace(create_approval=create, list_approvals=AsyncMock(return_value=[object()]))
    with (
        patch.object(acts, "install_root", return_value=tmp_path),
        patch.object(routes, "ApprovalGateService", return_value=service),
    ):
        with pytest.raises(HTTPException) as err:
            await routes.propose_env_copies_cleanup({"id": "u1"}, MagicMock())
    assert err.value.status_code == 409 and "already waiting" in err.value.detail
    create.assert_not_awaited()


async def test_a_lost_insert_race_is_409_after_a_rollback(tmp_path: Path) -> None:
    from sqlalchemy.exc import IntegrityError

    await asyncio.to_thread(_seed, tmp_path)
    lost = AsyncMock(side_effect=IntegrityError("insert", {}, Exception("unique")))
    service = SimpleNamespace(create_approval=lost, list_approvals=AsyncMock(return_value=[]))
    db = MagicMock()
    db.rollback = AsyncMock()
    with (
        patch.object(acts, "install_root", return_value=tmp_path),
        patch.object(routes, "ApprovalGateService", return_value=service),
        pytest.raises(HTTPException) as err,
    ):
        await routes.propose_env_copies_cleanup({"id": "u1"}, db)
    assert err.value.status_code == 409
    db.rollback.assert_awaited_once()


def test_the_model_declares_both_partial_unique_indexes() -> None:
    from models.approval import PENDING_ENV_COPIES_INDEX, PENDING_SSH_CREDENTIAL_INDEX, Approval

    by_name = {i.name: i for i in Approval.__table__.indexes}
    assert by_name[PENDING_ENV_COPIES_INDEX].unique and len(by_name[PENDING_ENV_COPIES_INDEX].expressions) == 2
    assert by_name[PENDING_SSH_CREDENTIAL_INDEX].unique
    assert "slm_node_ssh_password_delete" in str(
        by_name[PENDING_SSH_CREDENTIAL_INDEX].dialect_options["postgresql"]["where"]
    )
