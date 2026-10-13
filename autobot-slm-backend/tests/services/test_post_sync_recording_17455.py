# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Each post-sync command and restart a sync executes leaves a redacted row (#17455)."""

from __future__ import annotations

import asyncio
import importlib
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))
_orm = importlib.import_module("_real_orm_import")  # a sibling helper in tests/api, not on the package path
SLM_ROOT = _orm.SLM_ROOT

service_restart, recorder, runner, plan_runner = _orm.import_modules_with_real_orm(
    ("services.post_sync_recorder", "services.post_sync_runner", "services.post_sync_plan_runner"),
    path_loaded={
        "services.service_restart": SLM_ROOT / "services" / "service_restart.py",
    },
)

_REC = recorder.RunContext("run1", "n1", "autobot-backend")
_NOW = datetime(2026, 10, 11, tzinfo=timezone.utc)


def _outcome(**kw):
    base = dict(success=True, exit_code=0, output_tail="", error=None, started_at=_NOW, finished_at=_NOW)
    return recorder.ActionOutcome(**{**base, **kw})


def test_row_content_is_redacted_and_complete():
    out = _outcome(success=False, exit_code=1, output_tail="x" * 900 + " api_key=hunter2", error="token=abc123")
    row = recorder.build_row(
        _REC, "post_sync", "Post-sync command", "curl -H 'Authorization: Bearer s3cr3t'", None, out
    )
    assert (row.run_id, row.node_id, row.role_name, row.category) == ("run1", "n1", "autobot-backend", "post_sync")
    assert (row.exit_code, row.success, row.started_at, row.finished_at) == (1, False, _NOW, _NOW)
    assert "s3cr3t" not in row.command
    assert "hunter2" not in row.output_tail and len(row.output_tail) <= 800
    assert "abc123" not in row.error


async def test_recording_never_fails_the_sync(monkeypatch):
    broken = MagicMock()
    broken.session.side_effect = RuntimeError("db down")
    monkeypatch.setattr(recorder, "db_service", broken)
    await recorder.record_action_run(_REC, "restart", "Restart a", "cmd", "a", _outcome())  # must not raise


class _Proc:
    def __init__(self, rc, out):
        self.returncode, self._out = rc, out

    async def communicate(self):
        return self._out, b""


def _fake_ssh(monkeypatch, rc=0, out=b""):
    async def _spawn(*argv, **kwargs):
        return _Proc(rc, out)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _spawn)


@pytest.fixture
def recorded(monkeypatch):
    mock = AsyncMock()
    monkeypatch.setattr(runner, "record_action_run", mock)
    return mock


def _base():
    return runner.restart_ssh_base("node.example.test", "svc", 22)


async def test_a_failed_restart_is_recorded(monkeypatch, recorded):
    _fake_ssh(monkeypatch, rc=1, out=b"Failed to restart a.service")
    outcome = await runner.restart_units(_base(), ["a.service"], _REC)
    (rec, category, label, command, units, recorded_outcome), _ = recorded.call_args
    assert (category, label, units) == ("restart", "Restart a.service", "a.service")
    assert command == "sudo -n systemctl restart -- a.service"
    assert (recorded_outcome.success, recorded_outcome.exit_code) == (False, 1)
    assert outcome.success is False


async def test_a_failed_post_sync_command_is_recorded_and_reported(monkeypatch, recorded):
    _fake_ssh(monkeypatch, rc=2, out=b"pip: no matching distribution")
    outcome = await runner.run_post_sync_command(_base(), "pip install x", 5, _REC, "Install deps", "install")
    assert (outcome.success, outcome.exit_code) == (False, 2)
    assert "no matching distribution" in outcome.output_tail
    args = recorded.call_args.args
    assert (args[1], args[2], args[3]) == ("install", "Install deps", "pip install x")


async def test_without_a_run_context_nothing_is_recorded(monkeypatch, recorded):
    _fake_ssh(monkeypatch)
    assert (await runner.restart_units(_base(), ["a.service"])).success
    recorded.assert_not_called()


async def test_a_deferred_self_restart_that_is_refused_records_a_failure_not_an_endless_issued(monkeypatch, recorded):
    """#17455: if `sudo -n` refuses the self-restart the process survives; the row must not stay "issued"."""
    _fake_ssh(monkeypatch, rc=1, out=b"sudo: a password is required")
    action = SimpleNamespace(role_name="r", systemd_service="autobot-slm-backend")
    conn = plan_runner.NodeConn("n1", "node.example.test", "svc", 22)
    await plan_runner.issue_deferred([plan_runner.DeferredRestart(action, conn, _REC)])
    outcome = recorded.call_args.args[5]
    assert (outcome.success, outcome.exit_code) == (False, 1)
    assert "password is required" in outcome.output_tail


async def test_the_issued_row_is_success_unknown_and_written_for_every_deferred_restart(monkeypatch):
    mock = AsyncMock(return_value={"label": "x"})
    monkeypatch.setattr(plan_runner, "record_action_run", mock)
    action = SimpleNamespace(role_name="r", systemd_service="autobot-slm-backend")
    conn = plan_runner.NodeConn("n1", "node.example.test", "svc", 22)
    result = plan_runner.PlanResult(deferred=[plan_runner.DeferredRestart(action, conn, _REC)])
    await plan_runner.record_issued(result)
    out = mock.call_args.args[5]
    assert (out.success, out.exit_code) == (None, None) and "issued" in out.error
    assert result.rows == [{"label": "x"}]


@pytest.mark.parametrize("bad", ["a.service; reboot", "$(id).service", "-oProxyCommand=x", "a b.service"])
async def test_an_invalid_unit_is_recorded_as_a_failure_and_nothing_is_spawned_18359(monkeypatch, recorded, bad):
    """Decision 3: a role unit failing `validate_unit_name` is a recorded failure, never run, never silent."""
    spawned = []

    async def _spawn(*argv, **kwargs):
        spawned.append(argv)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _spawn)
    outcome = await runner.restart_units(_base(), [bad], _REC)
    assert outcome.success is False and "invalid systemd unit name" in outcome.error
    assert spawned == []
    args = recorded.call_args.args
    assert args[1] == "restart" and args[3] == "systemctl restart (rejected: invalid unit name)"
    assert args[5].success is False


def test_an_invalid_unit_is_never_deferred_as_an_issued_self_restart_18359():
    action = SimpleNamespace(category="restart", systemd_service="slm-backend; reboot")
    assert plan_runner._is_deferred(action, ["slm-backend;", "reboot"]) is False
