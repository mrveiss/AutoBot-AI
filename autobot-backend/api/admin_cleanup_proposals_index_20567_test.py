# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#20567: one pending ``.env.*~`` proposal is the database's rule; the route reports a lost race as 409."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from api import admin_cleanup_proposals as routes
from models.approval import PENDING_ENV_COPIES_INDEX, Approval
from services import install_cleanup_actions as acts


async def test_a_lost_insert_race_is_409_after_a_rollback() -> None:
    plan = acts.CleanupPlan(targets=(Path("x"),))
    service = SimpleNamespace(
        list_approvals=AsyncMock(return_value=[]),
        create_approval=AsyncMock(side_effect=IntegrityError("insert", {}, Exception("unique"))),
    )
    session = MagicMock()
    session.rollback = AsyncMock()
    with patch.object(routes, "ApprovalGateService", return_value=service):
        with pytest.raises(HTTPException) as refused:
            await routes._propose(
                plan,
                action=acts.ENV_COPIES_ACTION,
                title="t",
                description="d",
                current_user={"id": "u1"},
                session=session,
            )
    assert refused.value.status_code == 409
    session.rollback.assert_awaited_once()


def test_the_model_declares_the_partial_unique_index() -> None:
    index = next(i for i in Approval.__table__.indexes if i.name == PENDING_ENV_COPIES_INDEX)
    assert index.unique and acts.ENV_COPIES_ACTION in str(index.dialect_options["postgresql"]["where"])


def _migration():
    path = Path(__file__).parents[1] / "migrations/versions/20261106_112_approvals_pending_env_copies_cleanup_unique.py"
    spec = importlib.util.spec_from_file_location("mig112_env_copies_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _upgrade(monkeypatch, pending: int) -> MagicMock:
    mod = _migration()
    bind = MagicMock()
    bind.dialect.name = "postgresql"
    bind.execute.return_value.scalar.return_value = pending
    create = MagicMock()
    monkeypatch.setattr(mod.op, "get_bind", lambda: bind)
    monkeypatch.setattr(mod.op, "create_index", create)
    monkeypatch.setattr(mod, "has_table", lambda _t: True)
    monkeypatch.setattr(mod, "has_index", lambda _t, _i: False)
    mod.upgrade()
    return create


def test_the_migration_fails_when_several_are_pending(monkeypatch) -> None:
    with pytest.raises(RuntimeError, match="2 pending"):
        _upgrade(monkeypatch, 2)


def test_the_migration_creates_the_index_with_at_most_one_pending(monkeypatch) -> None:
    assert _upgrade(monkeypatch, 1).call_args.args[0] == PENDING_ENV_COPIES_INDEX
    assert acts.ENV_COPIES_ACTION in _migration()._WHERE
    assert _migration().down_revision == "20261105_111"
