# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for drift/resolve deploy bugs fixed in #11322, #11323, and #11336.

#11322 — constraints dir not deployed before pip:
  _deploy_constraints_dir rsyncs constraints/ to /opt/autobot/constraints/ before pip
  runs, so the relative `-c ../constraints/shared.txt` in requirements.txt resolves.
  pip non-zero rc is surfaced as success=False in DriftResolveResponse.

#11323 — code-sync didn't enforce target Python version in venvs:
  _ensure_venv_python checks <venv>/bin/python --version and recreates the venv
  via `pythonX.Y -m venv` when there is a version mismatch.

#11336 — top-level requirements.txt not deployed before pip:
  _deploy_repo_root_requirements copies repo-root files (e.g. requirements.txt)
  to /opt/autobot/ before pip runs, so `-r ../requirements.txt` resolves.
"""

from __future__ import annotations

import os
import sys
import time
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# ---------------------------------------------------------------------------
# Dev-host stub: provide minimal real Pydantic models for models.schemas so
# the router can be imported without a full SLM venv.
# ---------------------------------------------------------------------------
if "models" not in sys.modules or isinstance(sys.modules.get("models"), MagicMock):
    from pydantic import BaseModel as _BM

    def _pydantic_stub(name: str, **fields) -> type:
        return type(name, (_BM,), {"__annotations__": {k: type(v) for k, v in fields.items()}, **fields})

    _schemas = types.ModuleType("models.schemas")
    for _cls in [
        "CodeSyncStatusResponse",
        "CodeSyncRefreshResponse",
        "CodeVersionNotification",
        "CodeVersionNotificationResponse",
        "ComponentSyncJobStatus",
        "DriftResolveJobResponse",
        "DriftResolveRequest",
        "DriftResolveResponse",
        "FileDriftReport",
        "FleetSyncJobStatus",
        "FleetSyncNodeStatus",
        "FleetSyncRequest",
        "FleetSyncResponse",
        "MarkSyncedResponse",
        "NodeSyncRequest",
        "NodeSyncResponse",
        "PendingNodeResponse",
        "PendingNodesResponse",
        "ScheduleCreate",
        "ScheduleResponse",
        "ScheduleRunResponse",
        "ScheduleUpdate",
    ]:
        setattr(_schemas, _cls, _pydantic_stub(_cls))
    _models = sys.modules.get("models") or types.ModuleType("models")
    _models.schemas = _schemas  # type: ignore[attr-defined]
    sys.modules["models"] = _models
    sys.modules["models.schemas"] = _schemas

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND_ROOT))

import asyncio  # noqa: E402

from api.code_sync import (  # noqa: E402
    _COMPONENT_PYTHON_TARGET,
    _CONSTRAINTS_SOURCE_SUBDIR,
    _DB_BACKUP_DIR,
    _DB_BACKUP_KEEP,
    _HEALTH_POLL_TIMEOUT,
    _NPM_LOCK_HASH_MARKER,
    _REPO_ROOT_REQUIREMENT_FILES,
    _build_npm_frontend_for_component,
    _deploy_constraints_dir,
    _deploy_repo_root_requirements,
    _ensure_dist_writable,
    _ensure_target_python_installed,
    _ensure_venv_python,
    _install_pip_deps_for_component,
    _lockfile_hash,
    _lockfile_unchanged,
    _npm_install_if_needed,
    _pg_dump_before_migration,
    _prune_old_backups,
    _rollback_component,
    _run_alembic_migrations,
    _run_post_sync_steps,
    _snapshot_component,
    _wait_component_healthy,
)


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# #11322 — constants are defined
# ---------------------------------------------------------------------------


def test_constraints_source_subdir_constant() -> None:
    """_CONSTRAINTS_SOURCE_SUBDIR must be 'constraints'."""
    assert _CONSTRAINTS_SOURCE_SUBDIR == "constraints"


def test_component_python_target_has_backends() -> None:
    """Both pip-backend components have a python target defined."""
    assert _COMPONENT_PYTHON_TARGET["autobot-backend"] == "python3.14"
    assert _COMPONENT_PYTHON_TARGET["autobot-slm-backend"] == "python3.14"
    assert _COMPONENT_PYTHON_TARGET["autobot-npu-worker"] == "python3.11"


# ---------------------------------------------------------------------------
# #11322 — _deploy_constraints_dir
# ---------------------------------------------------------------------------


def test_deploy_constraints_dir_skipped_when_source_missing(tmp_path) -> None:
    """Step says 'not found' when the source dir doesn't exist."""
    steps: list[str] = []
    _run(_deploy_constraints_dir(str(tmp_path / "no_such_root"), steps))
    assert any("not found" in s for s in steps)


def test_deploy_constraints_dir_calls_rsync(tmp_path) -> None:
    """rsync is called when the source dir exists."""
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

    with patch("asyncio.create_subprocess_exec", side_effect=_fake_exec):
        _run(_deploy_constraints_dir(str(src_root), steps))

    assert "rsync" in captured
    assert any("deployed ok" in s for s in steps)


def test_deploy_constraints_dir_records_rsync_failure(tmp_path) -> None:
    """Non-zero rsync rc is recorded in steps."""
    src_root = tmp_path / "code_source"
    (src_root / "constraints").mkdir(parents=True)

    steps: list[str] = []

    async def _fake_exec(*cmd, **kw):
        proc = MagicMock()
        proc.returncode = 23
        proc.communicate = AsyncMock(return_value=(b"error", b""))
        return proc

    with patch("asyncio.create_subprocess_exec", side_effect=_fake_exec):
        _run(_deploy_constraints_dir(str(src_root), steps))

    assert any("failed" in s for s in steps)


# ---------------------------------------------------------------------------
# #11322 — _install_pip_deps_for_component returns bool
# ---------------------------------------------------------------------------


def test_pip_returns_true_on_success(tmp_path) -> None:
    req = tmp_path / "requirements.txt"
    req.write_text("-r nothing\n", encoding="utf-8")
    pip_bin = str(tmp_path / "venv" / "bin" / "pip")

    with patch(
        "api.code_sync._COMPONENT_PIP_PATHS",
        {"test-comp": (str(req), pip_bin)},
    ):

        async def _fake_exec(*cmd, **kw):
            proc = MagicMock()
            proc.returncode = 0
            proc.communicate = AsyncMock(return_value=(b"", b""))
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=_fake_exec):
            result = _run(_install_pip_deps_for_component("test-comp", []))

    assert result is True


