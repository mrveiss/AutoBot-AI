# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#20030: one pending owner proposal per session is the database's rule; the route reports a lost race as 409."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from api import admin_ownerless_chat_sessions as route
from api.admin_ownerless_chat_sessions_20030_test import _BODY, _USER, _db
from api.schemas_ownerless_chat_sessions import OwnerlessChatSessionRequest
from models.approval import PENDING_SESSION_OWNER_INDEX, Approval


async def _propose(body=_BODY, create=None):
    gate = MagicMock()
    gate.return_value.create_approval = create or AsyncMock(return_value=SimpleNamespace(id="a1", status="pending"))
    db = _db()
    db.rollback = AsyncMock()
    with (
        patch.object(route, "get_chat_history_manager", return_value=MagicMock()),
        patch.object(route, "session_is_ownerless", AsyncMock(return_value=True)),
        patch.object(route, "active_user_id", AsyncMock(return_value="user-1")),
        patch.object(route, "ApprovalGateService", gate),
    ):
        return await route.propose_chat_session_owner(body, MagicMock(), _USER, db), gate, db


async def test_the_proposal_carries_the_validated_account_id() -> None:
    _, gate, _ = await _propose()
    assert gate.return_value.create_approval.await_args.kwargs["context"]["owner_id"] == "user-1"


async def test_a_title_over_the_column_width_is_422_and_creates_nothing() -> None:
    body = OwnerlessChatSessionRequest(session_id="s" * 255, owner="alice")
    gate = MagicMock()
    with pytest.raises(HTTPException) as refused:
        await _propose(body, create=gate)
    assert refused.value.status_code == 422 and not gate.called


async def test_a_lost_insert_race_is_409_after_a_rollback() -> None:
    lost = AsyncMock(side_effect=IntegrityError("insert", {}, Exception("unique")))
    with pytest.raises(HTTPException) as refused:
        await _propose(create=lost)
    assert refused.value.status_code == 409


def test_the_router_uses_the_one_admin_gate() -> None:
    deps = [d.dependency.__name__ for d in route.router.dependencies]
    assert len(deps) == 1 and "admin_permission" in deps[0]  # the suite may stub the dependency by name


def test_the_model_declares_the_partial_unique_index() -> None:
    index = next(i for i in Approval.__table__.indexes if i.name == PENDING_SESSION_OWNER_INDEX)
    assert index.unique and "chat_session_owner_assign" in str(index.dialect_options["postgresql"]["where"])


def _migration():
    path = Path(__file__).parents[1] / "migrations/versions/20261105_111_approvals_pending_chat_session_owner_unique.py"
    spec = importlib.util.spec_from_file_location("mig111_owner_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run_upgrade(monkeypatch, sessions):
    mod = _migration()
    engine = sa.create_engine("sqlite://")  # canonical: ignore py-adhoc-db-engine
    with engine.begin() as conn:
        conn.execute(sa.text("CREATE TABLE approvals (status TEXT, context JSON)"))
        for session_id in sessions:
            conn.execute(
                sa.text(
                    "INSERT INTO approvals VALUES ('pending', "
                    "json_object('action', 'chat_session_owner_assign', 'session_id', :s))"
                ),
                {"s": session_id},
            )

        def execute(statement):  # this SQLite predates ``->>``
            return conn.execute(
                sa.text(re.sub(r"context ->> '(\w+)'", r"json_extract(context, '$.\1')", str(statement)))
            )

        bind = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"), execute=execute)
        create = MagicMock()
        monkeypatch.setattr(mod.op, "get_bind", lambda: bind)
        monkeypatch.setattr(mod.op, "create_index", create)
        monkeypatch.setattr(mod, "has_table", lambda _t: True)
        monkeypatch.setattr(mod, "has_index", lambda _t, _i: False)
        mod.upgrade()
    return create


def test_the_migration_fails_naming_duplicates(monkeypatch) -> None:
    with pytest.raises(RuntimeError) as err:
        _run_upgrade(monkeypatch, ["s-dup", "s-dup", "s-ok"])
    assert "s-dup (2 pending)" in str(err.value) and "s-ok" not in str(err.value)


def test_the_migration_creates_the_index_without_duplicates(monkeypatch) -> None:
    create = _run_upgrade(monkeypatch, ["s-1", "s-2"])
    assert create.call_args.args[0] == "uq_approvals_pending_chat_session_owner"
