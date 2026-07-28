# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Boards must be updatable and deletable (#12695).

Boards were the only LLC entity with no backend PUT/DELETE — a board created by
mistake could never be renamed or removed, from the UI or the API.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from user_management.services import TenantContext

_ORG = uuid.UUID("11111111-1111-1111-1111-111111111111")
_OTHER_ORG = uuid.UUID("99999999-9999-9999-9999-999999999999")
_USER = uuid.UUID("22222222-2222-2222-2222-222222222222")


def _board(company_id=_ORG, name="Sprint Board"):
    b = MagicMock()
    b.id = uuid.uuid4()
    b.company_id = company_id
    b.project_id = None
    b.sprint_id = None
    b.type = "kanban"
    b.name = name
    b.created_at = datetime.now(timezone.utc)
    b.updated_at = datetime.now(timezone.utc)
    b.columns = []
    return b


def _client(board, *, updated=None, deleted=True):
    from api.user_management.dependencies import get_current_user, require_org_context
    from llc.api.boards import router
    from llc.deps import get_session

    app = FastAPI()
    app.include_router(router, prefix="/api/llc")
    session = AsyncMock()
    session.commit = AsyncMock()

    async def _sess():
        yield session

    app.dependency_overrides[get_session] = _sess
    app.dependency_overrides[get_current_user] = lambda: {"id": str(_USER)}
    app.dependency_overrides[require_org_context] = lambda: TenantContext(
        org_id=_ORG, user_id=_USER, is_platform_admin=False
    )

    patch("llc.api.boards.BoardService.get_board", new=AsyncMock(return_value=board)).start()
    patch("llc.api.boards.BoardService.update_board", new=AsyncMock(return_value=updated)).start()
    patch("llc.api.boards.BoardService.delete_board", new=AsyncMock(return_value=deleted)).start()
    return TestClient(app), session


@pytest.fixture(autouse=True)
def _stop():
    yield
    patch.stopall()


def test_rename_a_board():
    board = _board()
    renamed = _board(name="Renamed")
    client, session = _client(board, updated=renamed)

    resp = client.put(f"/api/llc/boards/{board.id}", json={"name": "Renamed"})

    assert resp.status_code == 200
    assert resp.json()["name"] == "Renamed"
    session.commit.assert_awaited()


def test_delete_a_board():
    board = _board()
    client, session = _client(board)

    resp = client.delete(f"/api/llc/boards/{board.id}")

    assert resp.status_code == 204
    session.commit.assert_awaited()


def test_cannot_rename_another_tenants_board():
    """404, not 403 — cross-tenant existence must not be disclosed (GH#10296)."""
    client, session = _client(_board(company_id=_OTHER_ORG))

    resp = client.put(f"/api/llc/boards/{uuid.uuid4()}", json={"name": "Hijacked"})

    assert resp.status_code == 404
    session.commit.assert_not_awaited()


def test_cannot_delete_another_tenants_board():
    client, session = _client(_board(company_id=_OTHER_ORG))

    resp = client.delete(f"/api/llc/boards/{uuid.uuid4()}")

    assert resp.status_code == 404
    session.commit.assert_not_awaited()


def test_missing_board_is_404_on_both_verbs():
    client, _ = _client(None)
    bid = uuid.uuid4()

    assert client.put(f"/api/llc/boards/{bid}", json={"name": "x"}).status_code == 404
    assert client.delete(f"/api/llc/boards/{bid}").status_code == 404


@pytest.mark.parametrize("verb", ["put", "delete"])
def test_malformed_board_id_is_400(verb):
    client, _ = _client(_board())
    call = getattr(client, verb)
    resp = call("/api/llc/boards/not-a-uuid", **({"json": {"name": "x"}} if verb == "put" else {}))

    assert resp.status_code == 400


def test_rename_requires_a_name():
    client, _ = _client(_board())
    resp = client.put(f"/api/llc/boards/{uuid.uuid4()}", json={})
    assert resp.status_code == 422