def test_pip_returns_false_on_failure(tmp_path) -> None:
    req = tmp_path / "requirements.txt"
    req.write_text("-r nothing\n", encoding="utf-8")
    pip_bin = str(tmp_path / "venv" / "bin" / "pip")

    with patch(
        "api.code_sync._COMPONENT_PIP_PATHS",
        {"test-comp": (str(req), pip_bin)},
    ):

        async def _fake_exec(*cmd, **kw):
            proc = MagicMock()
            proc.returncode = 1
            proc.communicate = AsyncMock(return_value=(b"Could not open constraint file", b""))
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=_fake_exec):
            steps: list[str] = []
            result = _run(_install_pip_deps_for_component("test-comp", steps))

    assert result is False
    assert any("failed" in s for s in steps)


# ---------------------------------------------------------------------------
# #11322 — _run_post_sync_steps surfaces pip failure via pip_ok=False
# ---------------------------------------------------------------------------


def test_run_post_sync_steps_pip_ok_false_on_pip_failure() -> None:
    """When pip returns False, _run_post_sync_steps returns pip_ok=False."""
    with (
        patch("api.code_sync._compute_deps_changed", AsyncMock(return_value=False)),
        patch("api.code_sync._deploy_constraints_dir", AsyncMock()),
        patch("api.code_sync._deploy_repo_root_requirements", AsyncMock()),
        patch("api.code_sync._ensure_venv_python", AsyncMock()),
        patch("api.code_sync._install_pip_deps_for_component", AsyncMock(return_value=False)),
        patch("api.code_sync._run_alembic_migrations", AsyncMock()),
        patch("api.code_sync._ensure_autobot_shared_symlink", AsyncMock()),
        patch("api.code_sync._restart_component_services", AsyncMock()),
    ):
        _, _, pip_ok = _run(
            _run_post_sync_steps("autobot-backend", "/src/autobot-backend", "/opt/autobot/autobot-backend")
        )
    assert pip_ok is False


def test_run_post_sync_steps_pip_ok_true_on_success() -> None:
    """When pip returns True, _run_post_sync_steps returns pip_ok=True."""
    with (
        patch("api.code_sync._compute_deps_changed", AsyncMock(return_value=False)),
        patch("api.code_sync._deploy_constraints_dir", AsyncMock()),
        patch("api.code_sync._deploy_repo_root_requirements", AsyncMock()),
        patch("api.code_sync._ensure_venv_python", AsyncMock()),
        patch("api.code_sync._install_pip_deps_for_component", AsyncMock(return_value=True)),
        patch("api.code_sync._run_alembic_migrations", AsyncMock()),
        patch("api.code_sync._ensure_autobot_shared_symlink", AsyncMock()),
        patch("api.code_sync._restart_component_services", AsyncMock()),
    ):
        _, _, pip_ok = _run(
            _run_post_sync_steps("autobot-backend", "/src/autobot-backend", "/opt/autobot/autobot-backend")
        )
    assert pip_ok is True


# ---------------------------------------------------------------------------
# #11323 — _ensure_venv_python: version match → no-op
# ---------------------------------------------------------------------------


def test_ensure_venv_python_noop_when_version_matches(tmp_path) -> None:
    """When the venv reports the expected version, no recreate happens."""
    pip_bin = tmp_path / "venv" / "bin" / "pip"
    pip_bin.parent.mkdir(parents=True)
    py_bin = pip_bin.parent / "python"
    py_bin.write_text("#!/bin/sh\necho Python 3.14.0\n", encoding="utf-8")
    py_bin.chmod(0o755)

    with patch(
        "api.code_sync._COMPONENT_PIP_PATHS",
        {"autobot-backend": (str(tmp_path / "requirements.txt"), str(pip_bin))},
    ):

        async def _fake_exec(*cmd, **kw):
            proc = MagicMock()
            proc.returncode = 0
            proc.communicate = AsyncMock(return_value=(b"Python 3.14.0", b""))
            return proc

        steps: list[str] = []
        recreated: list[bool] = []
        with (
            patch("asyncio.create_subprocess_exec", side_effect=_fake_exec),
            patch("api.code_sync._recreate_venv", AsyncMock(side_effect=lambda *a, **k: recreated.append(True))),
        ):
            _run(_ensure_venv_python("autobot-backend", steps))

    assert not recreated, "venv should not be recreated when version matches"
    assert any("ok" in s for s in steps)


def test_ensure_venv_python_recreates_on_version_mismatch(tmp_path) -> None:
    """When the venv reports the wrong version AND target is installed, _recreate_venv is called."""
    pip_bin = tmp_path / "venv" / "bin" / "pip"
    pip_bin.parent.mkdir(parents=True)
    py_bin = pip_bin.parent / "python"
    py_bin.touch()

    with patch(
        "api.code_sync._COMPONENT_PIP_PATHS",
        {"autobot-backend": (str(tmp_path / "requirements.txt"), str(pip_bin))},
    ):

        async def _fake_exec(*cmd, **kw):
            proc = MagicMock()
            proc.returncode = 0
            proc.communicate = AsyncMock(return_value=(b"Python 3.12.13", b""))
            return proc

        steps: list[str] = []
        recreated: list[bool] = []

        async def _fake_recreate(*args, **kw):
            recreated.append(True)

        with (
            patch("asyncio.create_subprocess_exec", side_effect=_fake_exec),
            patch("api.code_sync._recreate_venv", side_effect=_fake_recreate),
            # simulate host where python3.14 IS installed
            patch("shutil.which", return_value="/usr/bin/python3.14"),
        ):
            _run(_ensure_venv_python("autobot-backend", steps))

    assert recreated, "venv must be recreated on mismatch when target is installed"
    assert any("mismatch" in s for s in steps)


def test_ensure_venv_python_creates_when_missing(tmp_path) -> None:
    """When <venv>/bin/python is absent but target is installed, _recreate_venv is called."""
    pip_bin = tmp_path / "venv" / "bin" / "pip"
    # Do NOT create py_bin — simulates missing venv

    with patch(
        "api.code_sync._COMPONENT_PIP_PATHS",
        {"autobot-backend": (str(tmp_path / "requirements.txt"), str(pip_bin))},
    ):
        steps: list[str] = []
        recreated: list[bool] = []

        async def _fake_recreate(*args, **kw):
            recreated.append(True)

        with (
            patch("api.code_sync._recreate_venv", side_effect=_fake_recreate),
            # target interpreter is present on PATH
            patch("shutil.which", return_value="/usr/bin/python3.14"),
        ):
            _run(_ensure_venv_python("autobot-backend", steps))

    assert recreated, "venv must be created when python binary is missing and target is installed"


def test_ensure_venv_python_skipped_for_unknown_component() -> None:
    """Helper is a no-op for components not in _COMPONENT_PYTHON_TARGET."""
    steps: list[str] = []
    _run(_ensure_venv_python("autobot-frontend", steps))
    assert steps == []


# ---------------------------------------------------------------------------
# #11327 safety guard — target interpreter absent: never destroy existing venv
# ---------------------------------------------------------------------------


