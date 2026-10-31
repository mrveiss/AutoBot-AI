# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""GET /work-items/{id}/comments (GH#18750): tenant-scoped, oldest first, bounded."""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

from user_management.services import TenantContext

_USER_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")
_T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _comment(org: str, item: str, body: str, minutes: int) -> MagicMock:
    c = MagicMock()
    c.id = uuid.uuid4()
    c.work_item_id = uuid.UUID(item)
    c.company_id = uuid.UUID(org)
    c.body = body
    c.author_agent_id = None
    c.author_user_id = _USER_ID
    c.created_at = _T0 + timedelta(minutes=minutes)
    return c


def _make_app(caller_org: str, item_company: str, rows=()):
    """Router-level app; returns (client, session) so tests can inspect the query."""
    from api.user_management.dependencies import get_current_user, require_org_context  # noqa: PLC0415
    from llc.api.work_item_comments import router  # noqa: PLC0415
    from llc.api.work_items import router as wi_router  # noqa: PLC0415
    from llc.deps import get_session  # noqa: PLC0415

    app = FastAPI()
    app.include_router(router)
    app.include_router(wi_router)
    session = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = list(rows)
    session.execute = AsyncMock(return_value=result)
    session.commit = AsyncMock()

    async def _fake_session():
        yield session

    app.dependency_overrides[get_session] = _fake_session
    app.dependency_overrides[get_current_user] = lambda: {"id": str(_USER_ID)}
    app.dependency_overrides[require_org_context] = lambda: TenantContext(
        org_id=uuid.UUID(caller_org), user_id=_USER_ID, is_platform_admin=False
    )
    item = MagicMock()
    item.company_id = item_company
    return TestClient(app), session, item


def _sql(session) -> str:
    stmt = session.execute.call_args.args[0]
    return str(stmt.compile(dialect=postgresql.dialect()))


def _bound(session) -> dict:
    """The values the query binds, so a test can assert the tenant and not only the predicate text."""
    stmt = session.execute.call_args.args[0]
    return stmt.compile(dialect=postgresql.dialect()).params


class TestListComments:
    def test_lists_comments_in_order_with_the_fetch_shape(self):
        org, item_id = str(uuid.uuid4()), str(uuid.uuid4())
        rows = [_comment(org, item_id, "first", 0), _comment(org, item_id, "second", 5)]
        client, session, item = _make_app(org, org, rows)
        with patch("llc.services.work_item_service.WorkItemService.get", AsyncMock(return_value=item)):
            resp = client.get(f"/work-items/{item_id}/comments")
        assert resp.status_code == 200
        body = resp.json()
        assert [c["body"] for c in body["comments"]] == ["first", "second"]
        assert body["comments"][0]["created_at"] == _T0.isoformat()
        assert body["comments"][0]["author_user_id"] == str(_USER_ID)
        sql = _sql(session)
        assert "ORDER BY llc_work_item_comments.created_at ASC" in sql
        assert "LIMIT" in sql and "llc_work_item_comments.company_id =" in sql
        bound = _bound(session)
        assert uuid.UUID(org) in bound.values()
        assert uuid.UUID(item_id) in bound.values()

    def test_other_companys_item_is_404_and_never_queries_comments(self):
        caller, other = str(uuid.uuid4()), str(uuid.uuid4())
        client, session, item = _make_app(caller, other)
        with patch("llc.services.work_item_service.WorkItemService.get", AsyncMock(return_value=item)):
            resp = client.get(f"/work-items/{uuid.uuid4()}/comments")
        assert resp.status_code == 404
        session.execute.assert_not_called()

    def test_missing_item_is_404(self):
        org = str(uuid.uuid4())
        client, _, _ = _make_app(org, org)
        with patch("llc.services.work_item_service.WorkItemService.get", AsyncMock(return_value=None)):
            assert client.get(f"/work-items/{uuid.uuid4()}/comments").status_code == 404

    def test_limit_is_bounded(self):
        from llc.api.work_item_comments import COMMENTS_PAGE_MAX  # noqa: PLC0415

        org = str(uuid.uuid4())
        client, _, item = _make_app(org, org)
        with patch("llc.services.work_item_service.WorkItemService.get", AsyncMock(return_value=item)):
            url = f"/work-items/{uuid.uuid4()}/comments"
            assert client.get(url, params={"limit": COMMENTS_PAGE_MAX + 1}).status_code == 422
            assert client.get(url, params={"limit": 0}).status_code == 422


class TestPaging:
    def test_a_full_page_with_more_behind_it_says_so_and_drops_the_probe_row(self):
        org, item_id = str(uuid.uuid4()), str(uuid.uuid4())
        rows = [_comment(org, item_id, f"c{i}", i) for i in range(3)]
        client, session, item = _make_app(org, org, rows)
        with patch("llc.services.work_item_service.WorkItemService.get", AsyncMock(return_value=item)):
            body = client.get(f"/work-items/{item_id}/comments", params={"limit": 2}).json()
        assert [c["body"] for c in body["comments"]] == ["c0", "c1"]
        assert body["has_more"] is True
        assert 3 in _bound(session).values()  # LIMIT is limit + 1

    def test_the_last_page_says_nothing_more(self):
        org, item_id = str(uuid.uuid4()), str(uuid.uuid4())
        rows = [_comment(org, item_id, f"c{i}", i) for i in range(2)]
        client, _, item = _make_app(org, org, rows)
        with patch("llc.services.work_item_service.WorkItemService.get", AsyncMock(return_value=item)):
            body = client.get(f"/work-items/{item_id}/comments", params={"limit": 2, "offset": 4}).json()
        assert len(body["comments"]) == 2 and body["has_more"] is False and body["offset"] == 4


class TestPageSizeSettings:
    def test_a_zero_or_negative_setting_is_floored_at_one(self, monkeypatch):
        import importlib  # noqa: PLC0415

        import llc.api.work_item_comments as mod  # noqa: PLC0415

        monkeypatch.setenv("LLC_COMMENTS_PAGE_DEFAULT", "-5")
        monkeypatch.setenv("LLC_COMMENTS_PAGE_MAX", "0")
        try:
            reloaded = importlib.reload(mod)
            assert reloaded.COMMENTS_PAGE_DEFAULT >= 1 and reloaded.COMMENTS_PAGE_MAX >= 1
        finally:
            monkeypatch.undo()
            importlib.reload(mod)


class TestPostSiblingStillWorks:
    def test_post_comment_returns_201(self):
        org, item_id = str(uuid.uuid4()), str(uuid.uuid4())
        client, _, item = _make_app(org, org)
        created = _comment(org, item_id, "hello", 0)
        with (
            patch("llc.services.work_item_service.WorkItemService.get", AsyncMock(return_value=item)),
            patch("llc.services.work_item_service.WorkItemService.add_comment", AsyncMock(return_value=created)),
        ):
            resp = client.post(f"/work-items/{item_id}/comments", json={"company_id": org, "body": "hello"})
        assert resp.status_code == 201
        assert resp.json()["body"] == "hello"
