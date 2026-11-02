# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A workflow command step runs the command it was given (#19807).

``_execute_command`` slept and returned exit 0 with "Simulated output", so every
command step "succeeded" and ran nothing. These tests drive the real
``SecurityLayer.execute_command`` path with real processes; only the audit sink is
stood in for, so the recording sites can be inspected.
"""

import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles
from starlette.testclient import TestClient

from auth_middleware import get_current_user
from security_layer import SecurityLayer
from user_management.models import Role, User, UserRole
from user_management.models.base import Base
from utils.bounded_subprocess import run_bounded

from . import command_step, routes
from .command_step import CommandStepFailed, run_command_step

SECRET = "hunter2-s3cr3t-value"  # pragma: allowlist secret


def _mask(text: str) -> str:
    return text.replace(SECRET, "***")


_OWNER = uuid.UUID(int=19807)
_TABLES = [User.__table__, UserRole.__table__, Role.__table__]


@compiles(JSONB, "sqlite")
def _compile_jsonb_as_json_on_sqlite(element, compiler, **kw):  # noqa: ANN001
    return "JSON"


@asynccontextmanager
async def _session_scope(factory):
    async with factory() as session:
        yield session


async def _seed(factory, user_id: uuid.UUID = _OWNER, **fields) -> None:
    """Commit a real user row; an admin by default, as login would issue the ``admin`` role for."""
    row = {
        "id": user_id,
        "email": f"{user_id}@example.invalid",
        "username": f"user-{user_id}",
        "password_hash": None,
        "display_name": "u",
        "org_id": None,
        "is_platform_admin": True,
        "is_active": True,
        "is_verified": False,
        "mfa_enabled": False,
        "preferences": {},
    }
    async with factory() as session:
        session.add(User(**{**row, **fields}))
        await session.commit()


async def _update(factory, **fields) -> None:
    """Change the owner's row after the workflow was created (demotion, deactivation, deletion)."""
    async with factory() as session:
        await session.execute(User.__table__.update().where(User.__table__.c.id == _OWNER).values(**fields))
        await session.commit()


@pytest_asyncio.fixture
async def layer(monkeypatch, tmp_path):
    """A real SecurityLayer and a real user database (in-memory); audit records are captured, not stored."""
    audit = []
    monkeypatch.setattr(command_step, "WORKFLOW_COMMAND_CWD", str(tmp_path))
    engine = create_async_engine("sqlite+aiosqlite://")  # canonical: ignore py-adhoc-db-engine (test-local, in-memory)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=_TABLES)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)  # canonical: ignore py-adhoc-db-engine
    await _seed(factory)
    monkeypatch.setattr(command_step, "db_session_context", lambda: _session_scope(factory))
    with patch("security_layer.emit_security", side_effect=lambda *a, **k: audit.append((a, k)) or True):
        security = SecurityLayer()
        security.audit = audit
        security.db = factory
        monkeypatch.setattr(command_step, "get_security_layer", lambda: security)
        try:
            yield security
        finally:
            await engine.dispose()


def _write_big_file(path) -> None:
    """A file whose lines hold the secret, large enough that the filter tees it."""
    path.write_text((SECRET + " " + "x" * 40 + "\n") * 4000, encoding="utf-8")


def _assert_tee_is_clean(tee) -> None:
    """The tee directory holds something, and neither a name nor a body carries the secret."""
    written = list(tee.iterdir()) if tee.exists() else []
    assert written, "the filter did not tee, so this proves nothing"
    assert all(SECRET not in f.name and SECRET not in f.read_text(encoding="utf-8") for f in written)


def _signal_recorded_pid(pid_file) -> None:
    """Probe the pid the command recorded; raises ProcessLookupError once it is gone."""
    os.kill(int(pid_file.read_text(encoding="utf-8")), 0)


async def _run(command: str, redactor=_mask, user: str | None = str(_OWNER)):
    return await run_command_step(command, user=user, value_redactor=redactor)


@pytest.mark.asyncio
async def test_stdout_is_the_commands_output_and_exit_is_real(layer):
    result = await _run("echo hello-19807")
    assert result["stdout"] == "hello-19807"
    assert result["exit_code"] == 0
    assert "Simulated" not in str(result)


@pytest.mark.asyncio
async def test_non_zero_exit_fails_the_step_with_real_code_and_stderr(layer):
    with pytest.raises(CommandStepFailed) as failed:
        await _run("ls /nonexistent-19807-dir")
    result = failed.value.result
    assert result["exit_code"] != 0
    assert "nonexistent-19807-dir" in result["stderr"]
    assert str(result["exit_code"]) in str(failed.value)


