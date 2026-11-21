# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A sprint is closed by the verified caller, whatever decider the body names (#20521)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llc.api import sprints as sprints_api

_ME = uuid.uuid4()
_FORGED = str(uuid.uuid4())


@pytest.mark.asyncio
async def test_the_decider_is_the_session_user_not_the_body() -> None:
    body = sprints_api.SprintCloseRequest(approval_id=uuid.uuid4(), decided_by=_FORGED, actor_user_id=_FORGED)
    close = AsyncMock(return_value=SimpleNamespace())
    svc = MagicMock(execute_close=close, schedule_closed_sprint_summary=MagicMock())
    session = AsyncMock()
    ctx = SimpleNamespace(org_id=uuid.uuid4(), user_id=_ME, is_platform_admin=False)

    with (
        patch.object(sprints_api, "_autoclose_svc", svc),
        patch.object(sprints_api, "require_sprint_in_org", AsyncMock()),
    ):
        await sprints_api.close_sprint(uuid.uuid4(), body, session, {"id": str(_ME)}, ctx)

    kwargs = close.await_args.kwargs
    assert kwargs["decided_by"] == _ME and kwargs["actor_user_id"] == str(_ME)
    assert not {"decided_by", "actor_user_id"} & set(sprints_api.SprintCloseRequest.model_fields)
