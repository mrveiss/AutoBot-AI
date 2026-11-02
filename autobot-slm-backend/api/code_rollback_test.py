# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""POST /code-sync/rollback and its picker: validation, permission, the gate, the audit order (#20214)."""

from __future__ import annotations

import ast
import os
import subprocess
import sys
import typing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from autobot_shared.paths import scrubbed_git_env

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

# api.code_sync cannot build its routes when models.schemas is the conftest's MagicMock: swap a benign `dict`
# in for every schema name it imports (same technique as tests/api/test_collect_outdated_node_ids.py).
_SCHEMA_NAMES = sorted(
    alias.name
    for node in ast.walk(ast.parse((_ROOT / "api" / "code_sync.py").read_text(encoding="utf-8")))
    if isinstance(node, ast.ImportFrom) and node.module == "models.schemas"
    for alias in node.names
)
if isinstance(sys.modules.get("models.schemas"), MagicMock):
    for _name in _SCHEMA_NAMES:
        setattr(sys.modules["models.schemas"], _name, dict)

from api import code_rollback as api_rb  # noqa: E402
from api import code_sync as cs  # noqa: E402
from models.rollback_schemas import RollbackRequest  # noqa: E402
from services import code_rollback as svc  # noqa: E402
from services import rollback_audit  # noqa: E402
from services.rollback_commits import ROLLBACK_SUPPORT_PATH  # noqa: E402
from services.rollback_migrations import BLOCKED, CLEAR, MigrationCheck  # noqa: E402

_GIT_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
}
USER = {"sub": "alice"}
DEPLOYED = "d" * 40


def _git(repo: Path, *args: str) -> str:
    out = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        env=scrubbed_git_env({**os.environ, **_GIT_ENV}),
    )
    return out.stdout.strip()


def _commit(repo: Path, name: str, support: bool = True) -> str:
    (repo / name).write_text(name, encoding="utf-8")
    _git(repo, "add", name)
    if support:
        module = repo / ROLLBACK_SUPPORT_PATH
        module.parent.mkdir(parents=True, exist_ok=True)
        module.write_text("# reads deploy_ref\n", encoding="utf-8")
        _git(repo, "add", ROLLBACK_SUPPORT_PATH)
    _git(repo, "commit", "-q", "-m", f"change {name}")
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def world(tmp_path, monkeypatch):
    """A real repo (origin/main = three commits, plus a side commit), with the collaborators around it faked."""
    root = tmp_path / "code_source"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    old = _commit(root, "o", support=False)
    first, second, third = (_commit(root, n) for n in ("a", "b", "c"))
    _git(root, "update-ref", "refs/remotes/origin/main", third)
    _git(root, "checkout", "-q", "-b", "side", first)
    side = _commit(root, "d")
    tracker = SimpleNamespace(repo_path=str(root), remote="origin", branch="main")
    monkeypatch.setattr(cs, "_get_tracker_for_db", AsyncMock(return_value=tracker))
    monkeypatch.setattr(cs, "_get_slm_deployed_commit", AsyncMock(return_value=DEPLOYED))
    events: list = []
    monkeypatch.setattr(api_rb, "verify_internal_api_key", lambda key: False)

    async def _audit(**kw):
        events.append(("audit", kw["outcome"], kw["phase"], kw.get("reason")))

    monkeypatch.setattr(rollback_audit, "record_rollback", _audit)

    async def _start(orchestrate=None):
        events.append(("start", orchestrate))
        return cs.UpdateAllJob(job_id="j1", status="pending", created_at="now")

    monkeypatch.setattr(cs, "_start_update_all_locked", _start)
    clear = [MigrationCheck("SLM", CLEAR, message="ok"), MigrationCheck("backend", CLEAR, message="ok")]
    check = AsyncMock(return_value=clear)
    monkeypatch.setattr(svc, "check_migrations", check)
    return SimpleNamespace(old=old, first=first, second=second, third=third, side=side, events=events, check=check)


