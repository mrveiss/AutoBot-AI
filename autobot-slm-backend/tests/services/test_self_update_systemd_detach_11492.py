# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Self-update ansible run must survive the Play-1 backend restart (#11492).

`code-sync self-update` runs update-all-nodes.yml as a subprocess of
autobot-slm-backend. The service is KillMode=control-group, so when Play 1's
"Restart backend service" task fires `systemctl restart autobot-slm-backend`,
systemd SIGTERMs the whole cgroup — including the ansible-playbook child —
before Play 1's tail and all of Play 2/3 ever run.

The fix has two parts:
  1. Detach that one run into its own transient systemd scope
     (`systemd-run --scope --collect`, a separate cgroup) so it survives the
     restart, gated to the self-update path only and falling back to the
     direct exec when systemd-run / a systemd-service context is unavailable
     (dev mode, tests, containers).
  2. File-back the detached run's stdout/stderr (never the backend's pipe):
     once the backend dies, the pipe's read end closes, and a further write
     from the still-running ansible-playbook would raise BrokenPipeError —
     killing Play 2/3 exactly like the cgroup-kill this fix exists to
     prevent. This backend tails the same log file for live progress while
     it is still alive.

Loaded via importlib to dodge the conftest's session-global stubs (#11248),
same pattern as test_dynamic_inventory_group_vars_11781.py.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[2]

_STUBS = [
    "services",
    "services.ansible_secrets",
    "services.inventory_builder",
    "services.provision_progress",
]


