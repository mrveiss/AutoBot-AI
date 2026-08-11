# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""GH#13993: GET /api/llc/boards/{id}/items response shape.

Regression coverage for three stacked defects:

1. The response nests items inside each column (`columns[].items`) — there
   is no top-level `items` key. The frontend previously read
   `itemsData.items`, which is always undefined, so every board rendered
   zero cards regardless of backend data.
2. `_work_item_summary()` omitted `assignee_type` and `column_id`, the two
   fields the frontend's column/swimlane filters key off.
3. The backend only ever writes `assignee_type` as "user" or "agent" —
   never "human" — so a frontend filter comparing against "human" silently
   drops every human-assigned item even once (1) and (2) are fixed.

This test locks in the actual response shape so a regression to any of the
three is caught here, not downstream in the UI.
"""

import uuid
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from user_management.services import TenantContext

_FIXED_USER_ID = uuid.UUID("55555555-5555-5555-5555-555555555555")
_ORG_ID = str(uuid.uuid4())


def _make_board(company_id: str) -> MagicMock:
    board = MagicMock()
    board.id = uuid.uuid4()
    board.company_id = uuid.UUID(company_id)
    board.project_id = None
    board.sprint_id = None
    board.type = "kanban"
    board.name = "Board"
    board.created_at = None
    board.updated_at = None
    board.columns = []
    return board


def _make_work_item(assignee_type, assignee_user_id=None, assignee_agent_id=None) -> MagicMock:
    item = MagicMock()
    item.id = uuid.uuid4()
    item.identifier = "WI-001"
    item.title = "Test task"
    item.type = "task"
    item.status = "ready"
    item.priority = "medium"
    item.story_points = None
    item.assignee_agent_id = assignee_agent_id
    item.assignee_user_id = assignee_user_id
    item.assignee_type = assignee_type
    return item


@contextmanager
def _make_client(board: MagicMock, columns_with_items: list):
    """Yield a TestClient with BoardService stubbed for the duration of the block.

    Scoped with ``monkeypatch``-style context management rather than
    ``patch(...).start()`` + ``patch.stopall()``: ``stopall`` tears down *every*
    started patch in the process, including ones owned by other modules, so a
    module-local cleanup would reach outside this file.
    """
    from api.user_management.dependencies import get_current_user, require_org_context  # noqa: PLC0415
    from llc.api.boards import router as boards_router  # noqa: PLC0415
    from llc.deps import get_session  # noqa: PLC0415

    app = FastAPI()
    app.include_router(boards_router, prefix="/api/llc")

    mock_session = AsyncMock()

    async def _fake_session():
        yield mock_session

    app.dependency_overrides[get_session] = _fake_session
    app.dependency_overrides[get_current_user] = lambda: {"id": str(_FIXED_USER_ID)}
    app.dependency_overrides[require_org_context] = lambda: TenantContext(
        org_id=uuid.UUID(_ORG_ID), user_id=_FIXED_USER_ID, is_platform_admin=False
    )

    with (
        patch("llc.services.board.BoardService.get_board", new=AsyncMock(return_value=board)),
        patch(
            "llc.services.board.BoardService.get_board_items",
            new=AsyncMock(return_value={"board": board, "columns": columns_with_items}),
        ),
    ):
        yield TestClient(app)


class TestBoardItemsShape:
    def test_items_are_nested_under_columns_not_top_level(self):
        """The response never carries a top-level `items` key (GH#13993 defect 1)."""
        board = _make_board(_ORG_ID)
        col_id = str(uuid.uuid4())
        item = _make_work_item(assignee_type="user", assignee_user_id=uuid.uuid4())
        columns_with_items = [
            {
                "id": col_id,
                "name": "Ready",
                "position": 0,
                "status_filter": ["ready"],
                "wip_limit": None,
                "items": [item],
            }
        ]

        with _make_client(board, columns_with_items) as client:
            resp = client.get(f"/api/llc/boards/{board.id}/items")

        assert resp.status_code == 200
        body = resp.json()
        assert "items" not in body
        assert len(body["columns"]) == 1
        assert len(body["columns"][0]["items"]) == 1

    def test_each_item_carries_assignee_type_and_column_id(self):
        """GH#13993 defect 2: the swimlane/column filters need both fields."""
        board = _make_board(_ORG_ID)
        col_id = str(uuid.uuid4())
        user_item = _make_work_item(assignee_type="user", assignee_user_id=uuid.uuid4())
        agent_item = _make_work_item(assignee_type="agent", assignee_agent_id=uuid.uuid4())
        columns_with_items = [
            {
                "id": col_id,
                "name": "Ready",
                "position": 0,
                "status_filter": ["ready"],
                "wip_limit": None,
                "items": [user_item, agent_item],
            }
        ]

        with _make_client(board, columns_with_items) as client:
            resp = client.get(f"/api/llc/boards/{board.id}/items")

        assert resp.status_code == 200
        items = resp.json()["columns"][0]["items"]
        assert {i["id"] for i in items} == {str(user_item.id), str(agent_item.id)}
        for returned in items:
            assert returned["column_id"] == col_id
        by_id = {i["id"]: i for i in items}
        assert by_id[str(user_item.id)]["assignee_type"] == "user"
        assert by_id[str(agent_item.id)]["assignee_type"] == "agent"

    def test_assignee_type_vocabulary_is_user_not_human(self):
        """GH#13993 defect 3: the backend never writes "human" — only "user"."""
        board = _make_board(_ORG_ID)
        col_id = str(uuid.uuid4())
        item = _make_work_item(assignee_type="user", assignee_user_id=uuid.uuid4())
        columns_with_items = [
            {
                "id": col_id,
                "name": "Ready",
                "position": 0,
                "status_filter": ["ready"],
                "wip_limit": None,
                "items": [item],
            }
        ]

        with _make_client(board, columns_with_items) as client:
            resp = client.get(f"/api/llc/boards/{board.id}/items")

        returned = resp.json()["columns"][0]["items"][0]
        assert returned["assignee_type"] == "user"
        assert returned["assignee_type"] != "human"