def _request(key: str | None = None):
    return SimpleNamespace(headers={"X-Internal-API-Key": key} if key else {})


async def _post(commit: str, request=None, user=USER):
    return await api_rb.start_rollback(RollbackRequest(commit=commit), request or _request(), None, user)


async def test_picker_lists_ancestors_with_dates_and_subjects_and_marks_nothing_pickable_outside_main(world):
    result = await api_rb.rollback_candidates(None, USER)
    assert [c.commit for c in result.commits] == [world.third, world.second, world.first]
    assert [c.subject for c in result.commits][0] == "change c"
    assert all(c.date and c.short == c.commit[:12] for c in result.commits)
    assert result.branch == "main" and result.deployed_commit == DEPLOYED


async def test_a_clear_path_starts_and_the_run_is_handed_the_chosen_commit(world):
    job = await _post(world.second)
    assert job.job_id == "j1"
    kinds = [e[0] for e in world.events]
    assert kinds == ["audit", "start"]
    orchestrate = world.events[1][1]
    assert callable(orchestrate) and orchestrate.__name__ == "_orchestrate"
    assert world.events[0][1:3] == ("success", "requested")
    assert world.check.await_args.args[1] == world.second  # the migration check ran against the chosen commit


@pytest.mark.parametrize("junk", ["", "main", "--output=x", "../../etc/passwd", "a" * 40 + "\n", "0" * 40])
async def test_junk_or_unknown_commit_is_refused_and_nothing_runs(world, junk):
    with pytest.raises(HTTPException) as err:
        await _post(junk)
    assert err.value.status_code == 400
    assert [e[:3] for e in world.events] == [("audit", "denied", "requested")]


async def test_a_commit_outside_main_is_refused(world):
    with pytest.raises(HTTPException) as err:
        await _post(world.side)
    assert err.value.status_code == 400 and "not part of main" in err.value.detail
    assert [e[0] for e in world.events] == ["audit"]


async def test_a_migration_in_the_way_is_refused_with_a_message_naming_it_and_nothing_runs(world):
    world.check.return_value = [
        MigrationCheck("SLM", CLEAR, message="ok"),
        MigrationCheck(
            "backend",
            BLOCKED,
            ["20260901_099"],
            "The backend database has 1 migration(s) applied that the chosen commit does not have.",
        ),
    ]
    with pytest.raises(HTTPException) as err:
        await _post(world.first)
    assert err.value.status_code == 409
    assert "backend database has 1 migration" in err.value.detail
    assert [e[:3] for e in world.events] == [("audit", "denied", "requested")]


async def test_preview_reports_the_blocking_database_without_starting_anything(world):
    world.check.return_value = [MigrationCheck("SLM", BLOCKED, ["m9"], "in the way"), MigrationCheck("backend", CLEAR)]
    preview = await api_rb.rollback_preview(world.first, None, USER)
    assert preview.allowed is False and preview.refusal == "in the way"
    assert preview.checks[0].in_the_way == ["m9"]
    assert world.events == []


async def test_preview_of_a_clear_commit_is_allowed(world):
    preview = await api_rb.rollback_preview(world.second, None, USER)
    assert preview.allowed is True and preview.refusal is None and preview.commit.subject == "change b"


async def test_refused_while_an_update_is_running_through_the_same_gate_as_update_everything():
    running = cs.UpdateAllJob(
        job_id="busy", status="running", created_at=cs.utc_timestamp(), last_progress_at=cs.utc_timestamp()
    )
    cs._set_update_all_job(running)
    try:
        with pytest.raises(HTTPException) as err:
            await cs._start_update_all_locked(orchestrate=lambda *a: None)
    finally:
        running.status = "failed"
    assert err.value.status_code == 409 and "already running" in err.value.detail


async def test_a_busy_gate_is_audited_as_denied_after_the_request_entry(world, monkeypatch):
    async def _busy(orchestrate=None):
        raise HTTPException(status_code=409, detail="An update-all job is already running (job_id=x)")

    monkeypatch.setattr(cs, "_start_update_all_locked", _busy)
    with pytest.raises(HTTPException) as err:
        await _post(world.second)
    assert err.value.status_code == 409
    assert [e[:3] for e in world.events] == [("audit", "success", "requested"), ("audit", "denied", "requested")]


