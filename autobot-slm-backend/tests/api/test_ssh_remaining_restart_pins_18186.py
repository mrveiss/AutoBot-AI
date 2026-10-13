# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The four other SSH systemctl sites keep their exact argv, timeout and failure handling (#18186).

backup (redis stop/start), blue_green (stop), code_distributor (`restart ... || true`) and
service_orchestrator (`_systemctl_action`) move onto the one executor with NO behaviour change.
These pins go through each site's public entry point with autospecced fakes, and pass on the tree
from before the move, which is what shows they are today's behaviour.
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import sys
from pathlib import Path
from unittest.mock import create_autospec

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
_real_orm = importlib.import_module("_real_orm_import")
SLM_ROOT, import_modules_with_real_orm = _real_orm.SLM_ROOT, _real_orm.import_modules_with_real_orm

_SVC = SLM_ROOT / "services"
_LOADED = import_modules_with_real_orm(
    (),
    path_loaded={
        "services.service_restart": _SVC / "service_restart.py",
        "services.backup": _SVC / "backup.py",
        "services.blue_green": _SVC / "blue_green.py",
        "services.code_distributor": _SVC / "code_distributor.py",
        "services.service_orchestrator": _SVC / "service_orchestrator.py",
    },
)
_, backup, blue_green, code_distributor, service_orchestrator = _LOADED


_REAL = (asyncio.create_subprocess_exec, asyncio.wait_for, asyncio.sleep)  # captured before any fake replaces them


class _Proc:
    def __init__(self, rc: int, out: bytes, err: bytes) -> None:
        self.returncode = rc
        self._io = (out, err)

    async def communicate(self, **_kwargs) -> tuple[bytes, bytes]:
        return self._io


class _Runner:
    """Records every spawn (argv, kwargs) and wait timeout; plays back scripted outcomes in order."""

    def __init__(self, monkeypatch, script=((0, b"out", b"err"),), spawn_error=None, timeout=False):
        self.spawns: list[tuple[list, dict]] = []
        self.timeouts: list = []
        script = list(script)

        async def _spawn(*argv, **kwargs):
            self.spawns.append((list(argv), kwargs))
            if spawn_error:
                raise spawn_error
            rc, out, err = script.pop(0) if len(script) > 1 else script[0]
            return _Proc(rc, out, err)

        async def _wait_for(aw, timeout=None):
            self.timeouts.append(timeout)
            if expire:
                aw.close()
                raise asyncio.TimeoutError
            return await aw

        async def _sleep(delay, result=None):
            return result

        expire = timeout
        monkeypatch.setattr(
            asyncio, "create_subprocess_exec", create_autospec(_REAL[0], spec_set=True, side_effect=_spawn)
        )
        monkeypatch.setattr(asyncio, "wait_for", create_autospec(_REAL[1], spec_set=True, side_effect=_wait_for))
        monkeypatch.setattr(asyncio, "sleep", create_autospec(_REAL[2], spec_set=True, side_effect=_sleep))

    @property
    def argv(self) -> list:
        return self.spawns[0][0]

    @property
    def kwargs(self) -> dict:
        return self.spawns[0][1]


def _fake_logger(monkeypatch, module):
    fake = create_autospec(logging.Logger, instance=True, spec_set=True)
    monkeypatch.setattr(module, "logger", fake)
    return fake


_FAILURES = [{"timeout": True}, {"spawn_error": OSError("boom")}]

# ---- backup: redis stop / start --------------------------------------------------------------

_BACKUP_PREFIX = [
    "/usr/bin/ssh",
    "-o",
    "StrictHostKeyChecking=accept-new",
    "-o",
    "ConnectTimeout=15",
    "-o",
    "BatchMode=yes",
    "-p",
    "2222",
    "--",
    "svc@node.example.test",
]


def _backup():
    return backup.BackupService.__new__(backup.BackupService)


async def test_backup_stop_redis_argv_no_dash_n_merged_stderr_timeout_30(monkeypatch):
    run = _Runner(monkeypatch)
    await _backup()._stop_redis_for_restore("node.example.test", "svc", 2222)
    assert run.argv == [*_BACKUP_PREFIX, f"sudo systemctl stop -- {backup.REDIS_UNIT}"]
    assert run.kwargs.get("stdin") is None
    assert (run.kwargs["stdout"], run.kwargs["stderr"]) == (asyncio.subprocess.PIPE, asyncio.subprocess.STDOUT)
    assert run.timeouts == [30]


