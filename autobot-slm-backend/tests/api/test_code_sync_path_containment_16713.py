# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the CodeQL py/path-injection containment guards fixed in #16713.

Split out of test_code_sync_deploy_bugs.py (grandfathered at its own #14236
ceiling, #16229 review precedent) rather than grown in place — moving these
cases out, rather than adding new ones alongside them, is what keeps that
file's line count from crossing its recorded ceiling.

Covers:
  - _deploy_constraints_dir / _deploy_repo_root_requirements
    (api/code_sync_paths.py): source_root must resolve under the
    code_source root (_get_code_source_root()).
  - _run_alembic_migrations / _pg_dump_before_migration (api/code_sync.py):
    the alembic config path and the pg_dump backup path must resolve under
    their own trusted roots (SLM_DEPLOYED_ROOT / _DB_BACKUP_DIR).

Each "skipped"/"calls"/"records_failure" test below is the pre-existing
#11322/#11336/#11376 coverage, relocated verbatim except for the new
containment-guard patch each now needs to keep passing. Each
"refuses_traversal" test is new: it proves a component/source_root value
that escapes the trusted root is rejected before any filesystem call.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# #12572: import api.code_sync via the shared helper — see
# test_code_sync_deploy_bugs.py's header for the full rationale.
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _code_sync_import import import_code_sync, patch_real_deployed_root  # noqa: E402

import_code_sync()

import asyncio  # noqa: E402

from api.code_sync import _pg_dump_before_migration, _run_alembic_migrations  # noqa: E402
from api.code_sync_paths import _deploy_constraints_dir, _deploy_repo_root_requirements  # noqa: E402


def _run(coro):
    # A dedicated loop per call — see test_code_sync_deploy_bugs.py's _run.
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# _deploy_constraints_dir
# ---------------------------------------------------------------------------


def test_deploy_constraints_dir_skipped_when_source_missing(tmp_path) -> None:
    """Step says 'not found' when the source dir doesn't exist (#11322)."""
    steps: list[str] = []
    with patch("api.code_sync._get_code_source_root", return_value=tmp_path):
        _run(_deploy_constraints_dir(str(tmp_path / "no_such_root"), steps))
    assert any("not found" in s for s in steps)


def test_deploy_constraints_dir_calls_rsync(tmp_path) -> None:
    """rsync is called when the source dir exists (#11322)."""
    src_root = tmp_path / "code_source"
    (src_root / "constraints").mkdir(parents=True)

    steps: list[str] = []
    captured: list = []

    async def _fake_exec(*cmd, **kw):
        captured.extend(cmd)
        proc = MagicMock()
        proc.returncode = 0
        proc.communicate = AsyncMock(return_value=(b"", b""))
        return proc

    with (
        patch("asyncio.create_subprocess_exec", side_effect=_fake_exec),
        patch("api.code_sync._get_code_source_root", return_value=tmp_path),
    ):
        _run(_deploy_constraints_dir(str(src_root), steps))

    assert "rsync" in captured
    assert any("deployed ok" in s for s in steps)


def test_deploy_constraints_dir_records_rsync_failure(tmp_path) -> None:
    """Non-zero rsync rc is recorded in steps (#11322)."""
    src_root = tmp_path / "code_source"
    (src_root / "constraints").mkdir(parents=True)

    steps: list[str] = []

    async def _fake_exec(*cmd, **kw):
        proc = MagicMock()
        proc.returncode = 23
        proc.communicate = AsyncMock(return_value=(b"error", b""))
        return proc

    with (
        patch("asyncio.create_subprocess_exec", side_effect=_fake_exec),
        patch("api.code_sync._get_code_source_root", return_value=tmp_path),
    ):
        _run(_deploy_constraints_dir(str(src_root), steps))

    assert any("failed" in s for s in steps)


def test_deploy_constraints_dir_refuses_traversal_before_filesystem_access(tmp_path) -> None:
    """A component-derived source_root escaping the code_source root is refused
    before any filesystem call is made."""
    outside = tmp_path / "outside"
    outside.mkdir()
    code_source_root = tmp_path / "code_source"
    code_source_root.mkdir()

    steps: list[str] = []
    with (
        patch("api.code_sync._get_code_source_root", return_value=code_source_root),
        patch("pathlib.Path.exists") as mock_exists,
        patch("asyncio.create_subprocess_exec") as mock_exec,
    ):
        with pytest.raises(ValueError, match="resolves outside"):
            _run(_deploy_constraints_dir(str(outside / ".." / ".." / "etc"), steps))

    mock_exists.assert_not_called()
    mock_exec.assert_not_called()


# ---------------------------------------------------------------------------
# _deploy_repo_root_requirements
# ---------------------------------------------------------------------------


def test_deploy_repo_root_requirements_skipped_when_file_missing(tmp_path) -> None:
    """Step says 'not found' when the source file doesn't exist (#11336)."""
    steps: list[str] = []
    with (
        patch("api.code_sync._get_deploy_base", return_value=tmp_path),
        patch("api.code_sync._get_code_source_root", return_value=tmp_path),
    ):
        _run(_deploy_repo_root_requirements(str(tmp_path / "no_such_root"), steps))
    assert any("not found" in s for s in steps)


def test_deploy_repo_root_requirements_calls_cp(tmp_path) -> None:
    """cp is called when the source file exists (#11336)."""
    src_root = tmp_path / "code_source"
    src_root.mkdir()
    (src_root / "requirements.txt").write_text("paramiko>=5.0.0\n", encoding="utf-8")
    dst_base = tmp_path / "opt_autobot"
    dst_base.mkdir()

    steps: list[str] = []
    captured: list = []

    async def _fake_exec(*cmd, **kw):
        captured.extend(cmd)
        proc = MagicMock()
        proc.returncode = 0
        proc.communicate = AsyncMock(return_value=(b"", b""))
        return proc

    with (
        patch("asyncio.create_subprocess_exec", side_effect=_fake_exec),
        patch("api.code_sync._get_deploy_base", return_value=dst_base),
        patch("api.code_sync._get_code_source_root", return_value=tmp_path),
    ):
        _run(_deploy_repo_root_requirements(str(src_root), steps))

    assert "cp" in captured
    assert any("deployed ok" in s for s in steps)


def test_deploy_repo_root_requirements_records_cp_failure(tmp_path) -> None:
    """Non-zero cp rc is recorded in steps (#11336)."""
    src_root = tmp_path / "code_source"
    src_root.mkdir()
    (src_root / "requirements.txt").write_text("paramiko>=5.0.0\n", encoding="utf-8")
    dst_base = tmp_path / "opt_autobot"
    dst_base.mkdir()

    steps: list[str] = []

    async def _fake_exec(*cmd, **kw):
        proc = MagicMock()
        proc.returncode = 1
        proc.communicate = AsyncMock(return_value=(b"permission denied", b""))
        return proc

    with (
        patch("asyncio.create_subprocess_exec", side_effect=_fake_exec),
        patch("api.code_sync._get_deploy_base", return_value=dst_base),
        patch("api.code_sync._get_code_source_root", return_value=tmp_path),
    ):
        _run(_deploy_repo_root_requirements(str(src_root), steps))

    assert any("failed" in s for s in steps)


def test_deploy_repo_root_requirements_refuses_traversal_before_filesystem_access(tmp_path) -> None:
    """A component-derived source_root escaping the code_source root is refused
    before any filesystem call is made."""
    code_source_root = tmp_path / "code_source"
    code_source_root.mkdir()
    dst_base = tmp_path / "opt_autobot"
    dst_base.mkdir()

    steps: list[str] = []
    with (
        patch("api.code_sync._get_deploy_base", return_value=dst_base),
        patch("api.code_sync._get_code_source_root", return_value=code_source_root),
        patch("pathlib.Path.exists") as mock_exists,
        patch("asyncio.create_subprocess_exec") as mock_exec,
    ):
        with pytest.raises(ValueError, match="resolves outside"):
            _run(_deploy_repo_root_requirements(str(tmp_path / ".." / "etc"), steps))

    mock_exists.assert_not_called()
    mock_exec.assert_not_called()


# ---------------------------------------------------------------------------
# _run_alembic_migrations
# ---------------------------------------------------------------------------


def test_alembic_aborted_when_dump_fails(tmp_path, monkeypatch) -> None:
    """Migration must not run if pg_dump returns None (#11376)."""
    patch_real_deployed_root(monkeypatch, tmp_path)
    executed: list[str] = []

    async def _fake_dump(component, deployed_dir, steps):
        steps.append("pg_dump: FAILED (rc=1): some error")
        return None

    async def _fake_exec(*cmd, **kw):
        executed.extend(cmd)
        proc = MagicMock()
        proc.returncode = 0
        proc.communicate = AsyncMock(return_value=(b"", b""))
        return proc

    deployed = tmp_path / "autobot-backend"
    deployed.mkdir()
    (deployed / "migrations").mkdir()
    (deployed / "migrations" / "alembic.ini").write_text("[alembic]\n", encoding="utf-8")

    with (
        patch(
            "api.code_sync._COMPONENT_MIGRATION_CONFIG",
            {"autobot-backend": "migrations/alembic.ini"},
        ),
        patch("api.code_sync._COMPONENT_PIP_PATHS", {"autobot-backend": ("req.txt", str(deployed / "venv/bin/pip"))}),
        patch("pathlib.Path.exists", return_value=True),
        patch("api.code_sync._pg_dump_before_migration", side_effect=_fake_dump),
        patch("asyncio.create_subprocess_exec", side_effect=_fake_exec),
    ):
        steps: list[str] = []
        result = _run(_run_alembic_migrations("autobot-backend", str(deployed), steps))

    assert result is False
    assert not executed, "alembic must NOT execute when pg_dump fails"
    assert any("ABORTED" in s for s in steps)


def test_run_alembic_migrations_refuses_traversal_before_filesystem_access(tmp_path, monkeypatch) -> None:
    """A deployed_dir escaping SLM_DEPLOYED_ROOT is refused before any
    filesystem call or subprocess spawn."""
    patch_real_deployed_root(monkeypatch, tmp_path)
    escaping_dir = str(tmp_path / ".." / "escape" / "autobot-backend")

    with (
        patch(
            "api.code_sync._COMPONENT_MIGRATION_CONFIG",
            {"autobot-backend": "migrations/alembic.ini"},
        ),
        patch(
            "api.code_sync._COMPONENT_PIP_PATHS",
            {"autobot-backend": ("req.txt", str(tmp_path / "venv" / "bin" / "pip"))},
        ),
        patch("pathlib.Path.exists") as mock_exists,
        patch("asyncio.create_subprocess_exec") as mock_exec,
    ):
        steps: list[str] = []
        result = _run(_run_alembic_migrations("autobot-backend", escaping_dir, steps))

    assert result is False
    mock_exists.assert_not_called()
    mock_exec.assert_not_called()
    assert any("outside the deployed root" in s for s in steps), steps


# ---------------------------------------------------------------------------
# _pg_dump_before_migration
# ---------------------------------------------------------------------------


def test_pg_dump_refuses_component_traversal_before_subprocess(tmp_path, monkeypatch) -> None:
    """A component value escaping the pg_dump backup directory is refused
    before pg_dump is ever spawned."""
    patch_real_deployed_root(monkeypatch, tmp_path)
    db_dsn = "postgresql://" + "localhost:5432/mydb"
    (tmp_path / ".env").write_text(f"AUTOBOT_DATABASE_URL={db_dsn}\n", encoding="utf-8")
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    malicious_component = "../../etc/passwd"

    with (
        patch("api.code_sync._DB_BACKUP_DIR", str(backup_dir)),
        patch("asyncio.create_subprocess_exec") as mock_exec,
    ):
        steps: list[str] = []
        result = _run(_pg_dump_before_migration(malicious_component, str(tmp_path), steps))

    assert result is None
    mock_exec.assert_not_called()
    assert any("refusing" in s for s in steps), steps