async def test_the_audit_entry_is_written_before_the_run_starts(world):
    await _post(world.second)
    assert [e[0] for e in world.events].index("audit") < [e[0] for e in world.events].index("start")


async def test_if_the_audit_trail_cannot_record_the_request_nothing_runs(world, monkeypatch):
    monkeypatch.setattr(
        rollback_audit, "record_rollback", AsyncMock(side_effect=rollback_audit.RollbackAuditUnavailable("x"))
    )
    with pytest.raises(HTTPException) as err:
        await _post(world.second)
    assert err.value.status_code == 503
    assert not [e for e in world.events if e[0] == "start"]


def _dependency(func, param):
    """The callable a parameter's ``Annotated[..., Depends(x)]`` names."""
    hint = typing.get_type_hints(func, include_extras=True)[param]
    return next(m.dependency for m in hint.__metadata__ if hasattr(m, "dependency"))


def test_permission_is_the_same_as_update_everything():
    assert _dependency(api_rb.start_rollback, "user") is _dependency(cs.start_update_all, "_")
    for handler in (api_rb.rollback_candidates, api_rb.rollback_preview):
        assert _dependency(handler, "_") is _dependency(cs.start_update_all, "_")


def test_the_routes_ride_the_code_sync_router_so_they_carry_its_include_level_auth():
    init = (_ROOT / "api" / "__init__.py").read_text(encoding="utf-8")
    assert "code_sync_router.include_router(code_rollback_router)" in init
    assert "from .code_rollback import router as code_rollback_router" in init
    assert api_rb.router.prefix == "/rollback"
    assert {(sorted(r.methods)[0], r.path) for r in api_rb.router.routes} == {
        ("GET", "/rollback/candidates"),
        ("GET", "/rollback/preview"),
        ("POST", "/rollback"),
    }


def test_audit_outcomes_are_only_the_four_allowed_ones():
    assert rollback_audit.OUTCOMES == {"success", "denied", "failed", "error"}


async def test_the_internal_service_key_cannot_roll_back(world, monkeypatch):
    monkeypatch.setattr(api_rb, "verify_internal_api_key", lambda key: key == "the-key")
    with pytest.raises(HTTPException) as err:
        await _post(world.second, request=_request("the-key"))
    assert err.value.status_code == 403 and "person" in err.value.detail
    assert world.events == []


async def test_a_token_that_names_nobody_cannot_roll_back(world):
    with pytest.raises(HTTPException) as err:
        await _post(world.second, user={})
    assert err.value.status_code == 403 and world.events == []


async def test_a_denied_row_never_stores_the_clients_text(world, monkeypatch):
    seen = []

    async def _audit(**kw):
        seen.append(kw)

    monkeypatch.setattr(rollback_audit, "record_rollback", _audit)
    with pytest.raises(HTTPException):
        await _post("<script>alert(1)</script>")
    assert seen and seen[0]["commit"] is None
    assert "script" not in repr(seen)


async def test_a_commit_that_predates_rollback_support_is_refused_with_a_plain_reason(world):
    with pytest.raises(HTTPException) as err:
        await _post(world.old)
    assert err.value.status_code == 400 and "predates rollback support" in err.value.detail


def test_the_routes_answer_403_while_rollback_is_off(monkeypatch):
    monkeypatch.delenv("SLM_ROLLBACK_ENABLED", raising=False)
    with pytest.raises(HTTPException) as err:
        api_rb.require_rollback_enabled()
    assert err.value.status_code == 403 and "not enabled" in err.value.detail
    monkeypatch.setenv("SLM_ROLLBACK_ENABLED", "true")
    api_rb.require_rollback_enabled()
    assert any(d.dependency is api_rb.require_rollback_enabled for d in api_rb.router.dependencies)
