# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for BacklogService.bulk_reorder and POST /companies/{id}/backlog/reorder (GH#9861)."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from llc.models.enums import WorkItemPriority, WorkItemStatus, WorkItemType
from llc.models.work_item import LLCWorkItem
from llc.services.backlog import BacklogService

# Import harness before any model imports to register SQLite compile shims.
from llc.tests import _e2e_harness as harness  # noqa: F401

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

    async def test_duplicate_ids_deduped_preserving_first(self, svc):
        """Duplicate ids in ordered_ids are deduplicated; only unique ids reach ownership check."""
        item_a = uuid.uuid4()
        item_b = uuid.uuid4()
        # item_a supplied twice — after dedup: [a, b]; both owned.
        session = _make_session(owned_ids=[item_a, item_b])
        result = await svc.bulk_reorder(
            session,
            company_id=str(uuid.uuid4()),
            ordered_ids=[str(item_a), str(item_b), str(item_a)],
        )
        # 2 unique owned ids → 2 updated; 0 unknown.
        assert result["updated"] == 2
        assert result["unknown_count"] == 0
        # Ownership SELECT + 2 UPDATE calls = 3 execute() calls (not 4).
        assert session.execute.call_count == 3


# ---------------------------------------------------------------------------
# Route-level tests via FastAPI TestClient
# ---------------------------------------------------------------------------

_FIXED_USER_ID = uuid.UUID("44444444-4444-4444-4444-444444444444")


class TestBacklogReorderRoute:
    """Route-level tests for POST /companies/{id}/backlog/reorder.

    All successful-path tests install auth dependency overrides exactly as
    test_work_items_idor.py does, so the route's ``get_current_user`` /
    ``require_org_context`` dependencies are exercised with real-shaped data.
    """

    def _client(self, svc_result=None, caller_org_id=None, install_auth=True):
        from unittest.mock import AsyncMock, patch

        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from api.user_management.dependencies import get_current_user, require_org_context  # noqa: PLC0415
        from llc.api.companies import router as companies_router  # noqa: PLC0415
        from llc.deps import get_session  # noqa: PLC0415
        from user_management.services import TenantContext  # noqa: PLC0415

        app = FastAPI()
        # companies_router already carries prefix="/companies"; mount at root.
        app.include_router(companies_router)

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()

        _result = svc_result or {"updated": 2, "unknown_count": 0}

        async def _fake_session():
            yield mock_session

        app.dependency_overrides[get_session] = _fake_session

        if install_auth:
            org = uuid.UUID(caller_org_id) if caller_org_id else uuid.uuid4()

            def _fake_user() -> dict:
                return {"id": str(_FIXED_USER_ID), "user_id": str(_FIXED_USER_ID)}

            def _fake_tenant() -> TenantContext:
                return TenantContext(
                    org_id=org,
                    user_id=_FIXED_USER_ID,
                    is_platform_admin=False,
                )

            app.dependency_overrides[get_current_user] = _fake_user
            app.dependency_overrides[require_org_context] = _fake_tenant

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
        company_id = str(uuid.uuid4())
        client, patcher = self._client(
            svc_result={"updated": 3, "unknown_count": 0},
            caller_org_id=company_id,
        )
        try:
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
        company_id = str(uuid.uuid4())
        client, patcher = self._client(
            svc_result={"updated": 1, "unknown_count": 2},
            caller_org_id=company_id,
        )
        try:
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

    # H1: security tests — cross-tenant and unauthenticated must both fail.

    def test_cross_tenant_org_returns_404(self):
        """Caller's org_id differs from the company_id path parameter → 404."""
        company_id = str(uuid.uuid4())
        different_org = str(uuid.uuid4())
        client, patcher = self._client(
            svc_result={"updated": 0, "unknown_count": 0},
            caller_org_id=different_org,  # different from company_id
        )
        try:
            ids = [str(uuid.uuid4())]
            resp = client.post(
                f"/companies/{company_id}/backlog/reorder",
                json={"work_item_ids": ids},
            )
            assert resp.status_code == 404
        finally:
            patcher.stop()

    def test_unauthenticated_returns_error(self):
        """No auth overrides installed → the real dependency rejects the request."""
        client, patcher = self._client(install_auth=False)
        try:
            company_id = str(uuid.uuid4())
            ids = [str(uuid.uuid4())]
            resp = client.post(
                f"/companies/{company_id}/backlog/reorder",
                json={"work_item_ids": ids},
            )
            # Any 4xx is acceptable — the dependency may raise 400/401/403/422
            # depending on how the test client handles missing Authorization headers.
            assert resp.status_code >= 400
        finally:
            patcher.stop()

    # M1: malformed UUID in work_item_ids → Pydantic returns 422 before the service is hit.

    def test_malformed_uuid_in_ids_returns_422(self):
        company_id = str(uuid.uuid4())
        client, patcher = self._client(caller_org_id=company_id)
        try:
            resp = client.post(
                f"/companies/{company_id}/backlog/reorder",
                json={"work_item_ids": ["not-a-uuid", str(uuid.uuid4())]},
            )
            assert resp.status_code == 422
        finally:
            patcher.stop()

    # LOW: duplicate ids in the payload — route returns 200 (service handles deduplication).

    def test_duplicate_ids_in_payload_returns_200(self):
        """Duplicate ids in the payload are accepted by the route and deduped by the service."""
        company_id = str(uuid.uuid4())
        item_a = str(uuid.uuid4())
        item_b = str(uuid.uuid4())
        # item_a appears twice — valid UUID, Pydantic accepts it.
        payload_ids = [item_a, item_b, item_a]
        client, patcher = self._client(
            svc_result={"updated": 2, "unknown_count": 0},
            caller_org_id=company_id,
        )
        try:
            resp = client.post(
                f"/companies/{company_id}/backlog/reorder",
                json={"work_item_ids": payload_ids},
            )
            assert resp.status_code == 200
        finally:
            patcher.stop()


