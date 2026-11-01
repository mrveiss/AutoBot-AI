# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A board move names its actor from the verified caller, and only a person owns tasks (#18978, #20508)."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.user_management.dependencies import get_current_user, require_org_context
from llc.api import _common
from llc.api import boards as boards_api
from llc.deps import get_session
from user_management.services import TenantContext

_USER = uuid.uuid4()
_ORG = uuid.uuid4()


def _move(user: dict, body_extra: dict):
    app = FastAPI()
    app.include_router(boards_api.router)

    async def _session():
        yield AsyncMock()

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[require_org_context] = lambda: TenantContext(
        org_id=_ORG, user_id=_USER, is_platform_admin=False
    )
    board = MagicMock(company_id=str(_ORG))
    mover = AsyncMock(return_value=MagicMock())
    with (
        patch("llc.services.board.BoardService.get_board", new=AsyncMock(return_value=board)),
        patch("llc.services.board.BoardService.move_item", new=mover),
        patch.object(boards_api, "_work_item_summary", return_value={}),
    ):
        resp = TestClient(app).post(
            f"/boards/{uuid.uuid4()}/move",
            json={"work_item_id": str(uuid.uuid4()), "column_id": str(uuid.uuid4()), **body_extra},
        )
    assert resp.status_code == 200, resp.text
    return mover.await_args.kwargs


def test_a_forged_actor_id_in_the_body_never_reaches_the_board_event() -> None:
    kwargs = _move({"id": str(_USER), "auth_method": "session"}, {"actor_id": "forged-actor"})
    assert kwargs["actor_id"] == str(_USER)


@pytest.mark.parametrize(
    ("user", "owns"),
    [
        ({"id": str(_USER), "auth_method": "session"}, True),
        ({"id": str(_USER)}, False),
        ({"id": str(_USER), "auth_method": "session", "service": True}, False),
        ({"id": str(_USER), "auth_method": "run_jwt"}, False),
    ],
    ids=["person", "no-auth-method", "service", "run-credential"],
)
def test_only_an_interactive_person_is_passed_as_the_task_owner(user: dict, owns: bool) -> None:
    assert _common.own_task_actor(user) == (_USER if owns else None)
    assert _move(user, {})["acting_user"] == (_USER if owns else None)