@pytest.mark.asyncio
async def test_a_command_needing_approval_is_refused_and_nothing_runs(layer):
    with patch("secure_command_executor.execute_shell_command", new=AsyncMock()) as ran:
        with pytest.raises(CommandStepFailed) as failed:
            await _run("frobnicate-19807 --now")
    ran.assert_not_called()
    assert failed.value.result["refused"] is True
    assert failed.value.result["exit_code"] != 0


async def _refused_with_nothing_run(**kwargs):
    """Run a step expecting a refusal; returns the failure after asserting no process started."""
    with patch("secure_command_executor.execute_shell_command", new=AsyncMock()) as ran:
        with pytest.raises(CommandStepFailed) as failed:
            await _run("echo hi", **kwargs)
    ran.assert_not_called()
    assert failed.value.result["refused"] is True and failed.value.result["exit_code"] == 1
    return failed.value


@pytest.mark.asyncio
async def test_a_plain_database_user_is_refused_by_the_permission_check(layer):
    """A non-admin account is issued the ``user`` role, which lacks allow_shell_execute."""
    plain = uuid.uuid4()
    await _seed(layer.db, plain, is_platform_admin=False)
    failure = await _refused_with_nothing_run(user=str(plain))
    assert "shell execution privileges" in failure.result["stderr"]


@pytest.mark.asyncio
async def test_an_unchanged_platform_admin_row_runs_end_to_end(layer):
    result = await _run("echo from-a-real-row")
    assert result["stdout"] == "from-a-real-row" and result["exit_code"] == 0


@pytest.mark.asyncio
async def test_a_demoted_owner_runs_nothing(layer):
    assert (await _run("echo hi"))["exit_code"] == 0
    await _update(layer.db, is_platform_admin=False)  # demoted after the workflow was created
    await _refused_with_nothing_run()


@pytest.mark.asyncio
async def test_a_deactivated_owner_runs_nothing(layer):
    await _update(layer.db, is_active=False)
    failure = await _refused_with_nothing_run()
    assert "no longer holds an active account" in failure.result["stderr"]


@pytest.mark.asyncio
async def test_a_deleted_owner_runs_nothing(layer):
    await _update(layer.db, deleted_at=datetime.now(tz=timezone.utc))
    await _refused_with_nothing_run()


@pytest.mark.asyncio
async def test_an_owner_with_no_row_or_no_account_id_runs_nothing(layer):
    await _refused_with_nothing_run(user=str(uuid.uuid4()))
    await _refused_with_nothing_run(user="admin")  # the synthetic auth-off admin is not an account row
    await _refused_with_nothing_run(user=None)


@pytest.mark.asyncio
async def test_a_store_failure_refuses_the_step(layer, monkeypatch):
    def _down():
        raise ConnectionError("database unreachable")

    monkeypatch.setattr(command_step, "db_session_context", _down)
    failure = await _refused_with_nothing_run()
    assert "could not be verified" in failure.result["stderr"]


@pytest.mark.asyncio
async def test_a_secret_value_reaches_no_record_and_no_result(layer):
    result = await _run(f"echo {SECRET}")
    assert result["stdout"] == "***"
    recorded = str(layer.audit) + str(layer.command_executor.command_history) + str(result)
    assert SECRET not in recorded
    assert "command_execution_complete" in recorded


@pytest.mark.asyncio
async def test_a_timeout_fails_the_step_with_exit_124(layer, monkeypatch):
    monkeypatch.setattr(command_step, "WORKFLOW_COMMAND_TIMEOUT_S", 1)
    with pytest.raises(CommandStepFailed) as failed:
        await _run("tail -f /dev/null")
    assert failed.value.result["exit_code"] == 124
    assert "timed out" in failed.value.result["stderr"]


@pytest.mark.asyncio
async def test_a_timeout_kills_the_child_not_only_the_shell(tmp_path):
    pid_file = tmp_path / "pid"
    run = await run_bounded(
        f"echo $$ > {pid_file}; sleep 60; true", cwd=str(tmp_path), timeout_s=1, max_output_bytes=1000
    )
    assert run.timed_out is True
    with pytest.raises(ProcessLookupError):
        _signal_recorded_pid(pid_file)


@pytest.mark.asyncio
async def test_output_is_capped_per_stream(tmp_path):
    run = await run_bounded("yes | head -c 100000", cwd=str(tmp_path), timeout_s=10, max_output_bytes=1000)
    assert len(run.stdout) == 1000 and run.truncated is True and run.return_code == 0


@pytest.mark.asyncio
async def test_the_command_runs_in_the_configured_directory(layer, tmp_path):
    result = await _run("pwd")
    assert result["stdout"] == str(tmp_path.resolve())


def _client(monkeypatch, user):
    created = []

    class _Manager:
        async def create_automated_workflow(self, **kwargs):
            created.append(kwargs)
            return "wf-1"

        async def create_workflow_from_chat_request(self, *args, **kwargs):
            created.append(kwargs)
            return None

    monkeypatch.setattr(routes, "get_workflow_manager", lambda: _Manager())
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app, raise_server_exceptions=False), created