def test_ensure_venv_python_skips_recreation_when_target_not_installed_mismatch(tmp_path) -> None:
    """Venv with wrong Python version is NOT removed when target interpreter is absent.

    Scenario: venv reports Python 3.12 but target is python3.14 and python3.14 is
    not installed on this host.  The existing venv must survive intact so the
    service can keep running.  A skip step is recorded instead.
    """
    pip_bin = tmp_path / "venv" / "bin" / "pip"
    pip_bin.parent.mkdir(parents=True)
    py_bin = pip_bin.parent / "python"
    py_bin.touch()
    venv_dir = tmp_path / "venv"

    with patch(
        "api.code_sync._COMPONENT_PIP_PATHS",
        {"autobot-backend": (str(tmp_path / "requirements.txt"), str(pip_bin))},
    ):

        async def _fake_exec(*cmd, **kw):
            proc = MagicMock()
            proc.returncode = 0
            proc.communicate = AsyncMock(return_value=(b"Python 3.12.13", b""))
            return proc

        steps: list[str] = []
        with (
            patch("asyncio.create_subprocess_exec", side_effect=_fake_exec),
            # target interpreter is NOT on PATH
            patch("shutil.which", return_value=None),
        ):
            _run(_ensure_venv_python("autobot-backend", steps))

    # venv dir must still exist — rmtree must NOT have been called
    assert venv_dir.exists(), "existing venv must not be removed when target interpreter is absent"
    assert any("not installed" in s or "skipping" in s.lower() for s in steps), f"expected a skip step, got: {steps}"


def test_ensure_venv_python_skips_creation_when_target_not_installed_missing(tmp_path) -> None:
    """When <venv>/bin/python is absent AND the target interpreter is absent, skip gracefully.

    Neither rmtree nor _recreate_venv should be called — a skip step is recorded.
    """
    pip_bin = tmp_path / "venv" / "bin" / "pip"
    # Do NOT create py_bin — simulates missing venv

    with patch(
        "api.code_sync._COMPONENT_PIP_PATHS",
        {"autobot-backend": (str(tmp_path / "requirements.txt"), str(pip_bin))},
    ):
        steps: list[str] = []
        recreated: list[bool] = []

        async def _fake_recreate(*args, **kw):
            recreated.append(True)

        with (
            patch("api.code_sync._recreate_venv", side_effect=_fake_recreate),
            # target interpreter is NOT on PATH
            patch("shutil.which", return_value=None),
        ):
            _run(_ensure_venv_python("autobot-backend", steps))

    assert not recreated, "must not attempt to recreate venv when target interpreter is absent"
    assert any("not installed" in s or "skipping" in s.lower() for s in steps), f"expected a skip step, got: {steps}"


# ---------------------------------------------------------------------------
# #11336 — _deploy_repo_root_requirements
# ---------------------------------------------------------------------------


def test_repo_root_requirement_files_constant() -> None:
    """_REPO_ROOT_REQUIREMENT_FILES must include requirements.txt."""
    assert "requirements.txt" in _REPO_ROOT_REQUIREMENT_FILES


def test_deploy_repo_root_requirements_skipped_when_file_missing(tmp_path) -> None:
    """Step says 'not found' when the source file doesn't exist."""
    steps: list[str] = []
    with patch("api.code_sync._get_deploy_base", return_value=tmp_path):
        _run(_deploy_repo_root_requirements(str(tmp_path / "no_such_root"), steps))
    assert any("not found" in s for s in steps)


def test_deploy_repo_root_requirements_calls_cp(tmp_path) -> None:
    """cp is called when the source file exists."""
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
    ):
        _run(_deploy_repo_root_requirements(str(src_root), steps))

    assert "cp" in captured
    assert any("deployed ok" in s for s in steps)


def test_deploy_repo_root_requirements_records_cp_failure(tmp_path) -> None:
    """Non-zero cp rc is recorded in steps."""
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
    ):
        _run(_deploy_repo_root_requirements(str(src_root), steps))

    assert any("failed" in s for s in steps)


def test_run_post_sync_steps_calls_deploy_repo_root_requirements() -> None:
    """_deploy_repo_root_requirements is called for pip backend components."""
    called: list[bool] = []

    async def _fake_deploy(source_root: str, steps: list) -> None:
        called.append(True)

    with (
        patch("api.code_sync._compute_deps_changed", AsyncMock(return_value=False)),
        patch("api.code_sync._deploy_constraints_dir", AsyncMock()),
        patch("api.code_sync._deploy_repo_root_requirements", side_effect=_fake_deploy),
        patch("api.code_sync._ensure_venv_python", AsyncMock()),
        patch("api.code_sync._install_pip_deps_for_component", AsyncMock(return_value=True)),
        patch("api.code_sync._run_alembic_migrations", AsyncMock()),
        patch("api.code_sync._ensure_autobot_shared_symlink", AsyncMock()),
        patch("api.code_sync._restart_component_services", AsyncMock()),
    ):
        _run(_run_post_sync_steps("autobot-backend", "/src/autobot-backend", "/opt/autobot/autobot-backend"))

    assert called, "_deploy_repo_root_requirements must be called for pip backend components"


# ---------------------------------------------------------------------------
# #11343 — _ensure_target_python_installed: provision interpreter when missing
# ---------------------------------------------------------------------------


def test_ensure_target_python_skips_when_present() -> None:
    """When shutil.which finds the target, no ansible playbook is invoked."""
    steps: list[str] = []
    with (
        patch("shutil.which", return_value="/usr/bin/python3.14"),
        patch("api.code_sync._run_python_provision_playbook", AsyncMock()) as run_pb,
    ):
        _run(_ensure_target_python_installed("autobot-backend", steps))
    run_pb.assert_not_called()
    assert any("already present" in s for s in steps)


def test_ensure_target_python_invokes_ansible_when_missing() -> None:
    """When the target is absent, the python314 provisioning playbook is run."""
    steps: list[str] = []
    with (
        patch("shutil.which", return_value=None),
        patch("api.code_sync._PROVISION_PYTHON_PLAYBOOK") as pb,
        patch("api.code_sync._run_python_provision_playbook", AsyncMock(return_value=True)) as run_pb,
    ):
        pb.exists.return_value = True
        _run(_ensure_target_python_installed("autobot-backend", steps))
    run_pb.assert_awaited_once()


def test_ensure_target_python_skipped_for_unknown_component() -> None:
    """Non-Python components have no target and are a no-op."""
    steps: list[str] = []
    with patch("api.code_sync._run_python_provision_playbook", AsyncMock()) as run_pb:
        _run(_ensure_target_python_installed("autobot-frontend", steps))
    run_pb.assert_not_called()
    assert steps == []


