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

import sys
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
    _NPM_LOCK_HASH_MARKER,
    _REPO_ROOT_REQUIREMENT_FILES,
    _build_npm_frontend_for_component,
    _deploy_constraints_dir,
    _deploy_repo_root_requirements,
    _ensure_target_python_installed,
    _ensure_venv_python,
    _install_pip_deps_for_component,
    _lockfile_hash,
    _lockfile_unchanged,
    _npm_install_if_needed,
    _run_post_sync_steps,
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