_CREATE = ("/create_workflow", {"name": "w", "description": "", "steps": [], "session_id": "s"})
_CHAT = ("/create_from_chat", {"user_request": "list files", "session_id": "s"})


@pytest.mark.parametrize("path,body", [_CREATE, _CHAT])
def test_a_user_without_shell_permission_cannot_create_a_workflow(monkeypatch, path, body):
    client, created = _client(monkeypatch, {"user_id": "u-1", "role": "user"})
    assert client.post(path, json=body).status_code == 403
    assert created == []


@pytest.mark.parametrize("path,body", [_CREATE, _CHAT])
def test_a_user_who_may_run_commands_can_create_a_workflow(monkeypatch, path, body):
    client, created = _client(monkeypatch, {"user_id": "u-1", "role": "operator"})
    assert client.post(path, json=body).status_code == 200


def test_create_from_chat_reports_a_missing_field_as_400_not_500(monkeypatch):
    client, created = _client(monkeypatch, {"user_id": "u-1", "role": "operator"})
    response = client.post("/create_from_chat", json={"user_request": "", "session_id": "s"})
    assert response.status_code == 400
    assert created == []


@pytest.mark.asyncio
async def test_the_filter_savings_failure_log_does_not_carry_the_command(monkeypatch, caplog):
    import logging

    from services import tool_output_filter

    async def _broken():
        raise RuntimeError("redis down")

    monkeypatch.setattr("autobot_shared.redis_client.get_async_redis_client", _broken)
    with caplog.at_level(logging.DEBUG, logger=tool_output_filter.logger.name):
        await tool_output_filter.record_filter_savings(f"echo {SECRET}", 10)
    assert "record_filter_savings: failed" in caplog.text
    assert SECRET not in caplog.text


@pytest.mark.asyncio
async def test_a_chained_command_with_a_secret_reaches_no_history_or_audit_row(layer):
    result = await _run(f"echo {SECRET} && echo done")
    assert result["exit_code"] == 0
    rows = str(layer.audit) + str(layer.command_executor.command_history)
    assert "Chained command" in rows, "the chained-reason path was not exercised"
    assert SECRET not in rows


@pytest.mark.asyncio
async def test_no_unredacted_output_or_name_reaches_the_tee_directory(layer, monkeypatch, tmp_path):
    from services import tool_output_filter

    tee = tmp_path / "tee"
    monkeypatch.setattr(tool_output_filter, "_TEE_DIR", tee)
    big = tmp_path / "big.txt"
    _write_big_file(big)
    result = await _run("cat big.txt")
    assert result["exit_code"] == 0
    _assert_tee_is_clean(tee)


def _rule(layer, action, rule_info):
    return patch.object(
        layer.command_executor, "check_permission_rules", new=AsyncMock(return_value=(action, rule_info))
    )


@pytest.mark.asyncio
async def test_approval_memory_does_not_count_under_a_policy(layer):
    with _rule(layer, "allow", {"action": "allow", "from_memory": True}):
        with patch("secure_command_executor.execute_shell_command", new=AsyncMock()) as ran:
            with pytest.raises(CommandStepFailed) as failed:
                await _run("frobnicate-19807 --now")
    ran.assert_not_called()
    assert failed.value.result["refused"] is True


@pytest.mark.asyncio
async def test_an_explicit_permission_rule_still_allows(layer):
    run = AsyncMock(return_value={"stdout": "ok", "stderr": "", "return_code": 0, "status": "success"})
    with _rule(layer, "allow", {"action": "allow", "pattern": "frobnicate*"}):
        with patch("secure_command_executor.execute_shell_command", new=run):
            result = await _run("frobnicate-19807 --now")
    run.assert_called_once()
    assert result["stdout"] == "ok"


@pytest.mark.asyncio
async def test_a_rule_does_not_lift_a_block_under_a_policy(layer):
    with _rule(layer, "allow", {"action": "allow", "pattern": "*"}):
        with patch("secure_command_executor.execute_shell_command", new=AsyncMock()) as ran:
            with pytest.raises(CommandStepFailed) as failed:
                await _run("rm -rf /")
    ran.assert_not_called()
    assert failed.value.result["refused"] is True


@pytest.mark.asyncio
async def test_disabled_command_security_refuses_the_step(layer):
    layer.enable_command_security = False
    with patch("secure_command_executor.execute_shell_command", new=AsyncMock()) as ran:
        with pytest.raises(CommandStepFailed) as failed:
            await _run("echo hi")
    ran.assert_not_called()
    assert failed.value.result["refused"] is True
    assert "security is disabled" in failed.value.result["stderr"]
