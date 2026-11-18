# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""An agent id in a release request cannot clear a person's checkout (#20521, interim guard).

The release route compared ``agent_id`` only when the row had an agent assignee, so any valid agent UUID cleared
the checkout stamps of a person-held item. A person-held item is refused with 409, as the checkout refuses it.
"""

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from llc.api import work_items as work_items_api
from llc.services import work_item_service as wis

_AGENT = "b3c1e7a2-9d4f-4c68-a1f5-2e8d6b0c7a43"
_USER = "5799065e-4061-4af8-bee7-64e65f1a2b91"
_ORG = uuid.UUID("0f1d7a52-3c88-4b6e-9a0d-61c2b7e4f905")
_ITEM_ID = uuid.UUID("9c2e4b1a-7d35-4f08-8e6a-3b1d5c7a9e02")


def _person_held():
    return MagicMock(
        id=_ITEM_ID, company_id=_ORG, assignee_user_id=uuid.UUID(_USER), assignee_agent_id=None,
        checkout_run_id=None, checkout_locked_at=datetime.now(timezone.utc), version=1,
    )  # fmt: skip


def _session(item) -> MagicMock:
    session = MagicMock(flush=AsyncMock(), commit=AsyncMock())
    session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=item)))
    return session


async def test_service_release_of_a_person_held_item_raises_checkout_conflict_and_leaves_the_row():
    """Before: the stamps were cleared and the version bumped. After: CheckoutConflict, nothing written."""
    item = _person_held()
    service = wis.WorkItemService(activity_log=MagicMock(record=AsyncMock()))
    with pytest.raises(wis.CheckoutConflict, match=f"held by user {_USER}"):
        await service.release(_session(item), str(_ITEM_ID), _AGENT)
    assert item.checkout_locked_at is not None
    assert item.version == 1


def _client(item) -> TestClient:
    from api.user_management.dependencies import get_current_user, require_org_context  # noqa: PLC0415
    from llc.deps import get_session  # noqa: PLC0415

    app = FastAPI()
    app.include_router(work_items_api.router)

    async def _override_session():
        yield _session(item)

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_current_user] = lambda: {"id": _USER, "user_id": _USER, "auth_method": "session"}
    app.dependency_overrides[require_org_context] = lambda: SimpleNamespace(org_id=_ORG, user_id=_USER)
    return TestClient(app)


def test_the_release_route_answers_409_with_the_holder_to_an_agent_releasing_a_person_held_item():
    item = _person_held()
    service = wis.WorkItemService(activity_log=MagicMock(record=AsyncMock()))
    service.get = AsyncMock(return_value=item)
    with patch.object(work_items_api, "_service", return_value=service):
        response = _client(item).post(f"/work-items/{_ITEM_ID}/release", json={"agent_id": _AGENT})
    assert response.status_code == 409
    assert _USER in response.json()["detail"]
