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
  1. Detach that one run into its own transient systemd unit (a separate
     cgroup) so it survives the restart, gated to the self-update path only
     and falling back to the direct exec when systemd-run / a systemd-service
     context is unavailable (dev mode, tests, containers).

     #12596: that unit must be a transient SERVICE (`systemd-run --collect
     --wait --slice=system.slice`), not a `--scope`. A scope keeps its payload
     a descendant of the invoking process, so a scope created from inside
     autobot-slm-backend stayed nested in that service's cgroup subtree and
     the Play-1 restart tore it down anyway — Play 2/3 never ran while the
     update still reported success.
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
import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

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
_DEFAULT_SHARED_DIR = _pe.SELF_UPDATE_SHARED_DIR


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
    # Ansible output can contain sensitive paths/values — 0600, not the
    # world-readable default umask (#11492 hardening).
    assert oct(log_path.stat().st_mode & 0o777) == "0o600"


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


def test_wrap_with_systemd_unit_builds_expected_command(tmp_path):
    ex = _executor(tmp_path)
    cmd = ["/usr/bin/ansible-playbook", "-i", "inv.yml", "update-all-nodes.yml"]
    env = {"ANSIBLE_FORCE_COLOR": "0", "PATH": "/usr/bin", "SECRET_TOKEN": "s3cr3t"}
    log_path = tmp_path / "self-update-ansible.log"

    wrapped = ex._wrap_with_systemd_unit(cmd, env, log_path)

    assert wrapped[0] == "sudo"
    assert wrapped[1] == "-n"  # non-interactive: fast-fail, never hang on a password prompt
    assert wrapped[2] == "systemd-run"
    # #12596: a transient SERVICE (PID 1-owned), never a --scope nested in this
    # backend's cgroup — see test_detached_run_is_a_transient_service_not_a_scope.
    assert "--scope" not in wrapped
    assert "--collect" in wrapped
    assert "--wait" in wrapped
    assert f"--slice={_pe.SELF_UPDATE_DETACH_SLICE}" in wrapped
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


def test_systemd_run_env_args_ansible_allowlist_is_enumerated_not_prefix():
    """An ANSIBLE_*-prefixed var outside the enumerated set (e.g. a vault
    password) must never forward just by matching the "ANSIBLE_" prefix
    (#11492 hardening — the allowlist is a fixed enumeration, not a prefix
    match)."""
    env = {
        "ANSIBLE_FORCE_COLOR": "0",  # enumerated -> forwarded
        "ANSIBLE_VAULT_PASSWORD": "hunter2",  # NOT enumerated -> must never forward
        "ANSIBLE_UNKNOWN_FUTURE_VAR": "whatever",  # NOT enumerated -> must never forward
    }
    args = _pe.PlaybookExecutor._systemd_run_env_args(env)

    assert "--setenv=ANSIBLE_FORCE_COLOR=0" in args
    assert not any("ANSIBLE_VAULT_PASSWORD" in a for a in args)
    assert not any("ANSIBLE_UNKNOWN_FUTURE_VAR" in a for a in args)


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
    assert argv[1] == "-n"
    assert argv[2] == "systemd-run"
    assert "--scope" not in argv  # #12596: transient service, not a nested scope
    assert "--collect" in argv
    tail = list(argv[argv.index("--") + 1 :])
    assert tail[:2] == ["/bin/sh", "-c"]
    assert str(log_path) in tail[2]
    assert tail[3:] == cmd

    # Never the backend's pipe: a dead backend must not be able to
    # BrokenPipe-crash the detached process (#11492 crux).
    assert captured["kwargs"]["stdout"] == asyncio.subprocess.DEVNULL
    assert captured["kwargs"]["stderr"] == asyncio.subprocess.DEVNULL
    # The log file was truncated fresh for this run and locked to 0600.
    assert log_path.read_text(encoding="utf-8") == ""
    assert oct(log_path.stat().st_mode & 0o777) == "0o600"


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
async def test_run_subprocess_falls_back_to_attached_when_all_log_paths_fail(tmp_path):
    """systemd-run is available, but NEITHER the canonical NOR the #12425
    fallback log path can be prepared (e.g. the uid-scoped tmp dir is also
    unwritable): only then does the run fall back to the direct
    pipe-attached exec rather than detaching without file-backed output
    (which would just trade one crash risk for another)."""
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
            with patch.object(_pe.PlaybookExecutor, "_write_fresh_log_file", return_value=None):
                with patch.object(asyncio, "create_subprocess_exec", side_effect=_fake_create_subprocess_exec):
                    result = await ex._run_subprocess(cmd, env, progress_callback=None, detach=True)

    assert result["returncode"] == 0
    assert captured["args"] == tuple(cmd)
    assert captured["kwargs"]["stdout"] == asyncio.subprocess.PIPE
    assert captured["kwargs"]["stderr"] == asyncio.subprocess.STDOUT


@pytest.mark.asyncio
async def test_run_subprocess_still_detaches_via_fallback_log_path(tmp_path):
    """#12425: the canonical /var/log/autobot path can be unwritable (e.g.
    owned by a different autobot-* service user) while systemd-run is fully
    available. That must NOT silently drop to the known-broken attached run
    (#11492) — it must retry under the uid-scoped fallback path and still
    detach."""
    ex = _executor(tmp_path)
    cmd = ["/usr/bin/ansible-playbook", "-i", "inv.yml", "update-all-nodes.yml"]
    env = {"PATH": "/usr/bin"}
    fallback_log_path = tmp_path / "fallback" / "self-update-ansible.log"

    captured = {}

    async def _fake_create_subprocess_exec(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return _FakeProcess(returncode=0)

    with patch.object(_pe.PlaybookExecutor, "_self_update_detach_available", return_value=True):
        with patch.object(_pe.PlaybookExecutor, "_prepare_self_update_log_file", return_value=None):
            with patch.object(_pe, "SELF_UPDATE_LOG_FALLBACK_PATH", fallback_log_path):
                with patch.object(asyncio, "create_subprocess_exec", side_effect=_fake_create_subprocess_exec):
                    result = await ex._run_subprocess(cmd, env, progress_callback=None, detach=True)

    assert result["returncode"] == 0
    argv = captured["args"]
    # Still wrapped + detached, not the pipe-attached exec.
    assert argv[0] == "sudo"
    assert argv[2] == "systemd-run"
    tail = list(argv[argv.index("--") + 1 :])
    assert str(fallback_log_path) in tail[2]
    assert tail[3:] == cmd
    assert captured["kwargs"]["stdout"] == asyncio.subprocess.DEVNULL
    assert captured["kwargs"]["stderr"] == asyncio.subprocess.DEVNULL
    # The fallback log file was actually created, truncated, and locked down.
    assert fallback_log_path.read_text(encoding="utf-8") == ""
    assert oct(fallback_log_path.stat().st_mode & 0o777) == "0o600"


def test_write_fresh_log_file_creates_truncates_and_chmods(tmp_path):
    log_path = tmp_path / "sub" / "fresh.log"
    log_path.parent.mkdir(parents=True)
    log_path.write_text("stale prior run content\n", encoding="utf-8")

    result = _pe.PlaybookExecutor._write_fresh_log_file(log_path)

    assert result == log_path
    assert log_path.read_text(encoding="utf-8") == ""
    assert oct(log_path.stat().st_mode & 0o777) == "0o600"


def test_write_fresh_log_file_returns_none_on_failure(tmp_path):
    blocked = tmp_path / "not_a_dir"
    blocked.write_text("x", encoding="utf-8")
    log_path = blocked / "fresh.log"

    assert _pe.PlaybookExecutor._write_fresh_log_file(log_path) is None


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
        "PLAY [Play 1 - Update SLM Server First] ****\n" "TASK [[PLAY 1] SLM | Restart autobot-slm-backend] ****\n",
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


# ---------------------------------------------------------------------------
# #12596: the detached run must not be nested in this backend's cgroup
# ---------------------------------------------------------------------------


def test_detached_run_is_a_transient_service_not_a_scope(tmp_path):
    """The self-update run must survive Play 1's own SLM restart.

    #11492/#12567 detached via ``systemd-run --scope``. A scope keeps its
    payload a descendant of the *invoking* process, so a scope created from
    inside ``autobot-slm-backend`` is nested in that service's cgroup subtree.
    Play 1 then runs ``systemctl restart autobot-slm-backend`` and systemd
    (KillMode=control-group) tore the nested scope down with the service —
    the run died at the end of Play 1 and Play 2/3 never deployed the
    co-located app tier or the workers, while the update still reported OK.

    A transient service is forked by PID 1 and lives in ``system.slice``, so
    restarting this backend cannot control-group-kill it.
    """
    ex = _executor(tmp_path)
    wrapped = ex._wrap_with_systemd_unit(
        ["/usr/bin/ansible-playbook", "update-all-nodes.yml"],
        {"PATH": "/usr/bin"},
        tmp_path / "self-update.log",
    )

    # The regression itself: --scope must never come back.
    assert "--scope" not in wrapped

    # Placement is stated explicitly, so cgroup delegation on this service can
    # never silently re-nest the unit under the caller again.
    assert f"--slice={_pe.SELF_UPDATE_DETACH_SLICE}" in wrapped
    assert _pe.SELF_UPDATE_DETACH_SLICE == "system.slice"

    # Named + garbage-collected so repeat runs neither collide nor leak units.
    assert any(a.startswith("--unit=autobot-selfupdate-") for a in wrapped)
    assert "--collect" in wrapped


def test_detached_service_waits_so_exit_code_still_propagates(tmp_path):
    """--wait preserves the pre-#12596 blocking semantics.

    Without it, ``systemd-run`` in service mode returns as soon as the unit has
    been *started*, so a detached run that does not restart this backend would
    report success immediately and the caller would lose the real exit code.
    When the Play-1 restart does land, only this waiting client is killed — the
    transient service keeps running to completion on its own.
    """
    ex = _executor(tmp_path)
    wrapped = ex._wrap_with_systemd_unit(
        ["/usr/bin/ansible-playbook", "update-all-nodes.yml"],
        {"PATH": "/usr/bin"},
        tmp_path / "self-update.log",
    )

    assert "--wait" in wrapped
    # --wait must be an option to systemd-run, not an argument to the payload.
    assert wrapped.index("--wait") < wrapped.index("--")


# ---------------------------------------------------------------------------
# #12803: a detached payload cannot see this service's PrivateTmp /tmp
# ---------------------------------------------------------------------------


def test_detached_run_stages_files_outside_private_tmp(tmp_path, monkeypatch):
    """Staging must leave /tmp, because the payload is in a different namespace.

    autobot-slm-backend.service sets PrivateTmp=true, so this process's /tmp is
    a private mount namespace. Under the old --scope the payload stayed in this
    process's namespace and read the inventory fine. A transient service is
    forked by PID 1 and gets the HOST /tmp, so anything under ANSIBLE_LOCAL_TMP
    is invisible to it — ansible died instantly with "Unable to parse ... as an
    inventory source" (#12803). ProtectSystem=strict leaves /opt/autobot
    (ReadWritePaths) as the only writable non-namespaced location.
    """
    shared = tmp_path / "shared"
    monkeypatch.setattr(_pe, "SELF_UPDATE_SHARED_DIR", shared)

    staged = _pe.PlaybookExecutor._stage_dir_for_run(detach=True)

    assert staged == str(shared)
    assert shared.is_dir()
    assert oct(shared.stat().st_mode & 0o777) == "0o700"

    # The invariant that actually matters is on the SHIPPED default, not on the
    # tmp_path fixture above (which is itself under /tmp): the default staging
    # dir must live outside the namespaced /tmp and inside ReadWritePaths.
    default = str(_DEFAULT_SHARED_DIR)
    assert not default.startswith("/tmp"), default
    assert default.startswith("/opt/autobot"), default


def test_attached_run_keeps_using_the_uid_tmp_dir(tmp_path, monkeypatch):
    """An attached payload shares this process's namespace — /tmp is correct
    there, so the #12803 staging must not change non-detached behaviour."""
    monkeypatch.setattr(_pe, "SELF_UPDATE_SHARED_DIR", tmp_path / "unused")

    assert _pe.PlaybookExecutor._stage_dir_for_run(detach=False) is None
    assert not (tmp_path / "unused").exists(), "attached runs must not create the shared dir"


def test_staging_failure_degrades_instead_of_aborting(tmp_path, monkeypatch):
    """If the shared dir cannot be created, fall back rather than kill the update."""
    blocked = tmp_path / "not_a_dir"
    blocked.write_text("x", encoding="utf-8")
    monkeypatch.setattr(_pe, "SELF_UPDATE_SHARED_DIR", blocked / "sub")

    assert _pe.PlaybookExecutor._stage_dir_for_run(detach=True) is None


def test_prune_removes_only_files_past_the_ttl(tmp_path, monkeypatch):
    """Pruning reclaims old staged files without ever racing a live run."""
    shared = tmp_path / "shared"
    shared.mkdir(mode=0o700)
    monkeypatch.setattr(_pe, "SELF_UPDATE_SHARED_DIR", shared)
    monkeypatch.setattr(_pe, "SELF_UPDATE_STAGE_TTL_SECONDS", 100.0)

    fresh = shared / "autobot_inv_fresh.yml"
    stale = shared / "autobot_inv_stale.yml"
    for f in (fresh, stale):
        f.write_text("x", encoding="utf-8")
    old = time.time() - 500
    os.utime(stale, (old, old))

    _pe.PlaybookExecutor._prune_stage_dir()

    assert fresh.exists(), "a file inside the TTL belongs to a possibly-live run"
    assert not stale.exists()


async def _run_playbook_capturing_staged_files(tmp_path, monkeypatch, *, detach: bool):
    """Drive a whole ``execute_playbook`` and report which staged files survive.

    Everything below the staging decision is stubbed: the point is what the
    ``finally`` block does to the two files, not what Ansible does.
    """
    ansible_dir = tmp_path / "ansible"
    ansible_dir.mkdir()
    (ansible_dir / "update-all-nodes.yml").write_text("- hosts: all\n", encoding="utf-8")
    shared = tmp_path / "shared"
    shared.mkdir(mode=0o700)
    monkeypatch.setattr(_pe, "SELF_UPDATE_SHARED_DIR", shared)
    monkeypatch.setattr(_pe, "fetch_deploy_secrets", AsyncMock(return_value={}))

    ex = _executor(ansible_dir)
    ex.inventory_path = ansible_dir / "slm-nodes.yml"

    async def _fake_inventory(_self, stage_dir=None):
        path = Path(stage_dir or tmp_path) / "autobot_inv_run.yml"
        path.write_text("all:\n", encoding="utf-8")
        return path

    def _fake_extra_vars(extra_vars, uid_tmp_dir=None):
        # ``services.inventory_builder`` is a MagicMock in this module's loader,
        # so the real writer produces no file. Write a real one into the same
        # stage dir: the assertion is what the ``finally`` block does to it.
        path = Path(uid_tmp_dir or tmp_path) / "autobot_evars_run.json"
        path.write_text(json.dumps(extra_vars), encoding="utf-8")
        return path

    monkeypatch.setattr(_pe, "write_temp_extra_vars", _fake_extra_vars)
    monkeypatch.setattr(_pe.PlaybookExecutor, "_build_dynamic_inventory", _fake_inventory)
    monkeypatch.setattr(
        _pe.PlaybookExecutor,
        "_build_ansible_command",
        lambda *a, **kw: ["/usr/bin/ansible-playbook", "update-all-nodes.yml"],
    )
    monkeypatch.setattr(_pe.PlaybookExecutor, "_build_ansible_env", lambda _self: {"PATH": "/usr/bin"})
    monkeypatch.setattr(
        _pe.PlaybookExecutor,
        "_run_subprocess",
        AsyncMock(return_value={"returncode": 0, "output": ""}),
    )

    result = await ex.execute_playbook(
        "update-all-nodes.yml",
        extra_vars={"a_secret": "value"},  # forces an extra-vars file into stage_dir
        detach=detach,
    )
    survivors = sorted(f.name for f in shared.iterdir()) if shared.exists() else []
    return result, survivors


@pytest.mark.asyncio
async def test_a_detached_run_leaves_both_staged_files_on_disk(tmp_path, monkeypatch):
    """The caller must not unlink files the detached payload still owns.

    #12803 reported this as the root cause. It was not -- the real cause was
    the PrivateTmp namespace -- but the deletion IS a live hazard now that the
    payload outlives this coroutine by design (Play 1 restarts this service
    mid-run). BOTH files must survive: they are removed by two separate
    branches, and guarding only one leaves the extra-vars race intact.

    This replaces a source-text check that compared ``str.index`` positions of
    ``"if detach:"``, ``"dynamic_inv_path.unlink"`` and ``"extra_vars_file.unlink"``
    inside ``inspect.getsource(execute_playbook)`` (#13311) -- it asserted the
    *textual order* of three substrings, so it passed for an ``if detach:``
    belonging to some other statement and broke on any reordering that changed
    nothing.
    """
    result, survivors = await _run_playbook_capturing_staged_files(tmp_path, monkeypatch, detach=True)

    assert result["success"] is True
    assert any(name.startswith("autobot_inv_") for name in survivors), (
        f"#12803: the staged inventory was deleted under a still-starting "
        f"detached run; survivors={survivors}"
    )
    assert len(survivors) >= 2, (
        f"#12803: the extra-vars file was deleted under a still-starting "
        f"detached run; survivors={survivors}"
    )


@pytest.mark.asyncio
async def test_an_attached_run_still_cleans_both_staged_files(tmp_path, monkeypatch):
    """The mirror: the detach guard must not turn into a permanent leak.

    Attached runs own their payload for the whole call, so nothing may be
    left behind for ``_prune_stage_dir`` to reclaim later.
    """
    result, survivors = await _run_playbook_capturing_staged_files(tmp_path, monkeypatch, detach=False)

    assert result["success"] is True
    assert survivors == [], f"attached run leaked staged files: {survivors}"
