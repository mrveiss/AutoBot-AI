# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A cost event must move budget_spent, for the model agents actually run on.

Three independent defects produced one symptom -- dollar budgets never accruing
-- and each alone was sufficient, so fixing any one of them left it:

* the route never called the service and returned ``{"recorded": True}`` (#15859);
* the default model had no price, so the cost resolved to zero (#15860);
* a missing budget row makes the atomic UPDATE match nothing, which is logged
  and returned as the cost anyway.

Every assertion here is on the **effect** -- what ``budget_spent`` became --
rather than on a return value. The route's old response was a literal
``{"recorded": True}``, so any test reading the response passed against code
that did nothing at all.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from autobot_shared.ssot_constants import ANTHROPIC_CLAUDE_SONNET4_6
from llc.exceptions import UnpricedModel
from llc.models.budget import LLCAgentBudget
from llc.models.enums import BudgetMode
from llc.services.budget import BudgetService
from llc.tests import _e2e_harness as harness

pytestmark = pytest.mark.asyncio

#: The model LLC hires agents on and the Anthropic provider defaults to.
#: Imported rather than written out: a test spelling the string itself passes
#: when the default moves, which is exactly the drift #15860 was.
DEFAULT_MODEL = ANTHROPIC_CLAUDE_SONNET4_6


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


async def _seed_budget(session: AsyncSession, agent_id: str, company_id: str) -> None:
    session.add(
        LLCAgentBudget(
            id=uuid.uuid4(),
            company_id=company_id,
            agent_id=agent_id,
            budget_mode=BudgetMode.DOLLARS.value,
            budget_limit=Decimal("100"),
            budget_spent=Decimal("0"),
            token_limit=None,
            tokens_spent=0,
            alert_threshold=0.8,
        )
    )
    await session.commit()


async def _spent(session: AsyncSession, agent_id: str, company_id: str) -> Decimal:
    row = (
        await session.execute(
            select(LLCAgentBudget).where(
                LLCAgentBudget.agent_id == agent_id,
                LLCAgentBudget.company_id == company_id,
            )
        )
    ).scalar_one()
    await session.refresh(row)
    return Decimal(str(row.budget_spent))


async def test_the_default_model_accrues_cost(session):  # noqa: ANN001
    """#15860: the model almost everything runs on had no price, so cost was zero.

    Asserted for the **default** specifically, not for an arbitrary priced
    model -- a test using `claude-sonnet-4-20250514` passes throughout the
    defect, because that one was always in the table.
    """
    agent, company = "agent-a", str(uuid.uuid4())
    await _seed_budget(session, agent, company)

    cost = await BudgetService().ingest_cost_event(
        session, agent_id=agent, company_id=company, tokens_in=1_000_000, tokens_out=0, model=DEFAULT_MODEL
    )
    await session.commit()

    assert cost > 0, f"{DEFAULT_MODEL} resolved to a cost of {cost}"
    assert await _spent(session, agent, company) > Decimal("0"), "budget_spent did not move"


async def test_an_unpriced_model_refuses_rather_than_costing_nothing(session):  # noqa: ANN001
    """#15860: a cost of 0 and a cost that could not be computed are the same number.

    Refusing is safe because the table distinguishes free from unknown -- every
    local model carries an explicit zero entry -- so absence means unpriced.
    """
    agent, company = "agent-b", str(uuid.uuid4())
    await _seed_budget(session, agent, company)

    with pytest.raises(UnpricedModel):
        await BudgetService().ingest_cost_event(
            session,
            agent_id=agent,
            company_id=company,
            tokens_in=1_000,
            tokens_out=1_000,
            model="a-model-nobody-priced",
        )

    assert await _spent(session, agent, company) == Decimal("0"), "an unpriced event still moved the budget"


async def test_a_priced_free_model_still_accrues_nothing(session):  # noqa: ANN001
    """The contrast case, and the reason refusing is not over-broad.

    A local model is priced at zero deliberately. If refusal keyed on `cost == 0`
    rather than on absence from the table, this would raise -- and the fix would
    have broken every local-model deployment.
    """
    from autobot_shared.ssot_constants import LOCAL_LLAMA3

    agent, company = "agent-c", str(uuid.uuid4())
    await _seed_budget(session, agent, company)

    cost = await BudgetService().ingest_cost_event(
        session, agent_id=agent, company_id=company, tokens_in=1_000_000, tokens_out=1_000_000, model=LOCAL_LLAMA3
    )
    await session.commit()

    assert cost == Decimal("0")
    assert await _spent(session, agent, company) == Decimal("0")


# ---------------------------------------------------------------------------
# Through the route handler, not just the service (#15859)
# ---------------------------------------------------------------------------
#
# The service tests above pass against a route that crashes before reaching it.
# That is not hypothetical: the first version of this fix dropped
# `_agent_context(request)` from both handlers, so every request would have
# raised NameError -- and every test here still passed, because none of them
# entered a handler.
#
# The PR named that gap as a limitation ("nothing issues a request through the
# mounted router"), honestly and correctly, and the defect landed in it. A
# proxy shipped with its blind spot named is honest; it is still a blind spot.
#
# These call the handler with a mocked Request and a REAL session factory, so
# the body runs end to end and `budget_spent` actually moves. Same shape as
# `test_agent_context_tenant_scope.py`, which is the existing precedent for
# exercising these handlers without an HTTP stack.


def _request(agent_id: str, company_id: str):
    from unittest.mock import MagicMock

    req = MagicMock()
    req.state.agent_id = agent_id
    req.state.company_id = company_id
    return req


def _factory_yielding(session: AsyncSession):
    """Stand-in for `get_async_session_factory` that hands back the test session.

    Two levels of indirection, matching the production shape: the handler calls
    `get_async_session_factory()` to obtain a factory, then calls *that* to get
    a context manager. Patching with the inner lambda directly is one level off
    and fails with `AsyncContextDecorator.__call__() missing 'func'`.
    """
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _cm():
        yield session

    def _get_factory():
        return lambda: _cm()

    return _get_factory


async def test_the_cost_event_route_moves_the_budget(session):  # noqa: ANN001
    """Through the handler: the assertion the service tests cannot make.

    A handler that raises before calling the service passes every service test
    in this file and fails this one.
    """
    from unittest.mock import patch

    from llc.api import agent_api

    agent, company = "agent-route", str(uuid.uuid4())
    await _seed_budget(session, agent, company)

    with patch("user_management.database.get_async_session_factory", new=_factory_yielding(session)):
        result = await agent_api.ingest_cost_event(
            agent_api.CostEvent(model=DEFAULT_MODEL, tokens_in=1_000_000, tokens_out=0),
            _request(agent, company),
        )

    assert result["recorded"] is True
    assert await _spent(session, agent, company) > Decimal("0"), (
        "the route returned recorded=True and budget_spent did not move — which is the "
        "defect #15859 describes, reintroduced"
    )


async def test_the_cost_event_route_refuses_an_unpriced_model(session):  # noqa: ANN001
    """422 rather than a silent zero, asserted at the boundary a caller sees."""
    from unittest.mock import patch

    from fastapi import HTTPException

    from llc.api import agent_api

    agent, company = "agent-route-2", str(uuid.uuid4())
    await _seed_budget(session, agent, company)

    with patch("user_management.database.get_async_session_factory", new=_factory_yielding(session)):
        with pytest.raises(HTTPException) as exc:
            await agent_api.ingest_cost_event(
                agent_api.CostEvent(model="a-model-nobody-priced", tokens_in=10, tokens_out=10),
                _request(agent, company),
            )

    assert exc.value.status_code == 422
    assert await _spent(session, agent, company) == Decimal("0")


async def test_the_cost_event_route_requires_agent_context(session):  # noqa: ANN001
    """401 when middleware injected nothing.

    Also the regression test for the handler losing its `_agent_context` call:
    without it the body raises NameError rather than this HTTPException.
    """
    from unittest.mock import MagicMock, patch

    from fastapi import HTTPException

    from llc.api import agent_api

    req = MagicMock()
    req.state.agent_id = None
    req.state.company_id = None

    with patch("user_management.database.get_async_session_factory", new=_factory_yielding(session)):
        with pytest.raises(HTTPException) as exc:
            await agent_api.ingest_cost_event(agent_api.CostEvent(model=DEFAULT_MODEL, tokens_in=1, tokens_out=1), req)

    assert exc.value.status_code == 401


# ---------------------------------------------------------------------------
# The SECOND route onto the same service call (#15860).
#
# Everything above exercises `POST /agent/cost-events` in `agent_api`.
# `POST /budgets/{agent_id}/ingest` in `llc/api/budget.py` calls the same
# `ingest_cost_event`, and when #15860 gave that service a second failure mode
# only the first route learned about it -- so one condition returned 422 from
# one route and 500 from the other, from the day the condition was introduced.
#
# A service test cannot see that. It is a property of the handler, and there
# were four callers of this service, so "the caller I edited is correct" was
# never the same claim as "the callers agree".
# ---------------------------------------------------------------------------


def _ctx(company_id: str):
    """A tenant context owning *company_id*, which is what `load_authorized` checks."""
    from user_management.services import TenantContext

    return TenantContext(org_id=uuid.UUID(company_id), user_id=uuid.uuid4(), is_platform_admin=False)


async def test_the_ingest_route_refuses_an_unpriced_model_with_422(session):  # noqa: ANN001
    """422, not 500 — the same verdict the sibling route gives for the same cause.

    Before #15860's handler was added here, `UnpricedModel` escaped the `except
    BudgetExhausted` and FastAPI turned it into a 500: a client-actionable
    condition reported as a server fault, on the route nobody would think to
    check after editing the other one.
    """
    from fastapi import HTTPException

    from llc.api import budget as budget_api

    agent, company = "agent-ingest-unpriced", str(uuid.uuid4())
    await _seed_budget(session, agent, company)

    with pytest.raises(HTTPException) as exc:
        await budget_api.ingest_cost(
            agent_id=agent,
            body=budget_api.IngestRequest(tokens_in=10, tokens_out=10, model="a-model-nobody-priced"),
            session=session,
            _current_user={},
            ctx=_ctx(company),
        )

    assert exc.value.status_code == 422, f"unpriced model produced {exc.value.status_code}, not 422"
    assert await _spent(session, agent, company) == Decimal("0")


async def test_the_two_routes_agree_on_an_unpriced_model(session):  # noqa: ANN001
    """The contrast the single-route tests cannot draw.

    Both call one service function. Asserting each against a literal 422
    separately would still pass if one route were changed and the other left
    behind -- which is exactly what happened. This compares them.
    """
    from unittest.mock import patch

    from fastapi import HTTPException

    from llc.api import agent_api
    from llc.api import budget as budget_api

    company = str(uuid.uuid4())
    await _seed_budget(session, "agent-cmp-a", company)
    await _seed_budget(session, "agent-cmp-b", company)

    with patch("user_management.database.get_async_session_factory", new=_factory_yielding(session)):
        with pytest.raises(HTTPException) as via_agent_api:
            await agent_api.ingest_cost_event(
                agent_api.CostEvent(model="a-model-nobody-priced", tokens_in=10, tokens_out=10),
                _request("agent-cmp-a", company),
            )

    with pytest.raises(HTTPException) as via_budget_api:
        await budget_api.ingest_cost(
            agent_id="agent-cmp-b",
            body=budget_api.IngestRequest(tokens_in=10, tokens_out=10, model="a-model-nobody-priced"),
            session=session,
            _current_user={},
            ctx=_ctx(company),
        )

    assert via_agent_api.value.status_code == via_budget_api.value.status_code, (
        f"the two routes onto ingest_cost_event disagree: agent_api gave "
        f"{via_agent_api.value.status_code}, budget_api gave {via_budget_api.value.status_code}"
    )


async def test_the_ingest_route_does_not_call_an_exhausted_budget_a_server_fault(session):  # noqa: ANN001
    """402 is right; `detail="Internal server error"` never was.

    Pre-existing and unrelated to #15860, fixed while in the handler: the
    caller is told the request failed on the server when in fact they have
    spent their budget, which is the one thing they can act on.
    """
    from fastapi import HTTPException

    from llc.api import budget as budget_api

    agent, company = "agent-ingest-exhausted", str(uuid.uuid4())
    await _seed_budget(session, agent, company)

    # Spend $99 of the $100 limit through the service, so the budget is live and
    # nearly gone; the handler call below is what tips it over. Two ways to get
    # this wrong, both of which assert nothing about the handler: spend the whole
    # limit in setup and the raise comes from setup, or spend too little in the
    # handler call and nothing raises at all. The service enforces AFTER the
    # write, on the accumulated total, so the handler event must be large enough
    # to cross on its own.
    await BudgetService().ingest_cost_event(session, agent, company, 33_000_000, 0, DEFAULT_MODEL)
    assert await _spent(session, agent, company) > Decimal("0"), "the setup spend did not land"

    with pytest.raises(HTTPException) as exc:
        await budget_api.ingest_cost(
            agent_id=agent,
            body=budget_api.IngestRequest(tokens_in=1_000_000, tokens_out=0, model=DEFAULT_MODEL),
            session=session,
            _current_user={},
            ctx=_ctx(company),
        )

    assert exc.value.status_code == 402
    assert "Internal server error" not in str(exc.value.detail), (
        "an exhausted budget is reported to the caller as a server fault, which is "
        "the one reading that tells them not to look at their own spend"
    )
    assert agent in str(exc.value.detail), "the detail does not name what was exhausted"
