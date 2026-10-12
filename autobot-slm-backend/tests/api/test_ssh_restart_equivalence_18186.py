# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The three SSH systemd-restart sites keep their exact argv, timeout and failure handling (#18186).

#18186 puts the three implementations behind one executor in `services/service_restart.py`
WITHOUT unifying their `sudo -n` flag, timeout or failure handling -- that is an owner decision
tracked on #17455. These tests pin each site's behaviour through its public entry point only, so
they pass on the tree from before the consolidation and prove the pin is what the sites did.

The fakes are autospecced with `spec_set=True` so a signature the real call does not accept
fails here instead of passing against a looser fake.
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import create_autospec

import pytest

from autobot_shared.ssot_config import config

# The root conftest stubs `services.service_restart` and `services.sync_orchestrator` as
# MagicMocks, and `models.database` with them. Load the three modules under test for real, the
# way test_restart_all_session_lifetime_15611.py does, so the sites run their own code.
sys.path.insert(0, str(Path(__file__).resolve().parent))
_real_orm = importlib.import_module("_real_orm_import")
SLM_ROOT, import_modules_with_real_orm = _real_orm.SLM_ROOT, _real_orm.import_modules_with_real_orm

service_restart, sync_orchestrator, roles = import_modules_with_real_orm(
    ("services.sync_orchestrator", "api.roles"),
    path_loaded={"services.service_restart": SLM_ROOT / "services" / "service_restart.py"},
)

_KEY = config.path.ssh_key_path
_NODE = SimpleNamespace(ssh_user="svc", ssh_port=2222, ip_address="node.example.test", hostname="n1", node_id="n1")
_FULL_SSH_PREFIX = [
    "/usr/bin/ssh",
    "-o",
    "StrictHostKeyChecking=accept-new",
    "-o",
    "ConnectTimeout=10",
    "-o",
    "BatchMode=yes",
    "-i",
    _KEY,
    "-p",
    "2222",
    "svc@node.example.test",
]


class _Proc:
    def __init__(self, rc: int, out: bytes, err: bytes) -> None:
        self.returncode = rc
        self._io = (out, err)

    async def communicate(self) -> tuple[bytes, bytes]:
        return self._io


class _Runner:
    """Records what the site spawned and with which timeout; returns a scripted outcome."""

    def __init__(self, monkeypatch, rc=0, out=b"out", err=b"err", spawn_error=None, timeout=False):
        self.argv: list[str] = []
        self.kwargs: dict = {}
        self.timeout = None
        self.calls = 0

        async def _spawn(*argv, **kwargs):
            self.calls += 1
            self.argv, self.kwargs = list(argv), kwargs
            if spawn_error:
                raise spawn_error
            return _Proc(rc, out, err)

        async def _wait_for(aw, timeout=None):
            self.timeout = timeout
            if timeout_flag:
                aw.close()
                raise asyncio.TimeoutError
            return await aw

        timeout_flag = timeout
        spawn = create_autospec(asyncio.create_subprocess_exec, spec_set=True, side_effect=_spawn)
        wait = create_autospec(asyncio.wait_for, spec_set=True, side_effect=_wait_for)
        monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
        monkeypatch.setattr(asyncio, "wait_for", wait)


def _ctx(units=("a.service", "b.service"), restart=True):
    ctx = sync_orchestrator.SyncNodeContext()
    ctx.node_ip, ctx.node_user, ctx.node_port = "node.example.test", "svc", 2222
    ctx.auto_restart, ctx.systemd_service = restart, list(units) if units else None
    return ctx


@pytest.fixture
def orch_logger(monkeypatch, tmp_path):
    fake = create_autospec(logging.Logger, instance=True, spec_set=True)
    monkeypatch.setattr(sync_orchestrator, "logger", fake)
    # SyncOrchestrator() creates its cache dir; the default is a host path a CI runner lacks.
    monkeypatch.setattr(sync_orchestrator, "CODE_CACHE_DIR", tmp_path / "code-cache")
    return fake


@pytest.fixture
def usable_key(monkeypatch, tmp_path):
    key = tmp_path / "id"
    key.write_text("k", encoding="utf-8")
    monkeypatch.setattr(sync_orchestrator, "SSH_KEY_PATH", key)
    return key


async def test_orchestrator_argv_has_no_dash_n_one_call_all_units_and_literal_60(monkeypatch, orch_logger, usable_key):
    run = _Runner(monkeypatch)
    await sync_orchestrator.SyncOrchestrator()._restart_systemd_service(_ctx(), "n1", True)
    assert run.argv == [
        "ssh",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        "ConnectTimeout=10",
        "-p",
        "2222",
        "-i",
        str(usable_key),
        "svc@node.example.test",
        "sudo systemctl restart -- a.service b.service",
    ]
    assert run.kwargs == {"stdout": asyncio.subprocess.PIPE, "stderr": asyncio.subprocess.STDOUT}
    assert run.timeout == 60


