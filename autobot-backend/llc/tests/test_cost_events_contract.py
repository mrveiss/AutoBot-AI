# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The /api/llc/cost-events response must describe the object the client reads (GH#13617).

The dashboard crashed on load for any company with a budget row: the endpoint
sent ``ts``/``cost_usd``/``tokens_in``/``tokens_out`` while the client's
``CostEvent`` declared ``created_at``/``cost``/``input_tokens``/
``output_tokens``. Not one field name matched, so every read was ``undefined``
and ``ev.created_at.slice(0, 10)`` threw.

The first test reads the field names out of the client interface itself rather
than restating them here. A copy of the list in this file would drift with the
same silence that produced the bug -- both sides could be edited and still
agree with a stale third copy. Parsing the real declaration means a rename on
either side fails this test.
"""

from __future__ import annotations

import re
import uuid
from decimal import Decimal
from pathlib import Path
from typing import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from autobot_shared.user_management.base_service import TenantContext
from llc.api.budget import list_cost_events
from llc.models.budget import LLCAgentBudget
from llc.models.enums import BudgetMode
from llc.tests import _e2e_harness as harness

COST_DASHBOARD = (
    Path(__file__).resolve().parents[3] / "autobot-frontend" / "src" / "views" / "llc" / "CostDashboard.vue"
)


def _client_cost_event_fields() -> set[str]:
    """Field names declared by ``interface CostEvent`` in the dashboard.

    Raises rather than skipping when the file cannot be found or parsed: a
    contract test that quietly disappears when a path changes provides exactly
    the false assurance it exists to remove.
    """
    assert COST_DASHBOARD.is_file(), f"client contract source not found at {COST_DASHBOARD}"
    source = COST_DASHBOARD.read_text(encoding="utf-8")
    match = re.search(r"interface CostEvent \{(.*?)\n\}", source, re.DOTALL)
    assert match, "interface CostEvent not found in CostDashboard.vue"
    fields = set(re.findall(r"^\s*(\w+)\??\s*:", match.group(1), re.MULTILINE))
    assert fields, "parsed no fields out of interface CostEvent"
    return fields


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


async def _one_row(session: AsyncSession, company_id: str) -> dict:
    session.add(
        LLCAgentBudget(
            id=uuid.uuid4(),
            company_id=company_id,
            agent_id=f"agent-{uuid.uuid4().hex[:8]}",
            budget_mode=BudgetMode.DOLLARS.value,
            budget_limit=Decimal("100.000000"),
            budget_spent=Decimal("1.250000"),
            token_limit=None,
            tokens_spent=4321,
            alert_threshold=0.8,
        )
    )
    await session.flush()
    rows = await list_cost_events(
        company_id=company_id,
        limit=100,
        session=session,
        _current_user={"id": str(uuid.uuid4())},
        ctx=TenantContext(org_id=uuid.UUID(company_id), is_platform_admin=False),
    )
    assert len(rows) == 1, "fixture should produce exactly one row"
    return rows[0]


@pytest.mark.asyncio
async def test_response_carries_every_field_the_client_declares(session: AsyncSession) -> None:
    """Each non-optional field of the client's CostEvent is present in the payload."""
    company_id = str(uuid.uuid4())
    row = await _one_row(session, company_id)

    missing = _client_cost_event_fields() - set(row)
    assert not missing, f"client reads fields the endpoint never sends: {sorted(missing)}"


@pytest.mark.asyncio
async def test_unknown_values_are_null_not_plausible_placeholders(session: AsyncSession) -> None:
    """What has no source is sent as null, not as a stand-in that reads as real.

    ``model`` was the literal string ``"unknown"``, which renders in the table
    as though an agent really used a model by that name; ``input_tokens``/
    ``output_tokens`` were ``0``, asserting an agent had spent no tokens when
    the split simply is not stored. A null says "not recorded", which is true.
    """
    company_id = str(uuid.uuid4())
    row = await _one_row(session, company_id)

    assert row["created_at"] is None
    assert row["model"] is None
    assert row["provider"] is None
    assert row["input_tokens"] is None
    assert row["output_tokens"] is None
    assert row["source"] == "budget_summary"


@pytest.mark.asyncio
async def test_cost_is_a_number_and_known_tokens_survive(session: AsyncSession) -> None:
    """``cost`` must arrive as a number, and the token total that IS known is kept.

    It was previously ``str(row.budget_spent)``; the client sums it with ``+``,
    so a string turned every total into concatenation or NaN rather than a sum.
    """
    company_id = str(uuid.uuid4())
    row = await _one_row(session, company_id)

    assert isinstance(row["cost"], float)
    assert row["cost"] == pytest.approx(1.25)
    assert row["tokens_spent"] == 4321
