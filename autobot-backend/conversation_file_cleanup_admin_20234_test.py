# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Admin view and reset of stuck cleanups, and the duplicate-refusing migration (#20234, #17038).

The routes run against the real SQLite file store; only auth, the audit sink and the proposer are
stubbed. The migration runs its real ``upgrade()`` on SQLite, which understands ``->>``; PostgreSQL's
index DDL is not executed here.
"""

import importlib.util
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import sqlalchemy as sa
from fastapi import HTTPException

from api import conversation_file_cleanup_admin as admin
from conversation_file_manager import ConversationFileManager

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def manager(tmp_path, monkeypatch):
    mgr = ConversationFileManager(storage_dir=tmp_path / "storage", db_path=tmp_path / "files.db")
    mgr._initialize_schema()
    mgr._invalidate_session_cache = AsyncMock()
    monkeypatch.setattr(
        "services.conversation_file_cleanup_proposals.propose_due_cleanups_logged", AsyncMock(return_value=None)
    )
    return mgr


@pytest.fixture
def request_for(manager, monkeypatch):
    audit = AsyncMock(return_value=True)
    monkeypatch.setattr(admin, "audit_log", audit)
    monkeypatch.setattr(admin, "resolve_human_user", AsyncMock(return_value={"username": "alice"}))
    monkeypatch.setenv("AUTOBOT_CONVERSATION_FILE_CLEANUP_MAX_ATTEMPTS", "2")
    req = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(conversation_file_manager=manager)))
    return req, audit


async def _stuck_file(mgr):
    stored = await mgr.add_file("s1", b"bytes", "a.txt", uploaded_by="u")
    await mgr.delete_file("s1", stored["file_id"])
    conn = await mgr._get_async_db_connection()
    try:
        await conn.execute(
            "CREATE TABLE IF NOT EXISTS file_cleanup_attempts (file_id TEXT PRIMARY KEY, failed_attempts INTEGER "
            "NOT NULL DEFAULT 0, last_failed_at TIMESTAMP, last_reason TEXT)"
        )
        await conn.execute(
            "INSERT INTO file_cleanup_attempts VALUES (?, 2, CURRENT_TIMESTAMP, 'path is outside')",
            (stored["file_id"],),
        )
        await conn.commit()
    finally:
        await conn.close()
    return stored["file_id"]


async def test_status_lists_the_stuck_file(manager, request_for):
    req, _ = request_for
    file_id = await _stuck_file(manager)
    status = await admin.get_cleanup_status(req)
    assert status["stuck_cleanup_files"] == 1 and status["pending_cleanup_files"] == 1
    assert status["stuck_cleanup"][0]["file_id"] == file_id


async def test_reset_clears_the_count_audits_and_removes_no_bytes(manager, request_for):
    req, audit = request_for
    file_id = await _stuck_file(manager)
    path = Path((await manager.get_storage_stats())["storage_directory"])
    before = sorted(p.name for p in path.rglob("*") if p.is_file())

    assert await admin.reset_stuck_cleanup(req, file_id) == {"file_id": file_id, "reset": True}

    assert (await admin.get_cleanup_status(req))["stuck_cleanup_files"] == 0
    assert sorted(p.name for p in path.rglob("*") if p.is_file()) == before, "reset removes no bytes"
    audit.assert_awaited_once()
    assert audit.await_args.args[0] == "conversation_file.cleanup_reset"
    assert audit.await_args.kwargs["user_id"] == "alice"
    assert audit.await_args.kwargs["resource"] == f"conversation_file:{file_id}"


async def test_reset_of_a_file_with_no_refusals_is_404_and_audits_nothing(manager, request_for):
    req, audit = request_for
    with pytest.raises(HTTPException) as err:
        await admin.reset_stuck_cleanup(req, "no-such-file")
    assert err.value.status_code == 404
    audit.assert_not_awaited()


async def test_routes_are_admin_only_and_declared():
    deps = [d.dependency.__name__ for d in admin.router.dependencies]
    assert len(deps) == 1 and "admin_permission" in deps[0]  # the suite may stub the dependency by name
    assert {r.path for r in admin.router.routes} == {"/cleanup/status", "/cleanup/{file_id}/reset"}


def _migration():
    path = Path(__file__).parent / "migrations/versions/20261101_109_approvals_pending_file_cleanup_unique.py"
    spec = importlib.util.spec_from_file_location("mig109_admin_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run_upgrade(mod, monkeypatch, rows):
    engine = sa.create_engine("sqlite://")  # canonical: ignore py-adhoc-db-engine
    with engine.begin() as conn:
        conn.execute(sa.text("CREATE TABLE approvals (status TEXT, requested_by_agent TEXT, context JSON)"))
        for file_id in rows:
            conn.execute(
                sa.text(
                    "INSERT INTO approvals VALUES ('pending', 'conversation-file-cleanup', "
                    "json_object('action', 'conversation_file_cleanup', 'file_id', :f))"
                ),
                {"f": file_id},
            )

        def execute(statement):  # this SQLite predates ``->>``: the same path read with json_extract
            sql = re.sub(r"context ->> '(\w+)'", r"json_extract(context, '$.\1')", str(statement))
            return conn.execute(sa.text(sql))

        bind = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"), execute=execute)
        create = MagicMock()
        monkeypatch.setattr(mod.op, "get_bind", lambda: bind)
        monkeypatch.setattr(mod.op, "create_index", create)
        monkeypatch.setattr(mod, "has_table", lambda _t: True)
        monkeypatch.setattr(mod, "has_index", lambda _t, _i: False)
        mod.upgrade()
    return create


async def test_migration_fails_naming_duplicates_and_changes_nothing(monkeypatch):
    mod = _migration()
    with pytest.raises(RuntimeError) as err:
        _run_upgrade(mod, monkeypatch, ["f-dup", "f-dup", "f-ok"])
    message = str(err.value)
    assert "f-dup (2 pending)" in message and "f-ok" not in message
    assert "Approvals inbox" in message and "Nothing was changed" in message


async def test_migration_creates_the_index_when_there_are_no_duplicates(monkeypatch):
    create = _run_upgrade(_migration(), monkeypatch, ["f-1", "f-2"])
    create.assert_called_once()
    assert create.call_args.args[0] == "uq_approvals_pending_file_cleanup"