def test_ensure_target_python_uses_arg_list_and_target_from_map(tmp_path) -> None:
    """The ansible invocation is an arg-list (no shell) using the mapped target."""
    steps: list[str] = []
    captured: list = []

    async def _fake_exec(*cmd, **kw):
        captured.extend(cmd)
        proc = MagicMock()
        proc.returncode = 0
        proc.communicate = AsyncMock(return_value=(b"ok", b""))
        return proc

    playbook = tmp_path / "provision-local-python.yml"
    playbook.write_text("---\n", encoding="utf-8")

    # shutil.which: None first (trigger provision), path after install re-check.
    with (
        patch("shutil.which", side_effect=[None, "/usr/bin/python3.14"]),
        patch("api.code_sync._PROVISION_PYTHON_PLAYBOOK", playbook),
        patch("asyncio.create_subprocess_exec", side_effect=_fake_exec),
    ):
        _run(_ensure_target_python_installed("autobot-backend", steps))

    assert captured[0] == "sudo"
    assert captured[1] == "ansible-playbook"
    assert "--tags" in captured and "python314" in captured
    assert "--connection" in captured and "local" in captured
    assert str(playbook) in captured
    # #11352: inline localhost inventory, NOT "--limit localhost" against the
    # fleet inventory (which targeted no hosts).
    assert "-i" in captured and "localhost," in captured
    assert "--limit" not in captured
    assert any("now on PATH" in s for s in steps)


def test_ensure_target_python_does_not_recreate_venv_on_provision_failure() -> None:
    """On ansible failure the venv is NOT removed/recreated (preserves #11323 guard)."""
    steps: list[str] = []
    with (
        patch("shutil.which", return_value=None),
        patch("api.code_sync._PROVISION_PYTHON_PLAYBOOK") as pb,
        patch("api.code_sync._run_python_provision_playbook", AsyncMock(return_value=False)),
        patch("api.code_sync._recreate_venv", AsyncMock()) as recreate,
        patch("shutil.rmtree") as rmtree,
    ):
        pb.exists.return_value = True
        _run(_ensure_target_python_installed("autobot-backend", steps))
    recreate.assert_not_called()
    rmtree.assert_not_called()


def test_run_post_sync_steps_provisions_python_before_venv() -> None:
    """_ensure_target_python_installed runs BEFORE _ensure_venv_python."""
    order: list[str] = []

    async def _provision(component, steps):
        order.append("provision")

    async def _venv(component, steps):
        order.append("venv")

    with (
        patch("api.code_sync._compute_deps_changed", AsyncMock(return_value=False)),
        patch("api.code_sync._deploy_constraints_dir", AsyncMock()),
        patch("api.code_sync._deploy_repo_root_requirements", AsyncMock()),
        patch("api.code_sync._ensure_target_python_installed", side_effect=_provision),
        patch("api.code_sync._ensure_venv_python", side_effect=_venv),
        patch("api.code_sync._install_pip_deps_for_component", AsyncMock(return_value=True)),
        patch("api.code_sync._run_alembic_migrations", AsyncMock()),
        patch("api.code_sync._ensure_autobot_shared_symlink", AsyncMock()),
        patch("api.code_sync._restart_component_services", AsyncMock()),
    ):
        _run(_run_post_sync_steps("autobot-backend", "/src/autobot-backend", "/opt/autobot/autobot-backend"))

    assert order == ["provision", "venv"], f"expected provision before venv, got {order}"


# ---------------------------------------------------------------------------
# #11351 — conditional npm ci: lockfile-hash skip logic
# ---------------------------------------------------------------------------


def test_lockfile_hash_returns_none_when_missing(tmp_path) -> None:
    """_lockfile_hash returns None when package-lock.json is absent."""
    assert _lockfile_hash(str(tmp_path)) is None


def test_lockfile_hash_returns_hex_digest(tmp_path) -> None:
    """_lockfile_hash returns a 64-char hex string for an existing lockfile."""
    (tmp_path / "package-lock.json").write_bytes(b'{"lockfileVersion":3}')
    result = _lockfile_hash(str(tmp_path))
    assert result is not None
    assert len(result) == 64
    assert all(c in "0123456789abcdef" for c in result)


def test_lockfile_unchanged_false_when_node_modules_missing(tmp_path) -> None:
    """Returns False when node_modules directory does not exist."""
    (tmp_path / "package-lock.json").write_bytes(b"{}")
    assert _lockfile_unchanged(str(tmp_path)) is False


def test_lockfile_unchanged_false_when_marker_absent(tmp_path) -> None:
    """Returns False when node_modules exists but the hash marker file is missing."""
    (tmp_path / "package-lock.json").write_bytes(b"{}")
    (tmp_path / "node_modules").mkdir()
    assert _lockfile_unchanged(str(tmp_path)) is False


def test_lockfile_unchanged_false_when_hash_differs(tmp_path) -> None:
    """Returns False when the stored hash doesn't match the current lockfile."""
    lock = tmp_path / "package-lock.json"
    lock.write_bytes(b'{"lockfileVersion":3}')
    nm = tmp_path / "node_modules"
    nm.mkdir()
    (nm / _NPM_LOCK_HASH_MARKER).write_text("deadbeef" * 8, encoding="utf-8")
    assert _lockfile_unchanged(str(tmp_path)) is False


def test_lockfile_unchanged_true_when_hash_matches(tmp_path) -> None:
    """Returns True when node_modules exists and the stored hash matches the lockfile."""
    import hashlib

    content = b'{"lockfileVersion":3}'
    lock = tmp_path / "package-lock.json"
    lock.write_bytes(content)
    nm = tmp_path / "node_modules"
    nm.mkdir()
    (nm / _NPM_LOCK_HASH_MARKER).write_text(hashlib.sha256(content).hexdigest(), encoding="utf-8")
    assert _lockfile_unchanged(str(tmp_path)) is True


# ---------------------------------------------------------------------------
# #11351 — _npm_install_if_needed: skip, run, failure
# ---------------------------------------------------------------------------


def test_npm_install_skipped_when_lockfile_unchanged(tmp_path) -> None:
    """npm ci is NOT invoked when _lockfile_unchanged returns True."""
    import hashlib

    content = b'{"lockfileVersion":3}'
    (tmp_path / "package-lock.json").write_bytes(content)
    nm = tmp_path / "node_modules"
    nm.mkdir()
    (nm / _NPM_LOCK_HASH_MARKER).write_text(hashlib.sha256(content).hexdigest(), encoding="utf-8")

    steps: list[str] = []
    executed: list[str] = []

    async def _fake_exec(*cmd, **kw):
        executed.extend(cmd)
        proc = MagicMock()
        proc.returncode = 0
        proc.communicate = AsyncMock(return_value=(b"", b""))
        return proc

    with patch("asyncio.create_subprocess_exec", side_effect=_fake_exec):
        result = _run(_npm_install_if_needed(str(tmp_path), "autobot-slm-frontend", steps))

    assert result is True
    assert not executed, "npm ci must not run when lockfile is unchanged"
    assert any("skipped" in s for s in steps)


