# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The findings write routes keep what they answer 2xx for (#21332).

`scan`, `promote` and `dismiss` only flush (`finding_proposal_service`), the handlers never commit, and
`get_session` used to close without committing: the write was rolled back while the caller got a 200. The
real `get_session` is used here (only its session factory is pointed at a file database) and every
assertion reads through a SECOND connection, so only a committed row passes.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import AsyncIterator
from unittest.mock import patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api.user_management.dependencies import get_current_user, require_org_context
from autobot_shared.status_enums import Severity
from llc.api import findings as findings_api
from llc.models.enums import FindingProposalStatus
from llc.models.finding_proposal import LLCFindingProposal
from llc.models.sprint import LLCProject
from llc.tests import _e2e_harness as harness
from user_management.services import TenantContext

_USER = uuid.uuid4()


@pytest_asyncio.fixture
async def factory(tmp_path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:  # noqa: ANN001
    engine = create_async_engine(  # canonical: ignore py-adhoc-db-engine (test-local engine)
        f"sqlite+aiosqlite:///{tmp_path / 'findings.db'}"
    )
    harness.loop_tables()  # scrubs the Postgres-only defaults of LLCProject for SQLite
    finding = LLCFindingProposal.__table__
    harness._scrub_pg_server_defaults(finding)
    harness._rebind_enums_by_value(finding)
    harness._clientside_timestamps(finding)
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: LLCProject.metadata.create_all(c, tables=[LLCProject.__table__, finding]))
    yield async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local session factory)
        engine, expire_on_commit=False, class_=AsyncSession
    )
    await engine.dispose()


@pytest_asyncio.fixture
async def seeded(factory) -> SimpleNamespace:  # noqa: ANN001
    company, project, proposal = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with factory() as s:
        s.add(LLCProject(id=project, company_id=company, name="P", code_source_id="src"))
        s.add(_proposal(proposal, company, project, "seed-key"))
        await s.commit()
    return SimpleNamespace(company=company, project=project, proposal=proposal)


def _proposal(pid: uuid.UUID, company: uuid.UUID, project: uuid.UUID, key: str) -> LLCFindingProposal:
    return LLCFindingProposal(
        id=pid,
        company_id=company,
        project_id=project,
        source_id="src",
        finding_key=key,
        finding_type="bug",
        severity=Severity.HIGH.value,
        file_path="a.py",
        description="d",
        status=FindingProposalStatus.PENDING,
    )


@pytest_asyncio.fixture
async def client(factory, seeded) -> AsyncIterator[AsyncClient]:  # noqa: ANN001
    app = FastAPI()
    app.include_router(findings_api.router)
    ctx = TenantContext(org_id=seeded.company, user_id=_USER, is_platform_admin=False)
    app.dependency_overrides[get_current_user] = lambda: {"id": str(_USER), "user_id": str(_USER)}
    app.dependency_overrides[require_org_context] = lambda: ctx
    # The REAL llc.deps.get_session runs: only the factory it opens its session from is the file database.
    with patch("llc.deps.get_async_session_factory", return_value=factory):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            yield c


async def _stored(factory, proposal: uuid.UUID) -> LLCFindingProposal:  # noqa: ANN001
    """The row as a DIFFERENT session sees it."""
    async with factory() as other:
        return (await other.execute(select(LLCFindingProposal).where(LLCFindingProposal.id == proposal))).scalar_one()


@pytest.mark.asyncio
async def test_a_dismissed_proposal_is_committed_when_the_route_answers(
    client, factory, seeded
) -> None:  # noqa: ANN001
    resp = await client.post(f"/findings/proposals/{seeded.proposal}/dismiss", json={"reason": "noise"})
    assert resp.status_code == 200
    stored = await _stored(factory, seeded.proposal)
    assert (stored.status, stored.dismiss_reason) == (FindingProposalStatus.DISMISSED, "noise")


@pytest.mark.asyncio
async def test_a_promoted_proposal_is_committed_when_the_route_answers(client, factory, seeded) -> None:  # noqa: ANN001
    item = uuid.uuid4()

    async def _flush_only_promote(proposal, session, actor):  # noqa: ANN001, ANN202
        """What `finding_proposal_service.promote` does to the proposal: change it and flush, never commit."""
        proposal.status = FindingProposalStatus.PROMOTED
        proposal.work_item_id = item
        await session.flush()
        return SimpleNamespace(id=item, identifier="X-1", title="t")

    with patch.object(findings_api, "promote", _flush_only_promote):
        resp = await client.post(f"/findings/proposals/{seeded.proposal}/promote")
    assert resp.status_code == 200
    stored = await _stored(factory, seeded.proposal)
    assert (stored.status, stored.work_item_id) == (FindingProposalStatus.PROMOTED, item)


@pytest.mark.asyncio
async def test_a_scanned_proposal_is_committed_when_the_route_answers(client, factory, seeded) -> None:  # noqa: ANN001
    new = uuid.uuid4()

    async def _flush_only_scan(project, session):  # noqa: ANN001, ANN202
        """What `finding_proposal_service.scan` does with a real finding: add the proposal and flush."""
        session.add(_proposal(new, project.company_id, project.id, "scan-key"))
        await session.flush()
        return {"gathered": 1, "verified_real": 1, "queued": 1}

    enabled = SimpleNamespace(enabled=True)

    async def _policy() -> SimpleNamespace:
        return enabled

    with (
        patch.object(findings_api, "scan", _flush_only_scan),
        patch.object(findings_api, "get_findings_policy", _policy),
    ):
        resp = await client.post(f"/projects/{seeded.project}/findings/scan")
    assert resp.status_code == 200
    assert (await _stored(factory, new)).finding_key == "scan-key"


@pytest.mark.asyncio
async def test_a_refused_dismissal_leaves_the_proposal_untouched(client, factory, seeded) -> None:  # noqa: ANN001
    """The other direction: a 409 raises inside the route, so the scope rolls back and nothing is written."""
    first = await client.post(f"/findings/proposals/{seeded.proposal}/dismiss", json={"reason": "first"})
    second = await client.post(f"/findings/proposals/{seeded.proposal}/dismiss", json={"reason": "second"})
    assert (first.status_code, second.status_code) == (200, 409)
    assert (await _stored(factory, seeded.proposal)).dismiss_reason == "first"
