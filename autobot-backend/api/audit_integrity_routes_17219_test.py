# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The audit-chain routes are admin-only, and the run route is human-only (#17219)."""

import contextlib
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from api.audit import check_admin_permission, refuse_service_principal, router
from autobot_shared.audit_chain import Finding
from services.audit.integrity import IntegrityReport


def _routes() -> dict[str, APIRoute]:
    return {f"{sorted(r.methods)[0]} {r.path}": r for r in router.routes if isinstance(r, APIRoute)}


def _deps(route: APIRoute) -> set:
    return {d.call for d in route.dependant.dependencies}


def _client(admin: bool = True, service: bool = False) -> TestClient:
    def _no():
        raise HTTPException(status_code=403)

    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[check_admin_permission] = (lambda: True) if admin else _no
    app.dependency_overrides[refuse_service_principal] = _no if service else (lambda: None)
    return TestClient(app)


def _report(findings=()) -> IntegrityReport:
    return IntegrityReport(
        ok=not findings,
        checked_at=datetime(2026, 11, 22, tzinfo=timezone.utc),
        rows_checked=3,
        chain_started=True,
        head_seq=3,
        head_hash="h" * 64,
        pre_chain_count=2,
        unchained_count=2,
        findings=list(findings),
    )


@contextlib.contextmanager
def _head(seq: int = 3, last=None):
    session = MagicMock()
    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=session)
    session_cm.__aexit__ = AsyncMock(return_value=False)
    with (
        patch("api.audit.db_session_context", return_value=session_cm),
        patch("api.audit.current_head", AsyncMock(return_value=(seq, "h" * 64))),
        patch("api.audit.last_report", return_value=last),
    ):
        yield


def test_the_read_route_is_admin_gated() -> None:
    assert check_admin_permission in _deps(_routes()["GET /audit/integrity"])


def test_the_run_route_is_admin_gated_and_refuses_the_service_principal() -> None:
    deps = _deps(_routes()["POST /audit/integrity/verify"])
    assert {check_admin_permission, refuse_service_principal} <= deps


@pytest.mark.parametrize(("method", "path"), [("get", "/api/audit/integrity"), ("post", "/api/audit/integrity/verify")])
def test_a_non_admin_is_refused_on_both_routes(method: str, path: str) -> None:
    with patch("api.audit.verify_chain", AsyncMock()) as verify:
        assert getattr(_client(admin=False), method)(path).status_code == 403
    verify.assert_not_awaited()


def test_the_service_key_cannot_run_a_verification() -> None:
    with patch("api.audit.verify_chain", AsyncMock()) as verify:
        assert _client(service=True).post("/api/audit/integrity/verify").status_code == 403
    verify.assert_not_awaited()


def test_the_read_route_returns_the_head_and_no_result_before_the_first_run() -> None:
    with _head():
        body = _client().get("/api/audit/integrity").json()
    assert body == {"last_result": None, "head_seq": 3, "head_hash": "h" * 64}


def test_the_read_route_returns_the_last_result() -> None:
    with _head(last=_report([Finding("modified_row", 2, "x")])):
        body = _client().get("/api/audit/integrity").json()
    assert body["last_result"]["ok"] is False and body["last_result"]["findings"][0]["seq"] == 2


def test_the_run_route_reports_findings_and_never_locks_anything_out() -> None:
    failed = _report([Finding("removed_row", 3, "gap")])
    with patch("api.audit.verify_chain", AsyncMock(return_value=failed)) as verify:
        response = _client().post("/api/audit/integrity/verify", json={"from_seq": 2})
    verify.assert_awaited_once_with(2)
    assert response.status_code == 200 and response.json()["findings"] == [
        {"kind": "removed_row", "seq": 3, "detail": "gap"}
    ]


def test_the_run_route_defaults_to_the_genesis() -> None:
    with patch("api.audit.verify_chain", AsyncMock(return_value=_report())) as verify:
        assert _client().post("/api/audit/integrity/verify").status_code == 200
    verify.assert_awaited_once_with(None)