def test_npm_install_runs_when_node_modules_missing(tmp_path) -> None:
    """npm ci IS invoked when node_modules doesn't exist."""
    (tmp_path / "package-lock.json").write_bytes(b'{"lockfileVersion":3}')
    # node_modules intentionally absent

    steps: list[str] = []
    executed: list[str] = []

    async def _fake_exec(*cmd, **kw):
        executed.extend(cmd)
        proc = MagicMock()
        proc.returncode = 0
        proc.communicate = AsyncMock(return_value=(b"", b""))
        return proc

    with patch("asyncio.create_subprocess_exec", side_effect=_fake_exec):
        result = _run(_npm_install_if_needed(str(tmp_path), "autobot-slm-frontend", steps))

    assert result is True
    assert "npm" in executed and "ci" in executed
    assert any("succeeded" in s for s in steps)


def test_npm_install_runs_when_lockfile_changed(tmp_path) -> None:
    """npm ci IS invoked when the stored hash doesn't match the current lockfile."""
    (tmp_path / "package-lock.json").write_bytes(b'{"lockfileVersion":3,"new-dep":true}')
    nm = tmp_path / "node_modules"
    nm.mkdir()
    (nm / _NPM_LOCK_HASH_MARKER).write_text("stale_hash" * 6, encoding="utf-8")

    steps: list[str] = []
    executed: list[str] = []

    async def _fake_exec(*cmd, **kw):
        executed.extend(cmd)
        proc = MagicMock()
        proc.returncode = 0
        proc.communicate = AsyncMock(return_value=(b"", b""))
        return proc

    with patch("asyncio.create_subprocess_exec", side_effect=_fake_exec):
        result = _run(_npm_install_if_needed(str(tmp_path), "autobot-slm-frontend", steps))

    assert result is True
    assert "npm" in executed and "ci" in executed


def test_npm_install_writes_marker_on_success(tmp_path) -> None:
    """After a successful npm ci the hash marker is written to node_modules/."""
    import hashlib

    content = b'{"lockfileVersion":3}'
    (tmp_path / "package-lock.json").write_bytes(content)
    # node_modules absent — will be created by the real npm, but we just need
    # the marker write to happen; fake the dir creation here.
    nm = tmp_path / "node_modules"
    nm.mkdir()

    async def _fake_exec(*cmd, **kw):
        proc = MagicMock()
        proc.returncode = 0
        proc.communicate = AsyncMock(return_value=(b"", b""))
        return proc

    with patch("asyncio.create_subprocess_exec", side_effect=_fake_exec):
        _run(_npm_install_if_needed(str(tmp_path), "autobot-slm-frontend", []))

    marker = nm / _NPM_LOCK_HASH_MARKER
    assert marker.exists()
    assert marker.read_text(encoding="utf-8") == hashlib.sha256(content).hexdigest()


def test_npm_install_returns_false_on_nonzero_rc(tmp_path) -> None:
    """_npm_install_if_needed returns False when npm ci exits non-zero."""
    (tmp_path / "package-lock.json").write_bytes(b"{}")

    steps: list[str] = []

    async def _fake_exec(*cmd, **kw):
        proc = MagicMock()
        proc.returncode = 1
        proc.communicate = AsyncMock(return_value=(b"ERESOLVE", b""))
        return proc

    with patch("asyncio.create_subprocess_exec", side_effect=_fake_exec):
        result = _run(_npm_install_if_needed(str(tmp_path), "autobot-slm-frontend", steps))

    assert result is False
    assert any("failed" in s for s in steps)


# ---------------------------------------------------------------------------
# #11351 — _build_npm_frontend_for_component: skip install → build still runs
# ---------------------------------------------------------------------------


def test_build_skips_install_and_runs_build(tmp_path) -> None:
    """When lockfile is unchanged, npm ci is skipped but npm run build still runs."""
    import hashlib

    content = b'{"lockfileVersion":3}'
    (tmp_path / "package-lock.json").write_bytes(content)
    nm = tmp_path / "node_modules"
    nm.mkdir()
    (nm / _NPM_LOCK_HASH_MARKER).write_text(hashlib.sha256(content).hexdigest(), encoding="utf-8")

    steps: list[str] = []
    build_called: list[bool] = []

    async def _fake_exec(*cmd, **kw):
        if "run" in cmd:
            build_called.append(True)
        proc = MagicMock()
        proc.returncode = 0
        proc.communicate = AsyncMock(return_value=(b"", b""))
        return proc

    with (
        patch("api.code_sync._COMPONENT_FRONTEND_DIRS", {"autobot-slm-frontend": str(tmp_path)}),
        patch("asyncio.create_subprocess_exec", side_effect=_fake_exec),
    ):
        result = _run(_build_npm_frontend_for_component("autobot-slm-frontend", steps))

    assert result is True
    assert build_called, "npm run build must still execute even when npm ci is skipped"
    assert any("skipped" in s for s in steps)
    assert any("succeeded" in s for s in steps)


def test_build_returns_false_on_npm_ci_failure(tmp_path) -> None:
    """When npm ci fails, the build is aborted and False is returned."""
    (tmp_path / "package-lock.json").write_bytes(b"{}")

    steps: list[str] = []

    async def _fake_exec(*cmd, **kw):
        proc = MagicMock()
        proc.returncode = 1
        proc.communicate = AsyncMock(return_value=(b"err", b""))
        return proc

    with (
        patch("api.code_sync._COMPONENT_FRONTEND_DIRS", {"autobot-slm-frontend": str(tmp_path)}),
        patch("asyncio.create_subprocess_exec", side_effect=_fake_exec),
    ):
        result = _run(_build_npm_frontend_for_component("autobot-slm-frontend", steps))

    assert result is False
    assert any("failed" in s for s in steps)


# ---------------------------------------------------------------------------
# #11351 — _run_post_sync_steps surfaces npm build failure via pip_ok=False
# ---------------------------------------------------------------------------


def test_run_post_sync_steps_pip_ok_false_on_npm_failure() -> None:
    """When npm build returns False, _run_post_sync_steps returns pip_ok=False."""
    with (
        patch("api.code_sync._compute_deps_changed", AsyncMock(return_value=False)),
        patch("api.code_sync._build_npm_frontend_for_component", AsyncMock(return_value=False)),
        patch("api.code_sync._restart_component_services", AsyncMock()),
    ):
        _, _, pip_ok = _run(
            _run_post_sync_steps(
                "autobot-slm-frontend",
                "/src/autobot-slm-frontend",
                "/opt/autobot/autobot-slm-frontend",
            )
        )
    assert pip_ok is False