async def test_backup_stop_redis_raises_with_the_output_on_failure(monkeypatch):
    _Runner(monkeypatch, script=((1, b" nope \n", b""),))
    with pytest.raises(RuntimeError) as exc:
        await _backup()._stop_redis_for_restore("h", "svc", 22)
    assert str(exc.value) == f"cannot restore: stop {backup.REDIS_UNIT} on h: nope"


@pytest.mark.parametrize(
    ("failure", "text"), [(_FAILURES[0], "Command timed out"), (_FAILURES[1], "Command execution failed")]
)
async def test_backup_stop_redis_timeout_and_error_text(monkeypatch, failure, text):
    _Runner(monkeypatch, **failure)
    with pytest.raises(RuntimeError) as exc:
        await _backup()._stop_redis_for_restore("h", "svc", 22)
    assert str(exc.value).endswith(f"on h: {text}")


async def test_backup_start_redis_argv_then_verify_and_failure_text(monkeypatch):
    run = _Runner(monkeypatch, script=((0, b"", b""), (0, b"PONG\n7", b"")))
    assert await _backup()._start_and_verify_redis("node.example.test", "svc", 2222) == (True, "PONG\n7")
    assert run.spawns[0][0] == [*_BACKUP_PREFIX, f"sudo systemctl start -- {backup.REDIS_UNIT}"]
    assert run.timeouts == [30, 15]
    _Runner(monkeypatch, script=((1, b"bad", b""),))
    assert await _backup()._start_and_verify_redis("h", "svc", 22) == (False, "Failed to start Redis: bad")


# ---- blue_green: stop -------------------------------------------------------------------------

_BG_PREFIX = [
    "ssh",
    "-o",
    "StrictHostKeyChecking=accept-new",
    "-o",
    "ConnectTimeout=10",
    "-o",
    "BatchMode=yes",
    "-p",
    "2222",
    "--",
    "svc@node.example.test",
]


def _bg():
    return blue_green.BlueGreenService.__new__(blue_green.BlueGreenService)


async def test_blue_green_stop_argv_no_dash_n_pipe_pipe_timeout_30(monkeypatch):
    run = _Runner(monkeypatch, script=((0, b"", b""),))
    assert await _bg()._stop_service_via_ssh("node.example.test", "svc", 2222, "autobot-x") is True
    assert run.argv == [*_BG_PREFIX, "sudo systemctl stop -- autobot-x"]
    assert (run.kwargs["stdout"], run.kwargs["stderr"]) == (asyncio.subprocess.PIPE, asyncio.subprocess.PIPE)
    assert run.timeouts == [30.0]


async def test_blue_green_stop_failure_handling(monkeypatch):
    _Runner(monkeypatch, script=((1, b"", b"x"),))
    assert await _bg()._stop_service_via_ssh("h", "svc", 22, "autobot-x") is False
    for failure in _FAILURES:
        fake = _fake_logger(monkeypatch, blue_green)
        _Runner(monkeypatch, **failure)
        assert await _bg()._stop_service_via_ssh("h", "svc", 22, "autobot-x") is False
        assert fake.warning.call_args.args[:2] == ("Failed to stop service %s: %s", "autobot-x")


async def test_blue_green_rejects_an_invalid_name_without_spawning(monkeypatch):
    run = _Runner(monkeypatch)
    assert await _bg()._stop_service_via_ssh("h", "svc", 22, "a; rm -rf /") is False
    assert run.spawns == []


# ---- code_distributor: restart ... || true -------------------------------------------------------


@pytest.fixture
def key(tmp_path):
    path = tmp_path / "id"
    path.write_text("k", encoding="utf-8")
    return path


