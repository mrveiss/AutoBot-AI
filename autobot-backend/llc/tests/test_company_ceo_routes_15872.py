# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The CEO designation is reachable over HTTP, and only by its own company (#15872).

`set_ceo` and `clear` existed and were callable only from service code, so an
owner could not appoint a human CEO or change the designation at all.

**Through a mounted app with a real session, not a called handler.** A handler
called directly skips the dependency chain — `require_org_context`,
`get_current_user`, response-model validation — and the tenant boundary lives in
that chain. `test_boards_idor.py` is the precedent.

**The refusal is what is mutated.** #15872's third criterion asks for a test
asserting a non-owner is refused, "not merely that an owner succeeds", because a
permission check is exactly the kind of guard that passes its positive test
while refusing nobody: delete `assert_company_access` and every success case
still passes.
"""

from __future__ import annotations

import uuid
from typing import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from llc.models.enums import RoleHolderType
from llc.tests import _e2e_harness as harness

pytestmark = pytest.mark.asyncio

_CALLER_USER = uuid.uuid4()


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


def _client(session: AsyncSession, caller_org: str):
    """The mounted router, with *caller_org* as the authenticated org."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api.user_management.dependencies import get_current_user, require_org_context
    from autobot_shared.user_management.base_service import TenantContext
    from llc.api.company_ceo import router
    from llc.deps import get_session

    app = FastAPI()
    app.include_router(router, prefix="/api/llc")

    async def _fake_session():
        yield session

    app.dependency_overrides[get_session] = _fake_session
    app.dependency_overrides[get_current_user] = lambda: {"id": str(_CALLER_USER)}
    app.dependency_overrides[require_org_context] = lambda: TenantContext(
        org_id=uuid.UUID(caller_org), user_id=_CALLER_USER, is_platform_admin=False
    )
    return TestClient(app)


async def _seed_agent(session: AsyncSession, company_id: str, slug: str) -> uuid.UUID:
    """An agent node in *company_id*, seeded through the model (#15905)."""
    from models.agent_org import AgentOrgNode

    node = AgentOrgNode(
        id=uuid.uuid4(),
        agent_id=slug,
        name=slug,
        org_role="ic",
        company_id=uuid.UUID(company_id),
    )
    session.add(node)
    await session.commit()
    return node.id


async def _designation(session: AsyncSession, company_id: str):
    from llc.services.company_ceo import CompanyCEOService

    return await CompanyCEOService().designation(session, uuid.UUID(company_id))


# ---------------------------------------------------------------------------
# The effect
# ---------------------------------------------------------------------------


async def test_setting_the_ceo_writes_the_designation(session):  # noqa: ANN001
    """The row changed — not merely that the route returned 200."""
    company = str(uuid.uuid4())
    agent = await _seed_agent(session, company, "ceo-candidate")

    response = _client(session, company).put(
        f"/api/llc/companies/{company}/ceo",
        json={"holder_type": RoleHolderType.AGENT.value, "holder_id": str(agent)},
    )

    assert response.status_code == 200, response.text
    assert response.json()["holder_id"] == str(agent)

    row = await _designation(session, company)
    assert row is not None, "the route returned success and no designation was written"
    assert str(row.holder_agent_id) == str(agent)
    assert row.holder_user_id is None, "the other holder column was left populated"


async def test_reading_back_reports_the_designation(session):  # noqa: ANN001
    company = str(uuid.uuid4())
    agent = await _seed_agent(session, company, "ceo-read")
    client = _client(session, company)
    client.put(
        f"/api/llc/companies/{company}/ceo",
        json={"holder_type": RoleHolderType.AGENT.value, "holder_id": str(agent)},
    )

    body = client.get(f"/api/llc/companies/{company}/ceo").json()

    assert body["holder_id"] == str(agent)
    assert body["holder_type"] == RoleHolderType.AGENT.value
    assert body["holder_exists"] is True


async def test_a_company_with_no_designation_reads_as_empty(session):  # noqa: ANN001
    """The contrast case: without it, a handler returning a fixed body passes."""
    company = str(uuid.uuid4())

    body = _client(session, company).get(f"/api/llc/companies/{company}/ceo").json()

    assert body["holder_id"] is None
    assert body["holder_exists"] is False


async def test_clearing_removes_the_row(session):  # noqa: ANN001
    company = str(uuid.uuid4())
    agent = await _seed_agent(session, company, "ceo-clear")
    client = _client(session, company)
    client.put(
        f"/api/llc/companies/{company}/ceo",
        json={"holder_type": RoleHolderType.AGENT.value, "holder_id": str(agent)},
    )

    response = client.delete(f"/api/llc/companies/{company}/ceo")

    assert response.status_code == 204
    assert await _designation(session, company) is None, "the route returned 204 and the row is still there"