def test_run_post_sync_steps_pip_ok_true_on_npm_success() -> None:
    """When npm build returns True, _run_post_sync_steps returns pip_ok=True."""
    with (
        patch("api.code_sync._compute_deps_changed", AsyncMock(return_value=False)),
        patch("api.code_sync._build_npm_frontend_for_component", AsyncMock(return_value=True)),
        patch("api.code_sync._restart_component_services", AsyncMock()),
    ):
        _, _, pip_ok = _run(
            _run_post_sync_steps(
                "autobot-slm-frontend",
                "/src/autobot-slm-frontend",
                "/opt/autobot/autobot-slm-frontend",
            )
        )
    assert pip_ok is True


# ---------------------------------------------------------------------------
# #11364 — _ensure_dist_writable: chown before npm build
# ---------------------------------------------------------------------------


def test_ensure_dist_writable_skipped_when_dist_absent(tmp_path) -> None:
    """No chown is run when dist/ does not exist."""
    steps: list[str] = []
    executed: list = []

    async def _fake_exec(*cmd, **kw):
        executed.extend(cmd)
        proc = MagicMock()
        proc.returncode = 0
        proc.communicate = AsyncMock(return_value=(b"", b""))
        return proc

    with patch("asyncio.create_subprocess_exec", side_effect=_fake_exec):
        _run(_ensure_dist_writable(str(tmp_path), steps))

    assert not executed, "sudo chown must not run when dist/ is absent"
    assert any("skipped" in s for s in steps)


def test_ensure_dist_writable_chowns_when_dist_exists(tmp_path) -> None:
    """sudo chown -R <user>:<user> dist/ is invoked when dist/ exists."""
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.js").write_bytes(b"")

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
        patch("getpass.getuser", return_value="autobot"),
    ):
        _run(_ensure_dist_writable(str(tmp_path), steps))

    assert captured[:3] == ["sudo", "chown", "-R"], f"unexpected cmd prefix: {captured[:3]}"
    assert "autobot:autobot" in captured
    assert str(dist) in captured
    assert any("normalized ownership" in s for s in steps)


def test_ensure_dist_writable_uses_getpass_not_hardcoded(tmp_path) -> None:
    """Service user comes from getpass.getuser(), not a hardcoded string."""
    dist = tmp_path / "dist"
    dist.mkdir()

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
        patch("getpass.getuser", return_value="customsvcuser"),
    ):
        _run(_ensure_dist_writable(str(tmp_path), steps))

    owner_arg = next((a for a in captured if "customsvcuser" in a), None)
    assert owner_arg == "customsvcuser:customsvcuser", f"expected owner arg, got captured={captured}"


def test_ensure_dist_writable_non_fatal_on_chown_failure(tmp_path) -> None:
    """A non-zero chown rc appends a failure step but does NOT raise."""
    dist = tmp_path / "dist"
    dist.mkdir()

    steps: list[str] = []

    async def _fake_exec(*cmd, **kw):
        proc = MagicMock()
        proc.returncode = 1
        proc.communicate = AsyncMock(return_value=(b"permission denied", b""))
        return proc

    with (
        patch("asyncio.create_subprocess_exec", side_effect=_fake_exec),
        patch("getpass.getuser", return_value="autobot"),
    ):
        _run(_ensure_dist_writable(str(tmp_path), steps))  # must not raise

    assert any("attempting build anyway" in s for s in steps)


def test_build_npm_calls_ensure_dist_writable_before_install(tmp_path) -> None:
    """_ensure_dist_writable is called before _npm_install_if_needed in the build path."""
    import hashlib

    content = b'{"lockfileVersion":3}'
    (tmp_path / "package-lock.json").write_bytes(content)
    nm = tmp_path / "node_modules"
    nm.mkdir()
    (nm / _NPM_LOCK_HASH_MARKER).write_text(hashlib.sha256(content).hexdigest(), encoding="utf-8")

    order: list[str] = []

    async def _fake_writable(fd, steps):
        order.append("ensure_dist_writable")

    async def _fake_install(fd, comp, steps):
        order.append("npm_install")
        return True

    async def _fake_exec(*cmd, **kw):
        proc = MagicMock()
        proc.returncode = 0
        proc.communicate = AsyncMock(return_value=(b"", b""))
        return proc

    with (
        patch("api.code_sync._COMPONENT_FRONTEND_DIRS", {"autobot-slm-frontend": str(tmp_path)}),
        patch("api.code_sync._ensure_dist_writable", side_effect=_fake_writable),
        patch("api.code_sync._npm_install_if_needed", side_effect=_fake_install),
        patch("asyncio.create_subprocess_exec", side_effect=_fake_exec),
    ):
        result = _run(_build_npm_frontend_for_component("autobot-slm-frontend", []))

    assert result is True
    assert order[0] == "ensure_dist_writable", f"expected ensure_dist_writable first, got {order}"


# ---------------------------------------------------------------------------
# #11376 — pg_dump before migrations
# ---------------------------------------------------------------------------


def test_pg_dump_constants_defined() -> None:
    """Module constants for backup dir and keep count must exist."""
    assert _DB_BACKUP_DIR  # non-empty string
    assert _DB_BACKUP_KEEP >= 1


def test_pg_dump_invoked_before_alembic(tmp_path) -> None:
    """_pg_dump_before_migration must be called before alembic upgrade (#11376)."""
    call_order: list[str] = []

    async def _fake_dump(component, deployed_dir, steps):
        call_order.append("dump")
        steps.append("pg_dump: backup ok → /tmp/test.dump")
        return "/tmp/test.dump"

    async def _fake_exec(*cmd, **kw):
        call_order.append("alembic")
        proc = MagicMock()
        proc.returncode = 0
        proc.communicate = AsyncMock(return_value=(b"", b""))
        return proc

    deployed = tmp_path / "autobot-backend"
    deployed.mkdir()
    (deployed / ".env").write_text("DATABASE_URL=postgresql://u:p@localhost/db\n", encoding="utf-8")
    alembic_ini = deployed / "migrations" / "alembic.ini"
    alembic_ini.parent.mkdir(parents=True)
    alembic_ini.write_text("[alembic]\n", encoding="utf-8")
    # Create a fake alembic binary so the path-existence check passes
    alembic_bin = deployed / "venv" / "bin" / "alembic"
    alembic_bin.parent.mkdir(parents=True)
    alembic_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    alembic_bin.chmod(0o755)

    with (
        patch(
            "api.code_sync._COMPONENT_MIGRATION_CONFIG",
            {"autobot-backend": "migrations/alembic.ini"},
        ),
        patch("api.code_sync._COMPONENT_PIP_PATHS", {"autobot-backend": ("req.txt", str(deployed / "venv/bin/pip"))}),
        patch("api.code_sync._pg_dump_before_migration", side_effect=_fake_dump),
        patch("asyncio.create_subprocess_exec", side_effect=_fake_exec),
    ):
        _run(_run_alembic_migrations("autobot-backend", str(deployed), []))

    assert call_order[0] == "dump", f"pg_dump must run before alembic; got order={call_order}"
    assert "alembic" in call_order


