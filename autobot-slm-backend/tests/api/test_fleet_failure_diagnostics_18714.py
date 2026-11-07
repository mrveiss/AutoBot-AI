# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A failed fleet start/stop/restart carries the node's ``systemctl status`` and journal (#18714).

The retired ``manage-service.yml`` rescue block returned both; the canonical SSH path returned a
200-character stderr slice. ``fetch_failure_diagnostics`` restores them through the same SSH
helper, unit validation and quoting the action uses, and the fleet response carries them.
"""

from __future__ import annotations

import asyncio
import secrets
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from testkit.fake_async_session import FakeAsyncSession

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _real_auth_import import load_real_auth  # noqa: E402
from _real_orm_import import SLM_ROOT, import_modules_with_real_orm  # noqa: E402

_auth = load_real_auth(secrets.token_hex(32))


async def _real_get_db():
    yield None


_fake_db = types.ModuleType("services.database")
_fake_db.get_db = _real_get_db
_fake_db.db_service = None

with patch.dict(sys.modules, {"services.auth": _auth, "services.database": _fake_db}):
    (_services_api,) = import_modules_with_real_orm(import_names=("api.services",))
(_restart,) = import_modules_with_real_orm(
    (), path_loaded={"services.service_restart": SLM_ROOT / "services" / "service_restart.py"}
)

_NODE = SimpleNamespace(ssh_user="svc", ssh_port=22, ip_address="node.example.test", hostname="n1", node_id="n1")
_UNIT = "redis-stack.service"


class _Proc:
    def __init__(self, rc: int, out: bytes, err: bytes = b"") -> None:
        self.returncode = rc
        self._io = (out, err)

    async def communicate(self):
        return self._io


class _Spawn:
    """Stands in for asyncio.create_subprocess_exec; scripts one outcome per remote command."""

    def __init__(self, monkeypatch, fail_status=False, fail_journal=False):
        self.remote: list[str] = []
        self.fail_status, self.fail_journal = fail_status, fail_journal
        monkeypatch.setattr(asyncio, "create_subprocess_exec", self)

    async def __call__(self, *argv, **_kw):
        self.remote.append(argv[-1])
        if "systemctl status" in argv[-1]:
            if self.fail_status:
                raise OSError("ssh spawn failed")
            return _Proc(3, b"STATUS-OUT")
        if self.fail_journal:
            return _Proc(1, b"", b"journal denied")
        return _Proc(0, b"JOURNAL-OUT")


async def test_diagnostics_run_status_and_journal_with_the_quoted_unit(monkeypatch):
    spawn = _Spawn(monkeypatch)
    text = await _restart.fetch_failure_diagnostics(_NODE, _UNIT)
    assert spawn.remote == [
        f"sudo -n systemctl status --no-pager -- {_UNIT}",
        f"sudo -n journalctl -u {_UNIT} -n {_restart._FAILURE_DIAG_JOURNAL_LINES} --no-pager",
    ]
    assert "STATUS-OUT" in text and "JOURNAL-OUT" in text


async def test_a_unit_that_is_not_allowlisted_runs_no_command(monkeypatch):
    spawn = _Spawn(monkeypatch)
    text = await _restart.fetch_failure_diagnostics(_NODE, "x;rm -rf ~")
    assert spawn.remote == []
    assert text.count("unavailable") == 2


async def test_a_failed_status_fetch_is_logged_and_does_not_hide_the_journal(monkeypatch, caplog):
    _Spawn(monkeypatch, fail_status=True)
    text = await _restart.fetch_failure_diagnostics(_NODE, _UNIT)
    assert "unavailable: OSError" in text and "JOURNAL-OUT" in text
    assert "Failure diagnostics (systemctl status)" in caplog.text


async def test_a_failed_journal_fetch_is_named_in_the_text(monkeypatch):
    _Spawn(monkeypatch, fail_journal=True)
    text = await _restart.fetch_failure_diagnostics(_NODE, _UNIT)
    assert "STATUS-OUT" in text and "journal denied" in text


async def test_each_section_is_bounded(monkeypatch):
    _Spawn(monkeypatch)
    monkeypatch.setattr(_restart, "_FAILURE_DIAG_MAX_CHARS", 5)
    monkeypatch.setattr(_restart, "_diagnostic_status", AsyncMock(return_value="x" * 100))
    text = await _restart.fetch_failure_diagnostics(_NODE, _UNIT)
    assert "xxxxxx" not in text


def _fake_db() -> FakeAsyncSession:
    return FakeAsyncSession(
        results=[
            [SimpleNamespace(service_name=_UNIT, node_id="n1"), SimpleNamespace(service_name=_UNIT, node_id="n2")],
            [SimpleNamespace(node_id="n1", hostname="a"), SimpleNamespace(node_id="n2", hostname="b")],
        ]
    )


@pytest.fixture
def fleet(monkeypatch):
    action = AsyncMock(side_effect=[(True, "ok"), (False, "Failed to restart service: boom")])
    diag = AsyncMock(return_value="DIAG")
    monkeypatch.setattr(_services_api, "run_ansible_service_action", action)
    monkeypatch.setattr(_services_api, "fetch_failure_diagnostics", diag)
    monkeypatch.setattr(_services_api, "ws_manager", AsyncMock())
    return SimpleNamespace(action=action, diag=diag, ws=_services_api.ws_manager)


async def test_a_failed_node_carries_its_diagnostics_and_the_original_error(fleet):
    response = await _services_api._run_fleet_action(_fake_db(), _UNIT, "restart")
    assert (response.success, response.message) == (False, "Restarted on 1/2 nodes")
    assert response.diagnostics == {"n2": "DIAG"}
    fleet.diag.assert_awaited_once()
    assert fleet.diag.await_args.args[1:] == (_UNIT,)
    failed = [c for c in fleet.ws.send_service_status.await_args_list if not c.kwargs["success"]]
    assert failed[0].kwargs["message"] == "Failed to restart service: boom"


async def test_success_everywhere_makes_no_diagnostics_call(fleet):
    fleet.action.side_effect = [(True, "ok"), (True, "ok")]
    response = await _services_api._run_fleet_action(_fake_db(), _UNIT, "start")
    assert response.success is True and response.diagnostics is None
    fleet.diag.assert_not_awaited()
