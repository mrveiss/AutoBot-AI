# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""GET /code-sync/update-all/nodes-offline over HTTP: gated, and it answers for now, not just for the log (#20250)."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import fastapi
from fastapi.testclient import TestClient

from autobot_shared.auth.permissions import Permission

_BACKEND = Path(__file__).resolve().parents[2]
_URL = "/code-sync/update-all/nodes-offline"
_STAMP = "2026-11-02T10:00:00Z"


def _load(name: str, module_stubs: dict) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, _BACKEND / Path(*name.split(".")).with_suffix(".py"))
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {name: module, **module_stubs}):
        spec.loader.exec_module(module)
    return module


def _client(log: Path, online: int) -> tuple[TestClient, list]:
    """The route on a real app; a request carrying no admin header gets the 403 the real gate gives."""
    gated: list = []

    def require_permission(permission):
        gated.append(permission)

        def gate(request: fastapi.Request) -> dict:
            if request.headers.get("x-admin") != "yes":
                raise fastapi.HTTPException(status_code=403)
            return {"sub": "admin"}

        return gate

    reader = _load("services.self_update_log_reader", {})
    db = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(scalar=lambda: online)))

    async def get_db():
        yield db

    module = _load(
        "api.update_report",
        {
            "services.auth": SimpleNamespace(require_permission=require_permission),
            "services.database": SimpleNamespace(get_db=get_db),
            "services.playbook_executor": SimpleNamespace(SELF_UPDATE_LOG_PATH=log),
            "services.self_update_log_reader": reader,
            "services.update_report": MagicMock(),
            "models.database": MagicMock(),
            "sqlalchemy": MagicMock(),
            "sqlalchemy.ext.asyncio": SimpleNamespace(AsyncSession=object),
        },
    )
    app = fastapi.FastAPI()
    app.include_router(module.router, prefix="/code-sync")
    return TestClient(app), gated


def _log(tmp_path: Path, *lines: str) -> Path:
    log = tmp_path / "self-update.log"
    log.write_text("\n".join(lines), encoding="utf-8")
    return log


def _offline_log(tmp_path: Path, stamped: bool = True) -> Path:
    start = [f"SELF-UPDATE RUN STARTED {_STAMP}"] if stamped else []
    marker = 'ok: [h] => {"msg": "NODES OFFLINE AFTER UPDATE: 2 of 3"}'
    return _log(tmp_path, *start, "PLAY [one] ****", marker, "PLAY RECAP ****", "h : ok=1 failed=0 unreachable=0")


def _get(client: TestClient) -> dict:
    response = client.get(_URL, headers={"x-admin": "yes"})
    assert response.status_code == 200
    return response.json()


def test_it_needs_the_admin_permission(tmp_path) -> None:
    client, gated = _client(_offline_log(tmp_path), online=1)
    assert client.get(_URL).status_code == 403
    assert Permission.ADMIN_SYSTEM in gated


def test_a_missing_log_reports_nothing(tmp_path) -> None:
    client, _ = _client(tmp_path / "absent.log", online=0)
    assert _get(client) == {"nodes_offline": 0, "nodes_total": 0, "run_started_at": ""}


def test_it_says_when_the_update_ran_and_how_many_are_still_down(tmp_path) -> None:
    client, _ = _client(_offline_log(tmp_path), online=2)
    assert _get(client) == {"nodes_offline": 1, "nodes_total": 3, "run_started_at": _STAMP}


def test_nodes_that_came_back_end_the_report(tmp_path) -> None:
    client, _ = _client(_offline_log(tmp_path), online=3)
    assert _get(client)["nodes_offline"] == 0


def test_a_report_with_no_date_isnt_shown(tmp_path) -> None:
    client, _ = _client(_offline_log(tmp_path, stamped=False), online=0)
    assert _get(client)["nodes_offline"] == 0