async def test_code_distributor_restart_argv_or_true_merged_stderr_timeout_60(monkeypatch, key):
    monkeypatch.setattr(code_distributor, "SSH_KEY_PATH", str(key))
    fake = _fake_logger(monkeypatch, code_distributor)
    run = _Runner(monkeypatch, script=((0, b"fine", b""),))
    dist = code_distributor.CodeDistributor.__new__(code_distributor.CodeDistributor)
    await dist._restart_slm_agent("n1", "node.example.test", "svc", 2222)
    assert run.argv == [
        "ssh", "-o", "StrictHostKeyChecking=accept-new", "-o", "ConnectTimeout=30", "-p", "2222",
        "-i", str(key), "--", "svc@node.example.test", "sudo systemctl restart -- slm-agent || true",
    ]  # fmt: skip
    assert (run.kwargs["stdout"], run.kwargs["stderr"]) == (asyncio.subprocess.PIPE, asyncio.subprocess.STDOUT)
    assert run.timeouts == [60.0]
    fake.info.assert_called_with("slm-agent restarted on node %s", "n1")
    fake.reset_mock()
    _Runner(monkeypatch, script=((1, b"why", b""),))
    await dist._restart_slm_agent("n1", "h", "svc", 22)
    fake.warning.assert_called_once_with("slm-agent restart may have failed on %s: %s", "n1", "why")
    for failure in _FAILURES:
        fake.reset_mock()
        _Runner(monkeypatch, **failure)
        await dist._restart_slm_agent("n1", "h", "svc", 22)
        assert fake.warning.call_args.args[:2] == ("Could not restart slm-agent on %s: %s", "n1")


# ---- service_orchestrator: _systemctl_action -------------------------------------------------------


def _orch(tmp_path):
    orch = service_orchestrator.ServiceOrchestrator.__new__(service_orchestrator.ServiceOrchestrator)
    orch.ssh_key, orch.ssh_user = tmp_path / "id", "autobot"
    orch._ssh_semaphore = asyncio.Semaphore(1)
    return orch


def _orch_prefix(tmp_path):
    return [
        "/usr/bin/ssh",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        "ConnectTimeout=10",
        "-o",
        "BatchMode=yes",
        "-i",
        str(tmp_path / "id"),
        "--",
        "autobot@node.example.test",
    ]


async def test_orchestrator_systemctl_action_argv_dash_n_pipe_pipe_timeout_30(monkeypatch, tmp_path):
    run = _Runner(monkeypatch, script=((0, b"done", b""),))
    result = await _orch(tmp_path)._systemctl_action("node.example.test", "x.service", "restart")
    assert result == (True, "done")
    assert run.argv == [*_orch_prefix(tmp_path), "sudo -n systemctl restart -- x.service"]
    assert (run.kwargs["stdout"], run.kwargs["stderr"]) == (asyncio.subprocess.PIPE, asyncio.subprocess.PIPE)
    assert run.timeouts == [30.0]


async def test_orchestrator_systemctl_action_user_scope_is_untouched(monkeypatch, tmp_path):
    run = _Runner(monkeypatch, script=((0, b"", b""),))
    result = await _orch(tmp_path)._systemctl_action("h", "x.service", "stop", requires_sudo=False)
    assert result == (True, "Command completed successfully")
    assert run.argv[-1] == "systemctl --user stop -- x.service"


@pytest.mark.parametrize("unit", ["x;id", "$(id)", "`id`", "a b", "-H", "a\nid"])
async def test_orchestrator_user_scope_refuses_a_hostile_unit_before_spawning(monkeypatch, tmp_path, unit):
    run = _Runner(monkeypatch, script=((0, b"", b""),))
    with pytest.raises(ValueError):
        await _orch(tmp_path)._systemctl_action("h", unit, "stop", requires_sudo=False)
    assert run.spawns == []


async def test_orchestrator_user_scope_refuses_a_non_allowlisted_action(monkeypatch, tmp_path):
    run = _Runner(monkeypatch, script=((0, b"", b""),))
    with pytest.raises(ValueError):
        await _orch(tmp_path)._systemctl_action("h", "x.service", "enable", requires_sudo=False)
    assert run.spawns == []


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"script": ((1, b"", b"e" * 900),)}, (False, "Command failed: " + "e" * 500)),
        ({"timeout": True}, (False, "SSH command timed out")),
        ({"spawn_error": OSError("boom")}, (False, "SSH command error")),
    ],
)
async def test_orchestrator_systemctl_action_failure_tuples(monkeypatch, tmp_path, kwargs, expected):
    _Runner(monkeypatch, **kwargs)
    assert await _orch(tmp_path)._systemctl_action("h", "x.service", "start") == expected
