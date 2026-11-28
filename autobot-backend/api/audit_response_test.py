# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression tests for #13259: POST /audit/cleanup and GET /audit/operations
dropped their payloads.

Both declared response_model=DataResponse[XData] over a flat dict return; the
fix declares the concrete flat model directly. Field-value assertions are the
regression guard -- a bare status_code == 200 check would still pass against
the bug (the envelope defaults message/timestamp to None but the request
still succeeds).
"""

import contextlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.audit import check_admin_permission, router


def _make_client() -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[check_admin_permission] = lambda: True
    return TestClient(app)


class TestCleanupOldLogsResponsePayload:
    def test_cleanup_reports_the_actual_retention_window_on_the_wire(self):
        client = _make_client()
        mock_logger = AsyncMock()

        with patch("api.audit.get_audit_logger", return_value=mock_logger):
            response = client.post(
                "/api/audit/cleanup",
                json={"days_to_keep": 45, "confirm": True},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["days_retained"] == 45
        assert "45" in body["message"]
        assert body["success"] is True
        mock_logger.cleanup_old_logs.assert_awaited_once_with(days_to_keep=45)


class TestListOperationTypesResponsePayload:
    def test_list_operation_types_returns_the_real_categories_on_the_wire(self):
        client = _make_client()

        fake_operations = {
            "auth.login": "security",
            "auth.logout": "security",
            "file.export": "data",
        }
        with patch("services.audit_logger.OPERATION_CATEGORIES", fake_operations):
            response = client.get("/api/audit/operations")

        assert response.status_code == 200
        body = response.json()
        assert sorted(body["categories"]["security"]) == ["auth.login", "auth.logout"]
        assert body["categories"]["data"] == ["file.export"]
        assert body["total_operations"] == 3


class TestAuditEntriesCarryTheActorName:
    """#22338: rows store the actor id; the response adds ``user_name`` resolved at read time."""

    def test_logs_resolve_ids_to_names_and_leave_services_and_system_as_stored(self):
        rows = [
            SimpleNamespace(to_response_dict=lambda uid=uid: {**_ROW, "user_id": uid})
            for uid in ("u-123", "service:slm", "system", None)
        ]
        audit_logger = AsyncMock()
        audit_logger.query = AsyncMock(return_value=rows)

        @contextlib.asynccontextmanager
        async def _session():
            yield MagicMock()

        with (
            patch("api.audit.get_audit_logger", return_value=audit_logger),
            patch("api.audit.db_session_context", _session),
            patch("api.audit.actor_names", AsyncMock(return_value={"u-123": "Ada Admin"})) as names,
        ):
            body = _make_client().get("/api/audit/logs").json()

        assert [e["user_name"] for e in body["entries"]] == ["Ada Admin", None, None, None]
        assert [e["user_id"] for e in body["entries"]] == ["u-123", "service:slm", "system", None]
        names.assert_awaited_once()


_ROW = {
    "id": "1",
    "timestamp": 1.0,
    "date": "d",
    "operation": "op",
    "result": "success",
    "details": {},
}


_UID = "0b1f6a52-3c3e-4f0a-9f43-6f1a2c0e9d11"


def _filter_call(path: str, user: object | None):
    """The ``user_ids`` the audit logger is queried with for *path*, with the username lookup returning *user*."""
    audit_logger = AsyncMock()
    audit_logger.query = AsyncMock(return_value=[])

    @contextlib.asynccontextmanager
    async def _session():
        yield MagicMock()

    service = MagicMock()
    service.get_user_by_username = AsyncMock(return_value=user)
    with (
        patch("api.audit.get_audit_logger", return_value=audit_logger),
        patch("api.audit.db_session_context", _session),
        patch("api.audit.UserService", return_value=service),
        patch("api.audit.actor_names", AsyncMock(return_value={})),
    ):
        assert _make_client().get(path).status_code == 200
    return audit_logger.query.await_args.kwargs["user_ids"], service


class TestUserFilterAcceptsAUsername:
    """#22338: a typed username matches the user's id and legacy username-keyed rows; an id matches only itself."""

    def test_a_username_resolves_to_the_id_and_keeps_the_raw_name(self):
        ids, _ = _filter_call("/api/audit/logs?user_id=ada", SimpleNamespace(id=_UID))
        assert ids == ["ada", _UID]

    def test_the_user_trail_route_resolves_a_username_the_same_way(self):
        ids, _ = _filter_call("/api/audit/user/ada", SimpleNamespace(id=_UID))
        assert ids == ["ada", _UID]

    def test_an_unknown_username_still_matches_the_raw_value(self):
        ids, _ = _filter_call("/api/audit/logs?user_id=ghost", None)
        assert ids == ["ghost"]

    def test_an_id_queries_as_is_without_a_username_lookup(self):
        ids, service = _filter_call(f"/api/audit/logs?user_id={_UID}", SimpleNamespace(id="other"))
        assert ids == [_UID]
        service.get_user_by_username.assert_not_awaited()

    def test_no_filter_sends_no_actor_constraint(self):
        ids, _ = _filter_call("/api/audit/logs", None)
        assert ids is None


class TestActorIdsFilterMatchesBothRowKinds:
    def test_the_resolved_set_matches_new_and_legacy_rows_and_an_id_only_its_own(self):
        from services.audit.taxonomy import AuditFilter

        new_row, legacy_row = {"actor_id": _UID}, {"actor_id": "ada"}
        both = AuditFilter(actor_ids=frozenset({"ada", _UID}))
        only_id = AuditFilter(actor_ids=frozenset({_UID}))
        assert both.matches(new_row) and both.matches(legacy_row)
        assert only_id.matches(new_row) and not only_id.matches(legacy_row)

    def test_the_store_filters_on_the_actor_set(self):
        from services.audit import store
        from services.audit.taxonomy import AuditFilter

        clauses = store.where_clauses(AuditFilter(actor_ids=frozenset({"ada", _UID})))
        assert any("IN" in str(c) for c in clauses)
