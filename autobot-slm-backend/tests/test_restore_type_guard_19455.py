# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Only a Redis backup may enter the restore path (#19455).

The restore stops Redis and replaces its ``dump.rdb`` with the artifact. It never read
``service_type``, so restoring a PostgreSQL dump or a secrets snapshot destroyed the Redis
data and restored nothing, one click away in the GUI. The route refuses before the job
starts, and the service refuses before Redis is touched.
"""

from __future__ import annotations

import ast
import importlib.util
import logging
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from testkit.fake_async_session import FakeAsyncSession

pytestmark = pytest.mark.asyncio

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, rel: str):
    for extra in (str(ROOT), str(ROOT.parent)):
        if extra not in sys.path:
            sys.path.insert(0, extra)
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# The harness hands out a MagicMock for models.database, whose every attribute is truthy, so the
# guard is only measured against the real enums.
ENUMS = _load("_real_status_enums_19455", "status_enums.py")


def _row(service_type: str, status: str = "completed"):
    return SimpleNamespace(
        backup_id="bk1", node_id="n1", service_type=service_type, status=status, backup_path="/x", extra_data={}
    )


@pytest.mark.parametrize("value", ["redis", "REDIS", " redis "])
def test_a_redis_backup_is_restorable(value):
    assert ENUMS.BackupServiceType.is_restorable(value)


@pytest.mark.parametrize("value", ["postgres", "postgresql", "secrets", "", "bogus"])
def test_any_other_stored_type_is_not_restorable(value):
    assert not ENUMS.BackupServiceType.is_restorable(value)


@pytest.fixture()
def service(monkeypatch):
    try:
        backup = _load("_real_backup_19455", "services/backup.py")
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"services/backup.py not importable here: {exc}")
    monkeypatch.setattr(backup, "BackupServiceType", ENUMS.BackupServiceType)
    monkeypatch.setattr(backup, "BackupStatus", ENUMS.BackupStatus)
    svc = backup.BackupService.__new__(backup.BackupService)
    calls: list[str] = []

    async def _stop(*_a):
        calls.append("stop")

    async def _ok(*_a):
        calls.append("step")
        return True, ""

    svc._stop_redis_for_restore = _stop
    svc._verify_remote_backup_exists = _ok
    svc._start_and_verify_redis = _ok
    return svc, calls


@pytest.mark.parametrize("service_type", ["postgres", "secrets"])
async def test_the_service_never_touches_redis_for_another_type(service, service_type):
    svc, calls = service
    node = SimpleNamespace(ip_address="192.0.2.10", ssh_user="autobot", ssh_port=22)
    ok, message = await svc.execute_restore(FakeAsyncSession(default_result=[_row(service_type)]), "bk1", node)
    assert not ok and service_type in message
    assert calls == [], "a non-Redis backup reached the Redis stop/copy steps"


async def test_contrast_a_redis_backup_still_restores(service):
    svc, calls = service
    node = SimpleNamespace(ip_address="192.0.2.10", ssh_user="autobot", ssh_port=22)
    ok, _ = await svc.execute_restore(FakeAsyncSession(default_result=[_row("redis")]), "bk1", node)
    assert ok and calls[0] == "stop"


def _real_restore_route(started: list):
    """Compile api/stateful.py's own ``restore_backup`` (the module itself needs the full app)."""
    tree = ast.parse((ROOT / "api" / "stateful.py").read_text(encoding="utf-8"))
    fn = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "restore_backup")
    fn.decorator_list = []
    for arg in fn.args.args:
        arg.annotation = None
    fn.returns = None
    scope = {
        "select": lambda *a: SimpleNamespace(where=lambda *a: None),
        "Backup": SimpleNamespace(backup_id=None),
        "BackupStatus": ENUMS.BackupStatus,
        "BackupServiceType": ENUMS.BackupServiceType,
        "HTTPException": HTTPException,
        "status": SimpleNamespace(HTTP_404_NOT_FOUND=404, HTTP_400_BAD_REQUEST=400),
        "uuid": __import__("uuid"),
        "fire_and_forget": lambda coro, **_: (started.append(coro), coro.close()),
        "_run_restore": lambda *a: _noop(),
        "logger": logging.getLogger("stateful-restore-test"),
        "BackupRestoreResponse": lambda **kw: SimpleNamespace(**kw),
    }
    exec(compile(ast.Module([fn], []), "stateful_restore_backup", "exec"), scope)
    return scope["restore_backup"]


async def _noop():
    return None


@pytest.mark.parametrize("service_type", ["postgres", "secrets"])
async def test_the_route_refuses_another_type_before_any_job(service_type):
    started: list = []
    route = _real_restore_route(started)
    with pytest.raises(HTTPException) as exc:
        await route(backup_id="bk1", db=FakeAsyncSession(default_result=[_row(service_type)]), _={})
    assert exc.value.status_code == 400 and service_type in exc.value.detail
    assert started == []


async def test_contrast_the_route_starts_a_redis_restore():
    started: list = []
    route = _real_restore_route(started)
    result = await route(backup_id="bk1", db=FakeAsyncSession(default_result=[_row("redis")]), _={})
    assert result.success and len(started) == 1


def test_the_response_tells_the_gui_where_restore_is_offered():
    """The GUI shows Restore only where ``restorable`` is true (BackupsView.vue)."""
    schemas = (ROOT / "models" / "schemas.py").read_text(encoding="utf-8")
    assert "def restorable(self) -> bool:\n        return BackupServiceType.is_restorable(self.service_type)" in schemas
    view = (ROOT.parent / "autobot-slm-frontend" / "src" / "views" / "BackupsView.vue").read_text(encoding="utf-8")
    assert "v-if=\"backup.status === 'completed' && backup.restorable\"" in view
