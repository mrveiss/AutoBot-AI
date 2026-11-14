# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The backend's read of one secrets-backup record is behind the internal-key gate (#18281).

Uses the REAL ``require_service_management_or_internal`` (loaded from its own file, since the
harness stubs ``services.auth``), mounted exactly as ``main.py`` mounts the router.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from testkit.fake_async_session import FakeAsyncSession

ROOT = Path(__file__).resolve().parents[1]
KEY = "k" * 64


def _load(name: str, rel: str):
    for extra in (str(ROOT), str(ROOT.parent)):
        if extra not in sys.path:
            sys.path.insert(0, extra)
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def client_for(monkeypatch):
    from fastapi import Depends, FastAPI
    from fastapi.testclient import TestClient

    enums = _load("_real_status_enums_18281b", "status_enums.py")
    db_module = sys.modules.get("models.database")
    if db_module is not None:
        for name in ("BackupStatus", "BackupServiceType"):
            monkeypatch.setattr(db_module, name, getattr(enums, name), raising=False)
    try:
        auth = _load("_real_slm_auth_18281", "services/auth.py")
        route = _load("_real_status_route_18281", "api/secrets_backup_status.py")
    except Exception as exc:
        pytest.skip(f"SLM auth/route modules not importable here: {exc}")

    def make(row, integrity=None):
        async def fake_integrity(_id):
            return integrity or {"valid": True, "checksum": "abc"}

        monkeypatch.setattr(route, "backup_service", SimpleNamespace(verify_backup_integrity=fake_integrity))
        app = FastAPI()
        app.include_router(
            route.router, prefix="/api", dependencies=[Depends(auth.require_service_management_or_internal)]
        )
        app.dependency_overrides[route.get_db] = lambda: FakeAsyncSession(default_result=[] if row is None else [row])
        return TestClient(app)

    return make


def _row(**over):
    base = dict(
        backup_id="bk1",
        status="completed",
        service_type="secrets",
        checksum="abc",
        completed_at=datetime(2026, 10, 12, 9, 0, tzinfo=timezone.utc),
    )
    base.update(over)
    return SimpleNamespace(**base)


URL = "/api/stateful/secrets-backups/bk1"


def test_no_key_and_no_user_is_refused(client_for, monkeypatch):
    monkeypatch.setenv("AUTOBOT_INTERNAL_API_KEY", KEY)
    assert client_for(_row()).get(URL).status_code in (401, 403)


def test_a_wrong_key_is_refused(client_for, monkeypatch):
    monkeypatch.setenv("AUTOBOT_INTERNAL_API_KEY", KEY)
    assert client_for(_row()).get(URL, headers={"X-Internal-API-Key": "w" * 64}).status_code in (401, 403)


def test_the_key_unset_on_the_server_never_matches(client_for, monkeypatch):
    monkeypatch.delenv("AUTOBOT_INTERNAL_API_KEY", raising=False)
    assert client_for(_row()).get(URL, headers={"X-Internal-API-Key": ""}).status_code in (401, 403)


def test_the_key_reads_the_record(client_for, monkeypatch):
    monkeypatch.setenv("AUTOBOT_INTERNAL_API_KEY", KEY)
    response = client_for(_row()).get(URL, headers={"X-Internal-API-Key": KEY})
    assert response.status_code == 200
    assert response.json() == {
        "status": "completed",
        "service_type": "secrets",
        "completed_at": "2026-10-12T09:00:00+00:00",
        "integrity_ok": True,
    }


def test_an_unknown_backup_is_404(client_for, monkeypatch):
    monkeypatch.setenv("AUTOBOT_INTERNAL_API_KEY", KEY)
    assert client_for(None).get(URL, headers={"X-Internal-API-Key": KEY}).status_code == 404


@pytest.mark.parametrize(
    "row, integrity",
    [
        (_row(status="failed"), None),
        (_row(service_type="redis"), None),
        (_row(checksum=None), None),
        (_row(), {"valid": False, "error": "Checksum mismatch"}),
        (_row(), {"valid": True, "warning": "No stored checksum to verify against"}),
    ],
)
def test_integrity_is_false_unless_everything_holds(client_for, monkeypatch, row, integrity):
    monkeypatch.setenv("AUTOBOT_INTERNAL_API_KEY", KEY)
    body = client_for(row, integrity).get(URL, headers={"X-Internal-API-Key": KEY}).json()
    assert body["integrity_ok"] is False


def test_it_is_mounted_behind_the_internal_gate_in_main():
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    assert 'app.include_router(secrets_backup_status_router, prefix="/api", dependencies=_SM_OR_AGENT)' in source
