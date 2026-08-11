# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""A company's teams must be readable from the company scope (#13938).

The Org Chart's People list groups people by team. Team data already exists —
``teams`` / ``team_memberships``, org-scoped (#6042) — and a company inside
AutoBot *is* an ``Organization``, so ``Team.org_id == company_id``. What did not
exist was a company-path-scoped read of it: ``/teams`` resolves the org from the
ambient tenant context, so a platform admin looking at another company's Org
Chart would have been grouped by their *own* org's teams.

These tests assert the payload a caller actually receives, not that a route
exists: a named team with the right member ids, an empty list when the company
has no team (so the UI can render an honest empty state instead of inventing a
group), and no leakage of another company's teams.
"""

from __future__ import annotations

import uuid
from typing import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine

# Importing the harness registers the SQLite compile shims for
# postgresql.JSONB / postgresql.UUID (module-level side effect).
from llc.tests import _e2e_harness as harness
from llc.tests.test_org_chart_enrichment import (  # noqa: F401 — pytest fixtures
    app,
    client,
    session_factory,
)
from user_management.models.base import Base
from user_management.models.team import Team, TeamMembership

# canonical: ignore py-adhoc-db-engine (test-local engine, in-memory only)
_SQLITE_MEMORY_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def engine() -> AsyncIterator:
    """Only the two team tables — ``_e2e_harness``'s loop schema deliberately
    omits them, and this endpoint reads nothing else. Shadows the imported
    ``engine`` fixture, which ``session_factory`` then resolves to."""
    eng = create_async_engine(_SQLITE_MEMORY_URL)
    tables = [Team.__table__, TeamMembership.__table__]
    for table in tables:
        harness._scrub_pg_server_defaults(table)
        harness._clientside_timestamps(table)
    async with eng.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield eng
    await eng.dispose()


async def _seed_team(
    session_factory,  # noqa: ANN001
    company_id: uuid.UUID,
    name: str,
    member_ids: list[uuid.UUID],
    *,
    deleted: bool = False,
) -> uuid.UUID:
    """Seed one team of ``company_id`` with its memberships. Returns the team id."""
    from autobot_shared.time_utils import now_utc

    team_id = uuid.uuid4()
    async with session_factory() as session:
        session.add(
            Team(
                id=team_id,
                org_id=company_id,
                name=name,
                settings={},
                is_default=False,
                deleted_at=now_utc() if deleted else None,
            )
        )
        for user_id in member_ids:
            session.add(TeamMembership(id=uuid.uuid4(), team_id=team_id, user_id=user_id))
        await session.commit()
    return team_id


@pytest.mark.asyncio
async def test_company_teams_returns_named_team_with_its_members(client, session_factory):  # noqa: ANN001
    """The reproduction: the caller gets the team name and its member user ids."""
    company_id = uuid.uuid4()
    user_id = uuid.uuid4()
    team_id = await _seed_team(session_factory, company_id, "Platform", [user_id])

    resp = await client.get(f"/api/llc/companies/{company_id}/teams")

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"teams": [{"id": str(team_id), "name": "Platform", "member_user_ids": [str(user_id)]}]}


@pytest.mark.asyncio
async def test_company_with_no_team_returns_an_empty_list(client, session_factory):  # noqa: ANN001
    """No teams is reported as no teams — never as a fabricated default group."""
    resp = await client.get(f"/api/llc/companies/{uuid.uuid4()}/teams")

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"teams": []}


@pytest.mark.asyncio
async def test_an_empty_team_is_still_listed(client, session_factory):  # noqa: ANN001
    """A team with no members is real data — dropping it would hide the team."""
    company_id = uuid.uuid4()
    await _seed_team(session_factory, company_id, "Legal", [])

    body = (await client.get(f"/api/llc/companies/{company_id}/teams")).json()

    assert [team["name"] for team in body["teams"]] == ["Legal"]
    assert body["teams"][0]["member_user_ids"] == []


@pytest.mark.asyncio
async def test_another_companys_team_is_never_returned(client, session_factory):  # noqa: ANN001
    """The case that must stay caught: grouping must never cross companies."""
    mine = uuid.uuid4()
    theirs = uuid.uuid4()
    await _seed_team(session_factory, mine, "Mine", [uuid.uuid4()])
    await _seed_team(session_factory, theirs, "Theirs", [uuid.uuid4()])

    body = (await client.get(f"/api/llc/companies/{mine}/teams")).json()

    assert [team["name"] for team in body["teams"]] == ["Mine"]


@pytest.mark.asyncio
async def test_soft_deleted_team_is_excluded(client, session_factory):  # noqa: ANN001
    """A deleted team must not reappear as a grouping."""
    company_id = uuid.uuid4()
    await _seed_team(session_factory, company_id, "Retired", [uuid.uuid4()], deleted=True)
    await _seed_team(session_factory, company_id, "Active", [])

    body = (await client.get(f"/api/llc/companies/{company_id}/teams")).json()

    assert [team["name"] for team in body["teams"]] == ["Active"]


@pytest.mark.asyncio
async def test_teams_are_denied_for_another_company(client, app, session_factory):  # noqa: ANN001
    """A non-admin caller scoped to one company cannot read another's teams.

    404 rather than 403 is the canonical ``assert_company_access`` behaviour
    (llc/deps.py:142) — a cross-company caller must not be able to tell "not my
    company" from "does not exist". The team names must not appear either way.
    """
    mine = uuid.uuid4()
    theirs = uuid.uuid4()
    await _seed_team(session_factory, theirs, "Theirs", [uuid.uuid4()])
    app.state.tenant["org_id"] = str(mine)
    app.state.tenant["is_platform_admin"] = False

    resp = await client.get(f"/api/llc/companies/{theirs}/teams")

    assert resp.status_code == 404, resp.text
    assert "Theirs" not in resp.text