async def test_clearing_nothing_is_a_404(session):  # noqa: ANN001
    """ "I removed it" and "there was nothing there" must not read alike to a
    client retrying a failed request."""
    company = str(uuid.uuid4())

    assert _client(session, company).delete(f"/api/llc/companies/{company}/ceo").status_code == 404


# ---------------------------------------------------------------------------
# The boundary — #15872 AC3
# ---------------------------------------------------------------------------


async def test_a_non_owner_cannot_read_another_companys_designation(session):  # noqa: ANN001
    company, intruder = str(uuid.uuid4()), str(uuid.uuid4())
    agent = await _seed_agent(session, company, "ceo-private")
    _client(session, company).put(
        f"/api/llc/companies/{company}/ceo",
        json={"holder_type": RoleHolderType.AGENT.value, "holder_id": str(agent)},
    )

    response = _client(session, intruder).get(f"/api/llc/companies/{company}/ceo")

    assert response.status_code == 404, "another org read this company's CEO designation"


async def test_a_non_owner_cannot_set_another_companys_ceo(session):  # noqa: ANN001
    """The write half, and the one that matters: reading leaks, writing installs.

    Asserted on the table, not only on the status code. A route that 404s after
    committing has refused nothing.
    """
    company, intruder = str(uuid.uuid4()), str(uuid.uuid4())
    agent = await _seed_agent(session, company, "ceo-target")

    response = _client(session, intruder).put(
        f"/api/llc/companies/{company}/ceo",
        json={"holder_type": RoleHolderType.AGENT.value, "holder_id": str(agent)},
    )

    assert response.status_code == 404
    assert await _designation(session, company) is None, "another org installed a CEO in this company"


async def test_a_non_owner_cannot_clear_another_companys_ceo(session):  # noqa: ANN001
    company, intruder = str(uuid.uuid4()), str(uuid.uuid4())
    agent = await _seed_agent(session, company, "ceo-keep")
    _client(session, company).put(
        f"/api/llc/companies/{company}/ceo",
        json={"holder_type": RoleHolderType.AGENT.value, "holder_id": str(agent)},
    )

    response = _client(session, intruder).delete(f"/api/llc/companies/{company}/ceo")

    assert response.status_code == 404
    assert await _designation(session, company) is not None, "another org cleared this company's CEO"


async def test_a_holder_from_another_company_is_refused(session):  # noqa: ANN001
    """CWE-639 on the holder as well as on the company.

    The caller owns the company here — `assert_company_access` passes — so this
    is the service's `_require_in_company` doing the work, and the route must
    surface it as 422 rather than 500.
    """
    company, elsewhere = str(uuid.uuid4()), str(uuid.uuid4())
    foreign = await _seed_agent(session, elsewhere, "ceo-foreign")

    response = _client(session, company).put(
        f"/api/llc/companies/{company}/ceo",
        json={"holder_type": RoleHolderType.AGENT.value, "holder_id": str(foreign)},
    )

    assert response.status_code == 422, response.text
    assert await _designation(session, company) is None, "a holder from another company was installed"


async def test_a_designation_whose_holder_is_gone_reports_it(session):  # noqa: ANN001
    """The only case where `designation()` and `resolve()` disagree — and the
    entire reason `holder_exists` is derived rather than hardcoded.

    The other `holder_exists is False` test covers *no designation at all*,
    which returns early and never reaches `resolve()`. So without this,
    replacing `resolved is not None` with `True` passes the whole suite.

    This is #15770's fifth criterion at the route layer: a designation whose
    holder was deleted or has left the company must report that rather than
    claim a CEO. It is covered at the service layer by
    `test_a_deleted_ceo_agent_reports_absence_rather_than_crashing` and was not
    covered here.
    """
    from models.agent_org import AgentOrgNode

    company = str(uuid.uuid4())
    agent = await _seed_agent(session, company, "ceo-vanishing")
    client = _client(session, company)
    client.put(
        f"/api/llc/companies/{company}/ceo",
        json={"holder_type": RoleHolderType.AGENT.value, "holder_id": str(agent)},
    )

    node = (await session.execute(select(AgentOrgNode).where(AgentOrgNode.id == agent))).scalar_one()
    await session.delete(node)
    await session.commit()

    body = client.get(f"/api/llc/companies/{company}/ceo").json()

    assert body["holder_id"] == str(agent), "the designation itself should still be reported"
    assert body["holder_exists"] is False, "a designation pointing at a deleted holder claimed a live CEO"
    assert await _designation(session, company) is not None, "reading must not delete the designation"