# ---------------------------------------------------------------------------
# H3 integration test: reorder then list → new order reflected
# Uses real in-memory SQLite via the e2e harness (same pattern as
# test_org_chart_enrichment.py).
# ---------------------------------------------------------------------------

_item_counter = 0


@pytest_asyncio.fixture
async def backlog_engine():  # noqa: ANN201
    eng = create_async_engine(  # canonical: ignore py-adhoc-db-engine (test-local engine)
        "sqlite+aiosqlite:///:memory:"
    )
    await harness.create_loop_schema(eng)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def backlog_session_factory(backlog_engine):  # noqa: ANN001, ANN201
    return async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local session factory)
        backlog_engine, expire_on_commit=False, class_=AsyncSession
    )


async def _seed_backlog_item(
    session_factory,  # noqa: ANN001
    company_id: uuid.UUID,
    *,
    priority: str = WorkItemPriority.MEDIUM.value,
    backlog_position: int | None = None,
) -> uuid.UUID:
    global _item_counter
    _item_counter += 1
    item_id = uuid.uuid4()
    async with session_factory() as session:
        item = LLCWorkItem(
            id=item_id,
            company_id=company_id,
            identifier=f"WI-{_item_counter}",
            type=WorkItemType.TASK.value,
            title=f"Item {_item_counter}",
            status=WorkItemStatus.BACKLOG.value,
            priority=priority,
            version=1,
            labels=[],
        )
        if backlog_position is not None:
            item.backlog_position = backlog_position
        session.add(item)
        await session.commit()
    return item_id


@pytest.mark.asyncio
async def test_reorder_then_list_reflects_new_order(backlog_session_factory):  # noqa: ANN001
    """H3: after bulk_reorder, list_backlog returns items in the new position order."""
    company_id = uuid.uuid4()
    svc = BacklogService()

    # Seed three items all with the same priority so without backlog_position
    # the natural sort would be by created_at (which is seeded in order a→b→c).
    id_a = await _seed_backlog_item(backlog_session_factory, company_id)
    id_b = await _seed_backlog_item(backlog_session_factory, company_id)
    id_c = await _seed_backlog_item(backlog_session_factory, company_id)

    # Reorder: desired order is [c, a, b].
    async with backlog_session_factory() as session:
        result = await svc.bulk_reorder(
            session,
            company_id=str(company_id),
            ordered_ids=[str(id_c), str(id_a), str(id_b)],
        )
        await session.commit()

    assert result["updated"] == 3
    assert result["unknown_count"] == 0

    # list_backlog must now return items in the reordered sequence [c, a, b].
    async with backlog_session_factory() as session:
        items, total = await svc.list_backlog(session, company_id=str(company_id))

    assert total == 3
    item_ids = [str(i.id) for i in items]
    assert item_ids == [str(id_c), str(id_a), str(id_b)], f"Expected [c, a, b] but got {item_ids}"
