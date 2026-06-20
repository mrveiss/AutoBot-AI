# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""IDOR hardening tests for boards.py routes (GH#10296).

Mirrors test_sprints_idor.py / test_work_items_idor.py: every entity-keyed and
create route must enforce tenant isolation — a caller in org A cannot read or
mutate org B's boards (cross-tenant returns 404, not 403, to avoid existence
disclosure).
"""

import uuid
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from user_management.services import TenantContext

_FIXED_USER_ID = uuid.UUID("55555555-5555-5555-5555-555555555555")


def _make_board(company_id: str, board_type: str = "kanban") -> MagicMock:
    board = MagicMock()
    board.id = uuid.uuid4()
    board.company_id = uuid.UUID(company_id)
    board.project_id = None
    board.sprint_id = None
    board.type = board_type
    board.name = "Board"
    board.created_at = None
    board.updated_at = None
    board.columns = []
    return board


def _make_client(caller_org_id: str, board_company_id: Optional[str] = None, board_exists: bool = True) -> TestClient:
    from api.user_management.dependencies import get_current_user, require_org_context  # noqa: PLC0415
    from llc.api.boards import router as boards_router  # noqa: PLC0415
    from llc.deps import get_session  # noqa: PLC0415

    app = FastAPI()
    app.include_router(boards_router, prefix="/api/llc")

    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()

    async def _fake_session():
        yield mock_session

    app.dependency_overrides[get_session] = _fake_session
    app.dependency_overrides[get_current_user] = lambda: {"id": str(_FIXED_USER_ID)}
    app.dependency_overrides[require_org_context] = lambda: TenantContext(
        org_id=uuid.UUID(caller_org_id), user_id=_FIXED_USER_ID, is_platform_admin=False
    )

    bcid = board_company_id if board_company_id is not None else caller_org_id
    board = _make_board(bcid) if board_exists else None

    # Patch the service methods the routes call.
    patch("llc.services.board.BoardService.get_board", new=AsyncMock(return_value=board)).start()
    patch(
        "llc.services.board.BoardService.get_board_items",
        new=AsyncMock(return_value={"board": board, "columns": []}),
    ).start()
    patch(
        "llc.services.board.BoardService.get_or_create_kanban",
        new=AsyncMock(return_value=board),
    ).start()
    patch(
        "llc.services.board.BoardService.get_or_create_sprint_board",
        new=AsyncMock(return_value=board),
    ).start()
    patch("llc.services.board.BoardService.move_item", new=AsyncMock(return_value=MagicMock())).start()
    return TestClient(app)


@pytest.fixture(autouse=True)
def _stop_patches():
    yield
    patch.stopall()


_OTHER_ORG = "99999999-9999-9999-9999-999999999999"


class TestBoardsIdor:
    def test_get_board_own_tenant_ok(self):
        org = str(uuid.uuid4())
        client = _make_client(org)
        resp = client.get(f"/api/llc/boards/{uuid.uuid4()}")
        assert resp.status_code == 200

    def test_get_board_cross_tenant_404(self):
        org = str(uuid.uuid4())
        client = _make_client(org, board_company_id=_OTHER_ORG)
        resp = client.get(f"/api/llc/boards/{uuid.uuid4()}")
        assert resp.status_code == 404

    def test_get_board_items_cross_tenant_404(self):
        org = str(uuid.uuid4())
        client = _make_client(org, board_company_id=_OTHER_ORG)
        resp = client.get(f"/api/llc/boards/{uuid.uuid4()}/items")
        assert resp.status_code == 404

    def test_move_item_cross_tenant_404(self):
        org = str(uuid.uuid4())
        client = _make_client(org, board_company_id=_OTHER_ORG)
        resp = client.post(
            f"/api/llc/boards/{uuid.uuid4()}/move",
            json={"work_item_id": str(uuid.uuid4()), "column_id": str(uuid.uuid4()), "actor_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 404

    def test_create_kanban_rejects_foreign_company(self):
        org = str(uuid.uuid4())
        client = _make_client(org)
        resp = client.post(
            "/api/llc/boards/kanban",
            json={"company_id": _OTHER_ORG, "project_id": str(uuid.uuid4()), "name": "K"},
        )
        assert resp.status_code == 404

    def test_create_sprint_rejects_foreign_company(self):
        org = str(uuid.uuid4())
        client = _make_client(org)
        resp = client.post(
            "/api/llc/boards/sprint",
            json={"company_id": _OTHER_ORG, "sprint_id": str(uuid.uuid4()), "name": "S"},
        )
        assert resp.status_code == 404

    def test_create_kanban_own_company_ok(self):
        org = str(uuid.uuid4())
        client = _make_client(org)
        resp = client.post(
            "/api/llc/boards/kanban",
            json={"company_id": org, "project_id": str(uuid.uuid4()), "name": "K"},
        )
        assert resp.status_code == 201
