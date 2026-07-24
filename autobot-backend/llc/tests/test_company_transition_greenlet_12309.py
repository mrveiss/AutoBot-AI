# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""GH#12309 regression: LLC company transitions must not 500 with
MissingGreenlet, and a failed response must never leave a committed state.

Two guards:

1. Real-engine tests (``TestTransitionSurvivesSyncSerialization``) drive the
   *actual* ``CompanyService`` against an in-memory aiosqlite ``AsyncSession``
   so SQLAlchemy's real attribute-expiry behaviour is exercised. The mapper
   default ``eager_defaults="auto"`` only RETURNING-fetches the onupdate
   ``updated_at`` on INSERT, not UPDATE — so post-flush ``updated_at`` stays
   expired and the router's ``_to_read(org)`` serialization (a sync attribute
   read) raises ``MissingGreenlet``. Without the ``session.refresh(org,
   ["updated_at"])`` fix these tests fail exactly as production did.

2. A router ordering test (``test_transition_serializes_before_commit``)
   proves the response is built *before* ``commit()`` so a serialization
   failure rolls back instead of persisting a partial transition (the
   data-integrity half of the bug: caller told 500, DB moved anyway).
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import MissingGreenlet
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles
from fastapi import FastAPI

from api.user_management.dependencies import get_current_user, require_org_context
from llc.api import companies
from llc.models.company import CompanyUpdate
from llc.services.company import CompanyService
from user_management.models.base import Base
from user_management.models.organization import Organization
from user_management.services import TenantContext


# Organization.settings is postgres JSONB; render it as JSON on sqlite so the
# real-engine repro can create the table. Scoped to the sqlite dialect only —
# no effect on the production postgres path.
@compiles(JSONB, "sqlite")
def _compile_jsonb_as_json_on_sqlite(element, compiler, **kw):  # noqa: ANN001
    return "JSON"


async def _seed_company(session_factory, llc_status: str = "onboarding") -> uuid.UUID:
    async with session_factory() as session:
        org = Organization(
            name="AutoBot Relations",
            slug=f"rel-{uuid.uuid4().hex[:8]}",
            settings={},
            llc_status=llc_status,
            issue_counter=0,
            budget_monthly_cents=0,
            spent_monthly_cents=0,
            require_approval_for_hires=False,
        )
        session.add(org)
        await session.commit()
        return org.id


@pytest.fixture()
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[Organization.__table__])
    try:
        yield async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    finally:
        await engine.dispose()


class TestTransitionSurvivesSyncSerialization:
    """The exact router sequence — ``svc.<verb>()`` then ``_to_read(org)`` — must
    not raise MissingGreenlet against a real AsyncSession (GH#12309)."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "start_status, verb, expected",
        [
            ("onboarding", "activate", "active"),
            ("active", "suspend", "paused"),
            ("active", "offboard", "offboarding"),
            ("paused", "archive", "archived"),
        ],
    )
    async def test_transition_then_serialize(self, session_factory, start_status, verb, expected):
        company_id = await _seed_company(session_factory, llc_status=start_status)
        async with session_factory() as session:
            svc = CompanyService(session=session)
            org = await getattr(svc, verb)(company_id)
            # Mirrors llc/api/companies.py: serialize BEFORE commit.
            read = companies._to_read(org)
            await session.commit()

        assert read.llc_status.value == expected
        assert read.updated_at is not None

    @pytest.mark.asyncio
    async def test_patch_update_then_serialize(self, session_factory):
        company_id = await _seed_company(session_factory, llc_status="active")
        async with session_factory() as session:
            svc = CompanyService(session=session)
            org = await svc.update(company_id, CompanyUpdate(name="Renamed"))
            read = companies._to_read(org)
            await session.commit()

        assert read.name == "Renamed"
        assert read.updated_at is not None

    @pytest.mark.asyncio
    async def test_updated_at_is_expired_without_refresh(self, session_factory):
        """Documents the root cause: after an UPDATE flush the onupdate
        ``updated_at`` is expired, so a *sync* read raises MissingGreenlet.
        Guards against a future regression that drops the refresh.
        """
        company_id = await _seed_company(session_factory, llc_status="onboarding")
        async with session_factory() as session:
            org = (await session.execute(select(Organization).where(Organization.id == company_id))).scalar_one()
            org.llc_status = "active"
            await session.flush()  # UPDATE, no refresh
            with pytest.raises(MissingGreenlet):
                _ = org.updated_at  # noqa: F841 — sync access of expired attr


class TestCommitOnlyOnSuccess:
    """The transition endpoints must build the response before committing so a
    serialization failure rolls back rather than persisting a partial state."""

    _ORG_ID = uuid.uuid4()
    _USER_ID = uuid.uuid4()

    def _app(self, svc) -> FastAPI:
        app = FastAPI()
        app.include_router(companies.router, prefix="/api/llc")
        app.dependency_overrides[companies._get_service] = lambda: svc
        app.dependency_overrides[get_current_user] = lambda: {
            "id": str(self._USER_ID),
            "user_id": str(self._USER_ID),
        }
        app.dependency_overrides[require_org_context] = lambda: TenantContext(
            org_id=self._ORG_ID, user_id=self._USER_ID, is_platform_admin=False
        )
        return app

    @pytest.mark.asyncio
    async def test_transition_serializes_before_commit(self, monkeypatch):
        """If ``_to_read`` fails, ``commit()`` must NOT run and ``rollback()``
        must — no committed-but-500 state (GH#12309 data-integrity half)."""
        svc = MagicMock()
        svc.session = AsyncMock()
        svc.activate = AsyncMock(return_value=object())
        monkeypatch.setattr(companies, "_to_read", MagicMock(side_effect=RuntimeError("serialize boom")))

        app = self._app(svc)
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(f"/api/llc/companies/{self._ORG_ID}/activate")

        assert resp.status_code == 500
        svc.session.commit.assert_not_awaited()
        svc.session.rollback.assert_awaited_once()