def _load_executor():
    saved = {n: sys.modules.get(n) for n in _STUBS}
    try:
        for n in _STUBS:
            sys.modules[n] = MagicMock()
        spec = importlib.util.spec_from_file_location("_pe_11492", _BACKEND_ROOT / "services" / "playbook_executor.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        for n, orig in saved.items():
            if orig is None:
                sys.modules.pop(n, None)
            else:
                sys.modules[n] = orig


_pe = _load_executor()


def _executor(ansible_dir: Path) -> "_pe.PlaybookExecutor":
    ex = _pe.PlaybookExecutor.__new__(_pe.PlaybookExecutor)  # skip __init__ (env probing)
    ex.ansible_dir = ansible_dir
    return ex


class _FakeProcess:
    """Minimal stand-in for asyncio.subprocess.Process. Already-exited by
    default (returncode set at construction) so log-tailing loops in tests
    stop as soon as the file has no more pending lines, instead of polling
    forever."""

    def __init__(self, returncode: int = 0):
        self.stdout = None  # skip _stream_playbook_output's readline loop
        self.returncode = returncode

    async def wait(self):
        return self.returncode


# ---------------------------------------------------------------------------
# Detection: systemd-run availability + systemd-service context (#11492)
# ---------------------------------------------------------------------------


def test_detach_available_when_systemd_run_present_and_invocation_id_set():
    with patch.object(_pe.shutil, "which", return_value="/usr/bin/systemd-run"):
        with patch.dict(os.environ, {"INVOCATION_ID": "abc123"}):
            assert _pe.PlaybookExecutor._self_update_detach_available() is True


def test_detach_unavailable_without_systemd_run_binary():
    with patch.object(_pe.shutil, "which", return_value=None):
        with patch.dict(os.environ, {"INVOCATION_ID": "abc123"}):
            assert _pe.PlaybookExecutor._self_update_detach_available() is False


def test_detach_unavailable_without_invocation_id():
    """No INVOCATION_ID => not running as a systemd service (dev uvicorn, tests, containers)."""
    with patch.object(_pe.shutil, "which", return_value="/usr/bin/systemd-run"):
        env = dict(os.environ)
        env.pop("INVOCATION_ID", None)
        with patch.dict(os.environ, env, clear=True):
            assert _pe.PlaybookExecutor._self_update_detach_available() is False


# ---------------------------------------------------------------------------
# Log file preparation (truncate-per-run, best-effort)
# ---------------------------------------------------------------------------


def test_prepare_self_update_log_file_creates_and_truncates(tmp_path):
    log_path = tmp_path / "sub" / "self-update-ansible.log"
    with patch.object(_pe, "SELF_UPDATE_LOG_PATH", log_path):
        # Stale content from a prior run must not leak into this run's tail.
        log_path.parent.mkdir(parents=True)
        log_path.write_text("stale prior run content\n", encoding="utf-8")

        result = _pe.PlaybookExecutor._prepare_self_update_log_file()

    assert result == log_path
    assert log_path.read_text(encoding="utf-8") == ""


def test_prepare_self_update_log_file_returns_none_on_failure(tmp_path):
    # Parent path is a FILE, not a directory -> mkdir(parents=True) raises OSError.
    blocked = tmp_path / "not_a_dir"
    blocked.write_text("x", encoding="utf-8")
    log_path = blocked / "self-update-ansible.log"

    with patch.object(_pe, "SELF_UPDATE_LOG_PATH", log_path):
        result = _pe.PlaybookExecutor._prepare_self_update_log_file()

    assert result is None


# ---------------------------------------------------------------------------
# Command construction
# ---------------------------------------------------------------------------


def test_wrap_with_systemd_scope_builds_expected_command(tmp_path):
    ex = _executor(tmp_path)
    cmd = ["/usr/bin/ansible-playbook", "-i", "inv.yml", "update-all-nodes.yml"]
    env = {"ANSIBLE_FORCE_COLOR": "0", "PATH": "/usr/bin", "SECRET_TOKEN": "s3cr3t"}
    log_path = tmp_path / "self-update-ansible.log"

    wrapped = ex._wrap_with_systemd_scope(cmd, env, log_path)

    assert wrapped[0] == "sudo"
    assert wrapped[1] == "systemd-run"
    assert "--scope" in wrapped
    assert "--collect" in wrapped
    assert any(a.startswith("--unit=autobot-selfupdate-") for a in wrapped)
    assert f"--uid={os.getuid()}" in wrapped
    assert f"--gid={os.getgid()}" in wrapped
    assert f"--working-directory={tmp_path}" in wrapped

    # After `--`: a shell that redirects the FINAL exec'd process's stdio to
    # the log file, never to the backend's pipe, then the original argv.
    tail = wrapped[wrapped.index("--") + 1 :]
    assert tail[0] == "/bin/sh"
    assert tail[1] == "-c"
    assert 'exec "$0" "$@"' in tail[2]
    assert str(log_path) in tail[2]
    assert ">>" in tail[2]  # append, not truncate — this backend already did the one-time truncate
    assert "2>&1" in tail[2]
    assert tail[3:] == cmd


def test_systemd_run_env_args_allowlist_excludes_secrets():
    env = {
        "ANSIBLE_FORCE_COLOR": "0",
        "ANSIBLE_LOCAL_TEMP": "/tmp/x",
        "PATH": "/usr/bin",
        "SECRET_TOKEN": "s3cr3t",
        "POSTGRES_PASSWORD": "hunter2",
    }
    args = _pe.PlaybookExecutor._systemd_run_env_args(env)

    assert "--setenv=ANSIBLE_FORCE_COLOR=0" in args
    assert "--setenv=ANSIBLE_LOCAL_TEMP=/tmp/x" in args
    assert "--setenv=PATH=/usr/bin" in args
    assert not any("SECRET_TOKEN" in a for a in args)
    assert not any("POSTGRES_PASSWORD" in a for a in args)


# ---------------------------------------------------------------------------
# _run_subprocess: wrap+file-backed vs fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_subprocess_wraps_file_backed_when_systemd_available(tmp_path):
    ex = _executor(tmp_path)
    cmd = ["/usr/bin/ansible-playbook", "-i", "inv.yml", "update-all-nodes.yml"]
    env = {"PATH": "/usr/bin"}
    log_path = tmp_path / "self-update-ansible.log"

    captured = {}

    async def _fake_create_subprocess_exec(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return _FakeProcess(returncode=0)

    with patch.object(_pe, "SELF_UPDATE_LOG_PATH", log_path):
        with patch.object(_pe.PlaybookExecutor, "_self_update_detach_available", return_value=True):
            with patch.object(asyncio, "create_subprocess_exec", side_effect=_fake_create_subprocess_exec):
                result = await ex._run_subprocess(cmd, env, progress_callback=None, detach=True)

    assert result["returncode"] == 0
    argv = captured["args"]
    assert argv[0] == "sudo"
    assert argv[1] == "systemd-run"
    assert "--scope" in argv
    assert "--collect" in argv
    tail = list(argv[argv.index("--") + 1 :])
    assert tail[:2] == ["/bin/sh", "-c"]
    assert str(log_path) in tail[2]
    assert tail[3:] == cmd

    # Never the backend's pipe: a dead backend must not be able to
    # BrokenPipe-crash the detached process (#11492 crux).
    assert captured["kwargs"]["stdout"] == asyncio.subprocess.DEVNULL
    assert captured["kwargs"]["stderr"] == asyncio.subprocess.DEVNULL
    # The log file was truncated fresh for this run.
    assert log_path.read_text(encoding="utf-8") == ""


@pytest.mark.asyncio
async def test_run_subprocess_falls_back_without_systemd(tmp_path):
    ex = _executor(tmp_path)
    cmd = ["/usr/bin/ansible-playbook", "-i", "inv.yml", "update-all-nodes.yml"]
    env = {"PATH": "/usr/bin"}

    captured = {}

    async def _fake_create_subprocess_exec(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return _FakeProcess(returncode=0)

    with patch.object(_pe.PlaybookExecutor, "_self_update_detach_available", return_value=False):
        with patch.object(asyncio, "create_subprocess_exec", side_effect=_fake_create_subprocess_exec):
            result = await ex._run_subprocess(cmd, env, progress_callback=None, detach=True)

    assert result["returncode"] == 0
    # No systemd-run wrap, no file redirection — the pre-#11492 direct-exec
    # + pipe behavior is unchanged when systemd-run/service context is absent.
    assert captured["args"] == tuple(cmd)
    assert captured["kwargs"]["stdout"] == asyncio.subprocess.PIPE
    assert captured["kwargs"]["stderr"] == asyncio.subprocess.STDOUT


@pytest.mark.asyncio
async def test_run_subprocess_falls_back_when_log_file_prep_fails(tmp_path):
    """systemd-run is available, but the log file can't be prepared: still
    falls back to the direct pipe-attached exec rather than detaching without
    file-backed output (which would just trade one crash risk for another)."""
    ex = _executor(tmp_path)
    cmd = ["/usr/bin/ansible-playbook", "-i", "inv.yml", "update-all-nodes.yml"]
    env = {"PATH": "/usr/bin"}

    captured = {}

    async def _fake_create_subprocess_exec(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return _FakeProcess(returncode=0)

    with patch.object(_pe.PlaybookExecutor, "_self_update_detach_available", return_value=True):
        with patch.object(_pe.PlaybookExecutor, "_prepare_self_update_log_file", return_value=None):
            with patch.object(asyncio, "create_subprocess_exec", side_effect=_fake_create_subprocess_exec):
                result = await ex._run_subprocess(cmd, env, progress_callback=None, detach=True)

    assert result["returncode"] == 0
    assert captured["args"] == tuple(cmd)
    assert captured["kwargs"]["stdout"] == asyncio.subprocess.PIPE
    assert captured["kwargs"]["stderr"] == asyncio.subprocess.STDOUT


@pytest.mark.asyncio
async def test_run_subprocess_unwrapped_when_detach_false(tmp_path):
    """Ordinary per-role/per-node deploys (detach=False) are unaffected: PIPE,
    no wrap, no file redirection — byte-for-byte the pre-#11492 behavior."""
    ex = _executor(tmp_path)
    cmd = ["/usr/bin/ansible-playbook", "-i", "inv.yml", "site.yml"]
    env = {"PATH": "/usr/bin"}

    captured = {}

    async def _fake_create_subprocess_exec(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return _FakeProcess(returncode=0)

    with patch.object(_pe.PlaybookExecutor, "_self_update_detach_available", return_value=True):
        with patch.object(asyncio, "create_subprocess_exec", side_effect=_fake_create_subprocess_exec):
            await ex._run_subprocess(cmd, env, progress_callback=None, detach=False)

    assert captured["args"] == tuple(cmd)
    assert captured["kwargs"]["stdout"] == asyncio.subprocess.PIPE
    assert captured["kwargs"]["stderr"] == asyncio.subprocess.STDOUT


# ---------------------------------------------------------------------------
# Log-file tailing parses the same progress lines the pipe would have
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tail_playbook_log_parses_existing_lines_then_stops(tmp_path):
    log_path = tmp_path / "self-update-ansible.log"
    log_path.write_text(
        "PLAY [Play 1 - Update SLM Server First] ****\n"
        "TASK [[PLAY 1] SLM | Restart autobot-slm-backend] ****\n",
        encoding="utf-8",
    )
    ex = _executor(tmp_path)
    process = _FakeProcess(returncode=0)  # already "exited" -> tail stops after draining the file

    seen = []

    async def _progress_callback(progress):
        seen.append(progress)

    output_lines = await ex._tail_playbook_log(log_path, process, _progress_callback)

    assert len(output_lines) == 2
    stages = [p["stage"] for p in seen]
    assert "play1_start" in stages
    assert "slm_restarting" in stages
