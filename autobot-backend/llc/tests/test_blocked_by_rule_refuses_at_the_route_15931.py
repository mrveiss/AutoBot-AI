# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The blocked-by refusal reaches the caller as a 409, through the route (#15931).

`test_blocked_by_rule_fires_15931.py` proves the rule fires when
`transition_status` is called the way production calls it. That is the service
boundary, and it is one layer below the thing a person actually does.

**Why that is not enough, and why this file exists.** The rule's whole history
is a correct implementation nobody reached: it was gated on `relation_svc`,
which only its own tests passed, so it had never run in production. A test that
calls the service directly cannot distinguish "the route enforces this" from
"the route swallows the exception and returns 200", and the latter is exactly
the failure that would restore the original defect with the service tests still
green. `work_items.py:644` sits inside a `try` whose handlers translate
exceptions — the refusal reaching a caller is a claim about the handler, not
about the service.

So these assertions go through `POST /work-items/{id}/transition` with a real
session and real rows, and assert on the **status code and message a client
sees**. The service is not called directly anywhere in this file.

Mutation-checked: deleting the refusal in `work_item_service.py` turns
`test_the_route_refuses_a_blocked_item` red. The service-level tests cannot
serve as that evidence, since they pass either way once the collaborator is
supplied.
"""

from __future__ import annotations

import uuid
from typing import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from llc.models.enums import WorkItemRelationType, WorkItemStatus, WorkItemType
from llc.services.work_item_service import WorkItemService
from llc.tests import _e2e_harness as harness

pytestmark = pytest.mark.asyncio

_COMPANY = str(uuid.uuid4())
_USER_ID = str(uuid.uuid4())


@pytest_asyncio.fixture
async def engine():  # noqa: ANN201
    eng = create_async_engine(  # canonical: ignore py-adhoc-db-engine (test-local engine)
        "sqlite+aiosqlite:///:memory:"
    )
    await harness.create_loop_schema(eng)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine) -> AsyncIterator[AsyncSession]:  # noqa: ANN001
    factory = async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local session factory)
        engine, expire_on_commit=False, class_=AsyncSession
    )
    async with factory() as s:
        yield s


@pytest_asyncio.fixture
async def client(session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """The real router over the real session — only auth and org context are stubbed.

    Overriding `get_session` with the *same* session the test seeds through is
    what makes this an end-to-end assertion rather than a mock agreeing with
    itself.
    """
    from fastapi import FastAPI  # noqa: PLC0415

    from api.user_management.dependencies import get_current_user, require_org_context  # noqa: PLC0415
    from llc.api.work_items import router  # noqa: PLC0415
    from llc.deps import get_session  # noqa: PLC0415
    from user_management.services import TenantContext  # noqa: PLC0415

    app = FastAPI()
    app.include_router(router, prefix="/api/llc")

    async def _session_override() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_session] = _session_override
    app.dependency_overrides[get_current_user] = lambda: {"id": _USER_ID, "sub": "tester"}
    app.dependency_overrides[require_org_context] = lambda: TenantContext(org_id=uuid.UUID(_COMPANY))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _item(session: AsyncSession, *, status: WorkItemStatus, title: str):
    """Seed through the service, so the fixture cannot disagree with production."""
    svc = WorkItemService()
    item = await svc.create(session, company_id=_COMPANY, type=WorkItemType.TASK, title=title)
    item.status = status.value
    await session.commit()
    return item


async def _block(session: AsyncSession, blocker, blocked) -> None:
    from llc.services.work_item_relations import WorkItemRelationService  # noqa: PLC0415

    await WorkItemRelationService().add(
        session,
        company_id=_COMPANY,
        source_id=str(blocker.id),
        target_id=str(blocked.id),
        relation_type=WorkItemRelationType.BLOCKED_BY,
    )
    await session.commit()


async def _transition(client: AsyncClient, item, status: WorkItemStatus):
    return await client.post(
        f"/api/llc/work-items/{item.id}/transition",
        json={"status": status.value},
    )


async def test_the_route_refuses_a_blocked_item(client, session):  # noqa: ANN001
    """The effect at the boundary a caller sees: 409, with the reason intact.

    This is the assertion the issue asks for. Before #15931 the same request
    returned 200 and moved the item, because the rule's collaborator was never
    supplied by this route.
    """
    blocker = await _item(session, status=WorkItemStatus.TODO, title="blocker")
    blocked = await _item(session, status=WorkItemStatus.BLOCKED, title="blocked")
    await _block(session, blocker, blocked)

    response = await _transition(client, blocked, WorkItemStatus.IN_PROGRESS)

    assert (
        response.status_code == 409
    ), f"expected the blocked-by refusal to surface as 409, got {response.status_code}: {response.text}"
    assert (
        "blocked_by" in response.json()["detail"]
    ), "the 409 must carry the reason — a generic conflict cannot be acted on by the UI"

    await session.refresh(blocked)
    assert blocked.status == WorkItemStatus.BLOCKED.value, "the refusal must not have moved the item"


async def test_the_route_allows_an_item_whose_blocker_is_resolved(client, session):  # noqa: ANN001
    """The contrast, and the reason this file is not one assertion.

    A refusal that fires for every BLOCKED item is indistinguishable, from the
    first test alone, from one that reads the relations. This transitions the
    same status with no unresolved blocker and must succeed.
    """
    blocker = await _item(session, status=WorkItemStatus.DONE, title="resolved blocker")
    blocked = await _item(session, status=WorkItemStatus.BLOCKED, title="unblocked")
    await _block(session, blocker, blocked)

    response = await _transition(client, blocked, WorkItemStatus.IN_PROGRESS)

    assert response.status_code == 200, f"a resolved blocker must not refuse: {response.text}"
    assert response.json()["status"] == WorkItemStatus.IN_PROGRESS.value


async def test_the_route_allows_an_item_with_no_blockers_at_all(client, session):  # noqa: ANN001
    """The floor: BLOCKED -> IN_PROGRESS is a legal transition on its own."""
    blocked = await _item(session, status=WorkItemStatus.BLOCKED, title="never blocked")

    response = await _transition(client, blocked, WorkItemStatus.IN_PROGRESS)

    assert response.status_code == 200, f"an item with no relations must transition: {response.text}"
