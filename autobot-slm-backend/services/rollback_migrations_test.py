# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A migration in the way of a rollback is detected from real git, against the applied state (#20214)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from autobot_shared.paths import scrubbed_git_env
from services.rollback_migrations import (
    BLOCKED,
    CLEAR,
    UNKNOWN,
    check_migrations,
    parse_backend_revisions,
    parse_slm_migrations,
)

_GIT_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
}


def _git(repo: Path, *args: str) -> str:
    out = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        env=scrubbed_git_env({**os.environ, **_GIT_ENV}),
    )
    return out.stdout.strip()


def _write(repo: Path, rel: str, text: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _runner(*names: str) -> str:
    return "MIGRATIONS = [\n" + "".join(f'    "{n}",\n' for n in names) + "]\n"


def _alembic(revision: str, down: str | None) -> str:
    return f'"""m"""\nrevision: str = "{revision}"\ndown_revision = {down!r}\n'


def _snapshot(repo: Path, slm: tuple[str, ...] | None, backend: dict[str, str | None]) -> str:
    """Commit one tree: an SLM runner (or none) and alembic files {revision: down_revision}."""
    if slm is not None:
        _write(repo, "autobot-slm-backend/migrations/runner.py", _runner(*slm))
    for rev, down in backend.items():
        _write(repo, f"autobot-backend/migrations/versions/{rev}_x.py", _alembic(rev, down))
    _write(repo, "marker.txt", str(len(list(repo.rglob("*")))))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "snapshot")
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "code_source"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    return root


def _reader(names: list[str]):
    async def _read() -> list[str]:
        return names

    return _read


def _broken(exc: Exception):
    async def _read() -> list[str]:
        raise exc

    return _read


async def _verdicts(repo, commit, slm_applied, backend_applied):
    checks = await check_migrations(str(repo), commit, _reader(slm_applied), _reader(backend_applied))
    return {c.database: c for c in checks}


async def test_database_ahead_of_target_is_blocked_and_names_what_is_in_the_way(repo):
    old = _snapshot(repo, ("m1", "m2"), {"r1": None, "r2": "r1"})
    _snapshot(repo, ("m1", "m2", "m3"), {"r1": None, "r2": "r1", "r3": "r2"})
    result = await _verdicts(repo, old, ["m1", "m2", "m3"], ["r3"])
    assert result["SLM"].status == BLOCKED
    assert result["SLM"].in_the_way == ["m3"]
    assert "does not have" in result["SLM"].message and "downgrade" in result["SLM"].message
    assert result["backend"].status == BLOCKED
    assert result["backend"].in_the_way == ["r3"]


async def test_each_database_is_judged_on_its_own(repo):
    old = _snapshot(repo, ("m1",), {"r1": None})
    result = await _verdicts(repo, old, ["m1"], ["r1", "r2"])
    assert (result["SLM"].status, result["backend"].status) == (CLEAR, BLOCKED)


async def test_a_clear_path_is_allowed_when_the_database_is_at_or_behind_the_target(repo):
    target = _snapshot(repo, ("m1", "m2"), {"r1": None, "r2": "r1"})
    at = await _verdicts(repo, target, ["m1", "m2"], ["r2"])
    behind = await _verdicts(repo, target, ["m1"], ["r1"])
    assert all(c.status == CLEAR for c in {**at, **{f"b{k}": v for k, v in behind.items()}}.values())


async def test_an_unreadable_database_is_unknown_and_not_clear(repo):
    target = _snapshot(repo, ("m1",), {"r1": None})
    checks = await check_migrations(
        str(repo), target, _broken(ConnectionRefusedError("refused for login xyzzy-credential")), _reader(["r1"])
    )
    slm = {c.database: c for c in checks}["SLM"]
    assert slm.status == UNKNOWN
    assert "ConnectionRefusedError" in slm.message and "xyzzy" not in slm.message


async def test_a_target_that_ships_no_migration_list_is_unknown(repo):
    target = _snapshot(repo, None, {})
    result = await _verdicts(repo, target, ["m1"], ["r1"])
    assert result["SLM"].status == UNKNOWN and result["backend"].status == UNKNOWN


async def test_check_refuses_anything_but_a_full_commit_id(repo):
    with pytest.raises(ValueError):
        await check_migrations(str(repo), "--output=x", _reader([]), _reader([]))


def test_parsers_read_literals_without_executing_anything():
    assert parse_slm_migrations('MIGRATIONS = ["a", "b"]\n') == ["a", "b"]
    assert parse_slm_migrations('MIGRATIONS: list = ["a"]\n') == ["a"]
    assert parse_slm_migrations("MIGRATIONS = [x for x in range(3)]\n") is None
    assert parse_slm_migrations('MIGRATIONS = ["a", NAME]\n') is None
    assert parse_slm_migrations("def (") is None
    assert parse_slm_migrations("OTHER = []\n") is None
    out = 'revision: str = "abc"\nrevision = \'def\'\ndown_revision = "zzz"\nx/some-revision.py:revision = "q"\n'
    assert parse_backend_revisions(out) == ["abc", "def", "q"]
