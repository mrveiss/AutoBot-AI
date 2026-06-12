# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for BacklogService.bulk_reorder and POST /companies/{id}/backlog/reorder (GH#9861)."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from llc.services.backlog import BacklogService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session(owned_ids=None, rowcount=1):
    """Return a mocked AsyncSession for BacklogService tests."""
    session = AsyncMock()
    session.flush = AsyncMock()

    # execute() returns an object whose .all() returns owned_id rows
    owned_rows = [(oid,) for oid in (owned_ids or [])]
    exec_result = MagicMock()
    exec_result.all.return_value = owned_rows
    session.execute = AsyncMock(return_value=exec_result)
    return session


# ---------------------------------------------------------------------------
# Service-level unit tests
# ---------------------------------------------------------------------------


class TestBulkReorderService:
    @pytest.fixture
    def svc(self):
        return BacklogService()

    async def test_empty_list_returns_zero(self, svc):
        session = _make_session()
        result = await svc.bulk_reorder(session, company_id=str(uuid.uuid4()), ordered_ids=[])
        assert result == {"updated": 0, "unknown_count": 0}
        session.execute.assert_not_called()

    async def test_all_owned_returns_updated_count(self, svc):
        ids = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]
        str_ids = [str(i) for i in ids]
        session = _make_session(owned_ids=ids)
        result = await svc.bulk_reorder(session, company_id=str(uuid.uuid4()), ordered_ids=str_ids)
        assert result["updated"] == 3
        assert result["unknown_count"] == 0

    async def test_cross_tenant_ids_excluded(self, svc):
        owned_id = uuid.uuid4()
        other_id = uuid.uuid4()
        # Only the first id is "owned" by this company
        session = _make_session(owned_ids=[owned_id])
        result = await svc.bulk_reorder(
            session,
            company_id=str(uuid.uuid4()),
            ordered_ids=[str(owned_id), str(other_id)],
        )
        assert result["updated"] == 1
        assert result["unknown_count"] == 1

    async def test_positions_assigned_in_order(self, svc):
        ids = [uuid.uuid4(), uuid.uuid4()]
        session = _make_session(owned_ids=ids)
        await svc.bulk_reorder(session, company_id=str(uuid.uuid4()), ordered_ids=[str(i) for i in ids])
        # The ownership SELECT + 2 UPDATE calls = 3 execute() calls total
        assert session.execute.call_count == 3

    async def test_flush_called_when_items_updated(self, svc):
        item_id = uuid.uuid4()
        session = _make_session(owned_ids=[item_id])
        await svc.bulk_reorder(session, company_id=str(uuid.uuid4()), ordered_ids=[str(item_id)])
        session.flush.assert_called_once()

    async def test_no_flush_when_zero_updates(self, svc):
        """If all ids are cross-tenant, flush must not be called."""
        session = _make_session(owned_ids=[])  # nothing owned
        await svc.bulk_reorder(
            session,
            company_id=str(uuid.uuid4()),
            ordered_ids=[str(uuid.uuid4())],
        )
        session.flush.assert_not_called()


# ---------------------------------------------------------------------------
# Route-level tests via FastAPI TestClient
# ---------------------------------------------------------------------------


class TestBacklogReorderRoute:
    def _client(self, svc_result=None):
        from unittest.mock import AsyncMock, patch

        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from llc.api.companies import router as companies_router
        from llc.deps import get_session

        app = FastAPI()
        # companies_router already carries prefix="/companies"; mount at root.
        app.include_router(companies_router)

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()

        _result = svc_result or {"updated": 2, "unknown_count": 0}

        async def _fake_session():
            yield mock_session

        app.dependency_overrides[get_session] = _fake_session

        patcher = patch(
            "llc.services.backlog.BacklogService.bulk_reorder",
            new=AsyncMock(return_value=_result),
        )
        patcher.start()
        client = TestClient(app, raise_server_exceptions=True)
        return client, patcher

    def test_missing_body_returns_422(self):
        client, patcher = self._client()
        try:
            company_id = str(uuid.uuid4())
            resp = client.post(f"/companies/{company_id}/backlog/reorder", json={})
            assert resp.status_code == 422
        finally:
            patcher.stop()

    def test_empty_ids_returns_422(self):
        client, patcher = self._client()
        try:
            company_id = str(uuid.uuid4())
            resp = client.post(
                f"/companies/{company_id}/backlog/reorder",
                json={"work_item_ids": []},
            )
            assert resp.status_code == 422
        finally:
            patcher.stop()

    def test_happy_path_returns_200(self):
        client, patcher = self._client(svc_result={"updated": 3, "unknown_count": 0})
        try:
            company_id = str(uuid.uuid4())
            ids = [str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())]
            resp = client.post(
                f"/companies/{company_id}/backlog/reorder",
                json={"work_item_ids": ids},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["updated"] == 3
            assert body["unknown_count"] == 0
        finally:
            patcher.stop()

    def test_cross_tenant_count_in_response(self):
        client, patcher = self._client(svc_result={"updated": 1, "unknown_count": 2})
        try:
            company_id = str(uuid.uuid4())
            ids = [str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())]
            resp = client.post(
                f"/companies/{company_id}/backlog/reorder",
                json={"work_item_ids": ids},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["unknown_count"] == 2
        finally:
            patcher.stop()