async def test_orchestrator_swallows_a_nonzero_exit_and_logs_restarted(monkeypatch, orch_logger, usable_key):
    _Runner(monkeypatch, rc=1)
    assert await sync_orchestrator.SyncOrchestrator()._restart_systemd_service(_ctx(), "n1", True) is None
    orch_logger.info.assert_called_once_with("Restarted %s on %s", "a.service b.service", "n1")
    orch_logger.warning.assert_not_called()


@pytest.mark.parametrize("failure", [{"timeout": True}, {"spawn_error": OSError("no ssh")}])
async def test_orchestrator_turns_a_timeout_or_error_into_one_warning(monkeypatch, orch_logger, usable_key, failure):
    _Runner(monkeypatch, **failure)
    assert await sync_orchestrator.SyncOrchestrator()._restart_systemd_service(_ctx(), "n1", True) is None
    assert orch_logger.warning.call_count == 1
    assert orch_logger.warning.call_args.args[0] == "Service restart failed: %s"
    orch_logger.info.assert_not_called()


@pytest.mark.parametrize(
    ("ctx", "restart"),
    [(_ctx(), False), (_ctx(restart=False), True), (_ctx(units=None), True)],
)
async def test_orchestrator_spawns_nothing_when_not_configured(monkeypatch, orch_logger, ctx, restart):
    run = _Runner(monkeypatch)
    await sync_orchestrator.SyncOrchestrator()._restart_systemd_service(ctx, "n1", restart)
    assert run.calls == 0


def _action_request(category="restart"):
    return roles.ExecuteActionRequest(role_name="r", category=category)


@pytest.fixture
def roles_role(monkeypatch):
    role = SimpleNamespace(systemd_service=["a.service", "b.service"], post_sync_cmd="echo hi")

    async def _resolve(db, node_id, role_name):
        return _NODE, role

    monkeypatch.setattr(roles, "_resolve_node_and_role", _resolve)
    return role


async def _execute(category="restart"):
    return await roles.execute_node_action("n1", _action_request(category), db=None, _={})


async def test_roles_argv_has_dash_n_one_call_all_units_and_timeout_120(monkeypatch, roles_role):
    run = _Runner(monkeypatch, out=b"OUT", err=b"ERR")
    body = await _execute()
    assert run.argv == [*_FULL_SSH_PREFIX, "sudo -n systemctl restart -- a.service b.service"]
    assert run.kwargs == {"stdout": asyncio.subprocess.PIPE, "stderr": asyncio.subprocess.PIPE}
    assert run.timeout == 120.0
    assert body == {"success": True, "node_id": "n1", "role_name": "r", "category": "restart", "output": "OUTERR"}


@pytest.mark.parametrize(
    ("kwargs", "success", "output"),
    [
        ({"rc": 1, "out": b"o", "err": b"e"}, False, "oe"),
        ({"rc": 1, "out": b"x" * 3000}, False, "x" * 2000),
        ({"timeout": True}, False, "Timeout after 120 seconds"),
        ({"spawn_error": OSError("boom")}, False, "Error: SSH command failed"),
    ],
)
async def test_roles_reports_each_failure_to_the_user(monkeypatch, roles_role, kwargs, success, output):
    _Runner(monkeypatch, **kwargs)
    body = await _execute()
    assert (body["success"], body["output"]) == (success, output)


async def test_roles_restart_without_units_is_422_and_the_other_category_is_untouched(monkeypatch, roles_role):
    run = _Runner(monkeypatch)
    await _execute("build")
    assert run.argv == [*_FULL_SSH_PREFIX, "echo hi"]
    roles_role.systemd_service = []
    with pytest.raises(roles.HTTPException) as exc:
        await _execute()
    assert exc.value.status_code == 422


async def test_service_restart_argv_has_dash_n_one_unit_per_call_and_the_env_timeout(monkeypatch):
    run = _Runner(monkeypatch, out=b"o", err=b"e")
    result = await service_restart.run_ansible_service_action(_NODE, "x.service", "stop")
    assert run.argv == [*_FULL_SSH_PREFIX, "sudo -n systemctl stop -- x.service"]
    assert run.kwargs == {"stdout": asyncio.subprocess.PIPE, "stderr": asyncio.subprocess.PIPE}
    assert run.timeout == service_restart._RESTART_SSH_TIMEOUT_SECONDS
    assert result == (True, "Service x.service stop completed")


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"rc": 1, "err": b"bad"}, (False, "Failed to restart service: bad")),
        ({"timeout": True}, (False, "Timeout waiting for restart to complete")),
        ({"spawn_error": OSError("boom")}, (False, "Service action failed")),
    ],
)
async def test_service_restart_returns_each_failure_as_a_tuple(monkeypatch, kwargs, expected):
    _Runner(monkeypatch, **kwargs)
    assert await service_restart.run_ansible_service_action(_NODE, "x.service", "restart") == expected
