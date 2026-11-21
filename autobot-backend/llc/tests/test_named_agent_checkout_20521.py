# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A body ``agent_id`` on checkout and release is accepted only from an owner/admin, for an agent of the item's company.

Owner decision 2026-11-21 (#20521). Any other member naming an agent is refused with 403; the forged value never
reaches the service. An agent acting for itself uses its own credential on the ``/agent`` routes, untouched here.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from llc.api import work_items as work_items_api
from llc.api._release_request import ReleaseRequest

_ORG = uuid.uuid4()
_ME = uuid.uuid4()
_AGENT = str(uuid.uuid4())  # the forged / named agent id


def _ctx() -> SimpleNamespace:
    return SimpleNamespace(org_id=_ORG, user_id=_ME, is_platform_admin=False)


def _session(agent_company: uuid.UUID | None) -> AsyncMock:
    """A session whose only query, the named agent's company lookup, answers *agent_company*."""
    session = AsyncMock()
    found = object() if agent_company == _ORG else None  # the query is scoped to the item's company
    session.execute.return_value = MagicMock(all=MagicMock(return_value=[found] if found else []))
    return session


def _service() -> MagicMock:
    item = SimpleNamespace(id=uuid.uuid4(), company_id=_ORG)
    return MagicMock(
        get=AsyncMock(return_value=item), checkout=AsyncMock(return_value=item), release=AsyncMock(return_value=item)
    )


async def _checkout(session: AsyncMock, svc: MagicMock) -> None:
    body = work_items_api.CheckoutRequest(agent_id=_AGENT, run_id="r1")
    with (
        patch.object(work_items_api, "_service", return_value=svc),
        patch.object(work_items_api, "_item_to_dict", AsyncMock(return_value={})),
    ):
        await work_items_api.checkout_work_item("w", body, session, {"id": str(_ME)}, _ctx())


async def _release(session: AsyncMock, svc: MagicMock) -> None:
    body = ReleaseRequest(agent_id=_AGENT)
    with (
        patch.object(work_items_api, "_service", return_value=svc),
        patch.object(work_items_api, "_item_to_dict", AsyncMock(return_value={})),
    ):
        await work_items_api.release_work_item("w", body, session, {"id": str(_ME)}, _ctx())


def _role(name: str | None):
    """The caller's membership role in the item's company, read by the canonical ``require_company_admin``."""
    return patch("llc.services.authz.membership_role", AsyncMock(return_value=name))


@pytest.mark.asyncio
@pytest.mark.parametrize("act", [_checkout, _release], ids=["checkout", "release"])
@pytest.mark.parametrize("role", ["member", "viewer", None], ids=["member", "viewer", "not-a-member"])
async def test_a_caller_who_is_not_owner_or_admin_cannot_name_an_agent(act, role) -> None:
    svc = _service()
    with _role(role), pytest.raises(HTTPException) as refused:
        await act(_session(_ORG), svc)  # even an agent of the item's own company

    assert refused.value.status_code == 403
    svc.checkout.assert_not_awaited()
    svc.release.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("act", [_checkout, _release], ids=["checkout", "release"])
@pytest.mark.parametrize("agent_company", [uuid.uuid4(), None], ids=["other-company", "unknown-agent"])
async def test_an_admin_cannot_name_an_agent_of_another_company(act, agent_company) -> None:
    svc = _service()
    with _role("admin"), pytest.raises(HTTPException) as refused:
        await act(_session(agent_company), svc)

    assert refused.value.status_code == 403
    svc.checkout.assert_not_awaited()
    svc.release.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["owner", "admin"])
async def test_an_owner_or_admin_may_act_as_an_agent_of_the_company(role) -> None:
    svc = _service()
    with _role(role):
        await _checkout(_session(_ORG), svc)
        await _release(_session(_ORG), svc)

    assert svc.checkout.await_args.kwargs["agent_id"] == _AGENT
    assert svc.release.await_args.kwargs["agent_id"] == _AGENT