def test_alembic_aborted_when_dump_fails(tmp_path) -> None:
    """Migration must not run if pg_dump returns None (#11376)."""
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


def test_pg_dump_abort_propagates_to_post_sync() -> None:
    """_run_post_sync_steps returns pip_ok=False when pg_dump fails (#11376)."""
    with (
        patch("api.code_sync._compute_deps_changed", AsyncMock(return_value=False)),
        patch("api.code_sync._snapshot_component", AsyncMock(return_value=None)),
        patch("api.code_sync._deploy_constraints_dir", AsyncMock()),
        patch("api.code_sync._deploy_repo_root_requirements", AsyncMock()),
        patch("api.code_sync._ensure_target_python_installed", AsyncMock()),
        patch("api.code_sync._ensure_venv_python", AsyncMock()),
        patch("api.code_sync._install_pip_deps_for_component", AsyncMock(return_value=True)),
        patch("api.code_sync._run_alembic_migrations", AsyncMock(return_value=False)),
        patch("api.code_sync._rollback_component", AsyncMock()),
        patch("api.code_sync._ensure_autobot_shared_symlink", AsyncMock()),
        patch("api.code_sync._restart_component_services", AsyncMock()),
    ):
        _, _, pip_ok = _run(
            _run_post_sync_steps("autobot-backend", "/src/autobot-backend", "/opt/autobot/autobot-backend")
        )
    assert pip_ok is False


def test_prune_old_backups_removes_oldest(tmp_path) -> None:
    """_prune_old_backups keeps only max_keep newest dumps (#11376)."""
    for i in range(4):
        p = tmp_path / f"autobot-backend_{i:04d}.dump"
        p.write_bytes(b"x")
        # stagger mtime so glob sort is deterministic
        os.utime(str(p), (time.time() + i, time.time() + i))

    _prune_old_backups(tmp_path, "autobot-backend", max_keep=2)

    remaining = sorted(tmp_path.glob("autobot-backend_*.dump"))
    assert len(remaining) == 2
    # Newest two should survive
    assert remaining[0].name == "autobot-backend_0002.dump"
    assert remaining[1].name == "autobot-backend_0003.dump"


def test_pg_dump_skips_when_no_database_url(tmp_path) -> None:
    """_pg_dump_before_migration returns None when DATABASE_URL is absent."""
    (tmp_path / ".env").write_text("FOO=bar\n", encoding="utf-8")
    steps: list[str] = []

    with patch.dict("os.environ", {}, clear=False):
        # Remove DATABASE_URL if present in env
        env_backup = os.environ.pop("DATABASE_URL", None)
        try:
            result = _run(_pg_dump_before_migration("autobot-backend", str(tmp_path), steps))
        finally:
            if env_backup is not None:
                os.environ["DATABASE_URL"] = env_backup

    assert result is None
    assert any("DATABASE_URL" in s for s in steps)


def test_pg_dump_uses_arg_list_subprocess(tmp_path) -> None:
    """pg_dump invocation must use an arg list, never a shell string (#11376)."""
    (tmp_path / ".env").write_text("DATABASE_URL=postgresql://user:pw@localhost:5432/mydb\n", encoding="utf-8")
    captured: list = []

    async def _fake_exec(*cmd, env=None, **kw):
        captured.extend(cmd)
        proc = MagicMock()
        proc.returncode = 0
        proc.communicate = AsyncMock(return_value=(b"", b""))
        return proc

    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    steps: list[str] = []

    with (
        patch("api.code_sync._DB_BACKUP_DIR", str(backup_dir)),
        patch("asyncio.create_subprocess_exec", side_effect=_fake_exec),
    ):
        _run(_pg_dump_before_migration("autobot-backend", str(tmp_path), steps))

    assert captured[0] == "pg_dump", f"first arg must be 'pg_dump', got {captured[0]}"
    assert "--format=custom" in captured
    assert "-h" in captured and "localhost" in captured
    assert "-U" in captured and "user" in captured
    # Each argument must be a plain string, not a shell-interpolated blob
    assert all(isinstance(a, str) for a in captured)


# ---------------------------------------------------------------------------
# #11377 — snapshot + rollback on post-sync failure
# ---------------------------------------------------------------------------


def test_snapshot_component_returns_none_when_not_git(tmp_path) -> None:
    """Returns None gracefully when git rev-parse fails (not a git repo)."""

    async def _fake_exec(*cmd, **kw):
        proc = MagicMock()
        proc.returncode = 128
        proc.communicate = AsyncMock(return_value=(b"not a git repository", b""))
        return proc

    with (
        patch("api.code_sync.get_default_deployed_dir", return_value=str(tmp_path)),
        patch("asyncio.create_subprocess_exec", side_effect=_fake_exec),
    ):
        result = _run(_snapshot_component("autobot-backend"))
    assert result is None


def test_snapshot_component_returns_sha(tmp_path) -> None:
    """Returns the SHA string when git rev-parse succeeds."""

    async def _fake_exec(*cmd, **kw):
        proc = MagicMock()
        proc.returncode = 0
        proc.communicate = AsyncMock(return_value=(b"abc123def456\n", b""))
        return proc

    with (
        patch("api.code_sync.get_default_deployed_dir", return_value=str(tmp_path)),
        patch("asyncio.create_subprocess_exec", side_effect=_fake_exec),
    ):
        result = _run(_snapshot_component("autobot-backend"))
    assert result == "abc123def456"


def test_rollback_component_calls_git_reset_and_restart(tmp_path) -> None:
    """_rollback_component runs git reset --hard and restarts services (#11377)."""
    restarted: list[bool] = []

    async def _fake_exec(*cmd, **kw):
        proc = MagicMock()
        proc.returncode = 0
        proc.communicate = AsyncMock(return_value=(b"HEAD is now at abc123", b""))
        return proc

    async def _fake_restart(component, steps):
        restarted.append(True)

    with (
        patch("api.code_sync.get_default_deployed_dir", return_value=str(tmp_path)),
        patch("asyncio.create_subprocess_exec", side_effect=_fake_exec),
        patch("api.code_sync._restart_component_services", side_effect=_fake_restart),
    ):
        steps: list[str] = []
        _run(_rollback_component("autobot-backend", "abc123def456", steps, "/tmp/dump.dump"))

    assert restarted, "services must be restarted after rollback"
    assert any("reverted" in s for s in steps)
    assert any("/tmp/dump.dump" in s for s in steps), "dump path must appear in steps"


def test_rollback_noop_when_no_snapshot() -> None:
    """_rollback_component is a no-op (warning) when snapshot is None (#11377)."""
    steps: list[str] = []
    with patch("api.code_sync._restart_component_services", AsyncMock()) as restart:
        _run(_rollback_component("autobot-backend", None, steps))
    restart.assert_not_called()
    assert any("no snapshot" in s for s in steps)


