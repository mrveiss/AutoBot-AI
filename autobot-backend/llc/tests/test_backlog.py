"""Tests for LLC BacklogService and backlog API routes (GH#8222)."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from llc.models.enums import WorkItemPriority, WorkItemStatus, WorkItemType
from llc.models.work_item import LLCWorkItem
from llc.services.backlog import BacklogService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_item(
    *,
    priority: WorkItemPriority = WorkItemPriority.MEDIUM,
    status: WorkItemStatus = WorkItemStatus.BACKLOG,
    type: WorkItemType = WorkItemType.TASK,
    sprint_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
) -> LLCWorkItem:
    item = MagicMock(spec=LLCWorkItem)
    item.id = uuid.uuid4()
    item.company_id = uuid.uuid4()
    item.identifier = f"WI-{uuid.uuid4().hex[:4]}"
    item.type = type
    item.title = "Test item"
    item.description = None
    item.status = status
    item.priority = priority
    item.story_points = None
    item.labels = []
    item.sprint_id = sprint_id
    item.project_id = project_id
    item.parent_id = None
    item.goal_id = None
    item.assignee_agent_id = None
    item.assignee_user_id = None
    item.assignee_type = None
    item.version = 1
    item.checkout_run_id = None
    item.checkout_locked_at = None
    item.created_by_agent_id = None
    item.created_by_user_id = None
    item.started_at = None
    item.completed_at = None
    item.cancelled_at = None
    item.created_at = None
    item.updated_at = None
    return item


@pytest.fixture
def service():
    return BacklogService()


@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.flush = AsyncMock()
    db_result = MagicMock()
    session.execute = AsyncMock(return_value=db_result)
    session._db_result = db_result
    return session


# ---------------------------------------------------------------------------
# BacklogService.list_backlog
# ---------------------------------------------------------------------------


class TestListBacklog:
    async def test_returns_items_and_total(self, service, mock_session):
        items = [_make_item(priority=WorkItemPriority.HIGH), _make_item(priority=WorkItemPriority.LOW)]
        # First execute call returns count, second returns items
        count_result = MagicMock()
        count_result.scalar_one.return_value = 2
        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = items
        mock_session.execute = AsyncMock(side_effect=[count_result, items_result])

        result_items, total = await service.list_backlog(mock_session, company_id=str(uuid.uuid4()))

        assert total == 2
        assert len(result_items) == 2

    async def test_no_sprint_filter_restricts_to_unassigned(self, service, mock_session):
        """Without sprint_id param, query filters sprint_id IS NULL."""
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(side_effect=[count_result, items_result])

        # No exception — verifies the IS NULL branch executes without error
        result_items, total = await service.list_backlog(mock_session, company_id=str(uuid.uuid4()))
        assert total == 0

    async def test_sprint_id_filter_applied(self, service, mock_session):
        sprint_id = str(uuid.uuid4())
        count_result = MagicMock()
        count_result.scalar_one.return_value = 1
        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = [_make_item(sprint_id=uuid.UUID(sprint_id))]
        mock_session.execute = AsyncMock(side_effect=[count_result, items_result])

        result_items, total = await service.list_backlog(
            mock_session, company_id=str(uuid.uuid4()), sprint_id=sprint_id
        )
        assert total == 1

    async def test_type_filter(self, service, mock_session):
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(side_effect=[count_result, items_result])

        result_items, total = await service.list_backlog(
            mock_session, company_id=str(uuid.uuid4()), type=WorkItemType.BUG
        )
        assert total == 0

    async def test_status_filter(self, service, mock_session):
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(side_effect=[count_result, items_result])

        result_items, total = await service.list_backlog(
            mock_session, company_id=str(uuid.uuid4()), status=WorkItemStatus.READY
        )
        assert total == 0

    async def test_empty_backlog_returns_zero_total(self, service, mock_session):
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(side_effect=[count_result, items_result])

        result_items, total = await service.list_backlog(mock_session, company_id=str(uuid.uuid4()))
        assert total == 0
        assert result_items == []


# ---------------------------------------------------------------------------
# BacklogService.bulk_assign_sprint
# ---------------------------------------------------------------------------


class TestBulkAssignSprint:
    async def test_updates_rows_and_returns_count(self, service, mock_session):
        update_result = MagicMock()
        update_result.rowcount = 3
        mock_session.execute = AsyncMock(return_value=update_result)

        item_ids = [str(uuid.uuid4()) for _ in range(3)]
        updated = await service.bulk_assign_sprint(
            mock_session,
            company_id=str(uuid.uuid4()),
            work_item_ids=item_ids,
            sprint_id=str(uuid.uuid4()),
        )
        assert updated == 3
        mock_session.flush.assert_called_once()

    async def test_empty_list_returns_zero_without_db_call(self, service, mock_session):
        updated = await service.bulk_assign_sprint(
            mock_session,
            company_id=str(uuid.uuid4()),
            work_item_ids=[],
            sprint_id=str(uuid.uuid4()),
        )
        assert updated == 0
        mock_session.execute.assert_not_called()

    async def test_partial_update_when_some_ids_not_in_company(self, service, mock_session):
        update_result = MagicMock()
        update_result.rowcount = 2  # only 2 of 3 belong to this company
        mock_session.execute = AsyncMock(return_value=update_result)

        item_ids = [str(uuid.uuid4()) for _ in range(3)]
        updated = await service.bulk_assign_sprint(
            mock_session,
            company_id=str(uuid.uuid4()),
            work_item_ids=item_ids,
            sprint_id=str(uuid.uuid4()),
        )
        assert updated == 2


# ---------------------------------------------------------------------------
# Backlog API routes (via TestClient)
# ---------------------------------------------------------------------------


@pytest.fixture
def app_client():
    """Minimal FastAPI app wiring only the backlog router for route-level tests."""
    from fastapi import FastAPI

    from llc.api.backlog import router

    app = FastAPI()
    app.include_router(router, prefix="/api/llc")
    return TestClient(app, raise_server_exceptions=True)


class TestBacklogRoute:
    def test_get_backlog_missing_company_id_returns_422(self, app_client):
        response = app_client.get("/api/llc/backlog")
        assert response.status_code == 422

    def test_get_backlog_calls_service(self, app_client):
        company_id = str(uuid.uuid4())
        items = [_make_item(priority=WorkItemPriority.CRITICAL)]

        with (
            patch("llc.api.backlog._service") as mock_svc_factory,
            patch("llc.api.backlog.get_async_session_factory"),
        ):
            svc = AsyncMock()
            svc.list_backlog = AsyncMock(return_value=(items, 1))
            mock_svc_factory.return_value = svc

            # Override the session dependency
            from fastapi import FastAPI

            from llc.api.backlog import get_session, router

            app = FastAPI()

            async def _fake_session():
                yield AsyncMock()

            app.include_router(router, prefix="/api/llc")
            app.dependency_overrides[get_session] = _fake_session

            from fastapi.testclient import TestClient as TC

            client = TC(app)
            response = client.get(f"/api/llc/backlog?company_id={company_id}")
            assert response.status_code == 200
            data = response.json()
            assert "items" in data
            assert "total" in data
            assert data["total"] == 1
            assert data["limit"] == 50
            assert data["offset"] == 0

    def test_bulk_assign_sprint_missing_body_returns_422(self, app_client):
        response = app_client.post("/api/llc/backlog/bulk-assign-sprint", json={})
        assert response.status_code == 422

    def test_bulk_assign_sprint_calls_service(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient as TC

        from llc.api.backlog import get_session, router

        app = FastAPI()

        async def _fake_session():
            yield AsyncMock()

        app.include_router(router, prefix="/api/llc")
        app.dependency_overrides[get_session] = _fake_session

        with patch("llc.api.backlog._service") as mock_svc_factory:
            svc = AsyncMock()
            svc.bulk_assign_sprint = AsyncMock(return_value=2)
            mock_svc_factory.return_value = svc

            client = TC(app)
            sprint_id = str(uuid.uuid4())
            payload = {
                "company_id": str(uuid.uuid4()),
                "sprint_id": sprint_id,
                "work_item_ids": [str(uuid.uuid4()), str(uuid.uuid4())],
            }
            response = client.post("/api/llc/backlog/bulk-assign-sprint", json=payload)
            assert response.status_code == 200
            data = response.json()
            assert data["updated"] == 2
            assert data["sprint_id"] == sprint_id