def test_run_post_sync_steps_rolls_back_on_pip_failure() -> None:
    """When pip fails, rollback is triggered (#11377)."""
    rolled_back: list[bool] = []

    async def _fake_rollback(component, snapshot, steps, dump_path=None):
        rolled_back.append(True)

    with (
        patch("api.code_sync._compute_deps_changed", AsyncMock(return_value=False)),
        patch("api.code_sync._snapshot_component", AsyncMock(return_value="aabbcc")),
        patch("api.code_sync._deploy_constraints_dir", AsyncMock()),
        patch("api.code_sync._deploy_repo_root_requirements", AsyncMock()),
        patch("api.code_sync._ensure_target_python_installed", AsyncMock()),
        patch("api.code_sync._ensure_venv_python", AsyncMock()),
        patch("api.code_sync._install_pip_deps_for_component", AsyncMock(return_value=False)),
        patch("api.code_sync._rollback_component", side_effect=_fake_rollback),
    ):
        _, _, pip_ok = _run(
            _run_post_sync_steps("autobot-backend", "/src/autobot-backend", "/opt/autobot/autobot-backend")
        )

    assert not pip_ok
    assert rolled_back, "rollback must be triggered on pip failure"


# ---------------------------------------------------------------------------
# #11378 — health polling after restart
# ---------------------------------------------------------------------------


def test_health_poll_timeout_constant_positive() -> None:
    """_HEALTH_POLL_TIMEOUT must be a positive number."""
    assert _HEALTH_POLL_TIMEOUT > 0


def test_wait_component_healthy_returns_true_on_healthy_response() -> None:
    """Returns True when the health endpoint responds 2xx (#11378)."""
    steps: list[str] = []

    class _FakeResp:
        status_code = 200

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        async def get(self, url):
            return _FakeResp()

    with (
        patch("api.code_sync._COMPONENT_HEALTH_URLS", {"autobot-backend": "http://127.0.0.1:8001/api/health"}),
        patch("api.code_sync._HEALTH_POLL_TIMEOUT", 5.0),
        patch("httpx.AsyncClient", return_value=_FakeClient()),
    ):
        result = _run(_wait_component_healthy("autobot-backend", steps))

    assert result is True
    assert any("healthy" in s for s in steps)


def test_wait_component_healthy_returns_false_on_timeout() -> None:
    """Returns False when the component stays unhealthy for the full timeout (#11378)."""
    steps: list[str] = []

    class _FailClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        async def get(self, url):
            raise ConnectionRefusedError("refused")

    with (
        patch("api.code_sync._COMPONENT_HEALTH_URLS", {"autobot-backend": "http://127.0.0.1:8001/api/health"}),
        patch("api.code_sync._HEALTH_POLL_TIMEOUT", 0.1),
        patch("api.code_sync._HEALTH_POLL_CONNECT_TIMEOUT", 0.05),
        patch("asyncio.sleep", AsyncMock()),
        patch("httpx.AsyncClient", return_value=_FailClient()),
    ):
        result = _run(_wait_component_healthy("autobot-backend", steps))

    assert result is False
    assert any("NOT healthy" in s for s in steps)


def test_wait_component_healthy_skips_when_no_url() -> None:
    """Components with no health URL are considered healthy immediately (#11378)."""
    steps: list[str] = []
    with patch("api.code_sync._COMPONENT_HEALTH_URLS", {}):
        result = _run(_wait_component_healthy("autobot-slm-backend", steps))

    assert result is True
    assert any("skipped" in s for s in steps)


def test_run_post_sync_steps_rolls_back_on_unhealthy(tmp_path) -> None:
    """When health poll fails after restart, rollback is triggered (#11378)."""
    rolled_back: list[bool] = []

    async def _fake_rollback(component, snapshot, steps, dump_path=None):
        rolled_back.append(True)

    with (
        patch("api.code_sync._compute_deps_changed", AsyncMock(return_value=False)),
        patch("api.code_sync._snapshot_component", AsyncMock(return_value="aabbcc")),
        patch("api.code_sync._deploy_constraints_dir", AsyncMock()),
        patch("api.code_sync._deploy_repo_root_requirements", AsyncMock()),
        patch("api.code_sync._ensure_target_python_installed", AsyncMock()),
        patch("api.code_sync._ensure_venv_python", AsyncMock()),
        patch("api.code_sync._install_pip_deps_for_component", AsyncMock(return_value=True)),
        patch("api.code_sync._run_alembic_migrations", AsyncMock(return_value=True)),
        patch("api.code_sync._ensure_autobot_shared_symlink", AsyncMock()),
        patch("api.code_sync._restart_component_services", AsyncMock()),
        patch("api.code_sync._wait_component_healthy", AsyncMock(return_value=False)),
        patch("api.code_sync._rollback_component", side_effect=_fake_rollback),
    ):
        _, _, pip_ok = _run(
            _run_post_sync_steps("autobot-backend", "/src/autobot-backend", "/opt/autobot/autobot-backend")
        )

    assert not pip_ok
    assert rolled_back, "rollback must be triggered when health poll fails after restart"


# ---------------------------------------------------------------------------
# #11403 — python provision runs with ansible.cfg discoverable (cwd + ANSIBLE_CONFIG)
# ---------------------------------------------------------------------------


def test_provision_playbook_runs_from_ansible_dir_with_config() -> None:
    """#11403: ansible-playbook must run with the ansible dir as cwd (survives
    sudo env_reset) and ANSIBLE_CONFIG set, so roles_path resolves the python314
    role instead of defaulting to playbooks/roles/ (role-not-found)."""
    from api.code_sync import (
        _ANSIBLE_CONFIG,
        _ANSIBLE_DIR,
        _PROVISION_PYTHON_PLAYBOOK,
        _run_python_provision_playbook,
    )

    captured: dict = {}

    async def _fake_exec(*cmd, **kw):
        captured["cmd"] = cmd
        captured["kw"] = kw
        proc = MagicMock()
        proc.returncode = 0
        proc.communicate = AsyncMock(return_value=(b"PLAY RECAP ok=11 changed=1 failed=0", b""))
        return proc

    steps: list = []
    with patch("asyncio.create_subprocess_exec", side_effect=_fake_exec):
        ok = _run(_run_python_provision_playbook("python3.14", steps))

    assert ok is True
    kw = captured["kw"]
    # cwd is the load-bearing fix (sudo preserves cwd; command args can't change)
    assert kw.get("cwd") == str(_ANSIBLE_DIR)
    env = kw.get("env") or {}
    assert env.get("ANSIBLE_CONFIG") == str(_ANSIBLE_CONFIG)
    # env must be merged from os.environ, else sudo/ansible-playbook aren't on PATH
    assert "PATH" in env
    # command args unchanged — must still match the exact NOPASSWD sudoers grant
    assert captured["cmd"][:3] == ("sudo", "ansible-playbook", str(_PROVISION_PYTHON_PLAYBOOK))
