# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""GH#12309 regression: LLC company transitions must not 500 with
MissingGreenlet, and a failed response must never leave a committed state.

Two guards:

1. Real-engine tests (``TestTransitionSurvivesSyncSerialization``) drive the
   *actual* ``CompanyService`` against an in-memory aiosqlite ``AsyncSession``
   so SQLAlchemy's real attribute-expiry behaviour is exercised. Base sets
   ``eager_defaults=True`` (#12322), so the onupdate ``updated_at`` is fetched
   inline via the UPDATE's RETURNING clause and stays fresh post-flush — the
   router's ``_to_read(org)`` serialization (a sync attribute read) never
   raises ``MissingGreenlet``. Without that setting these tests fail exactly as
   production did (#12209/#12309).

2. A router ordering test (``test_transition_serializes_before_commit``)
   proves the response is built *before* ``commit()`` so a serialization
   failure rolls back instead of persisting a partial transition (the
   data-integrity half of the bug: caller told 500, DB moved anyway).
"""

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import String, event, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Mapped, mapped_column

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


class _EagerDefaultsProbe(Base):
    """Dedicated throwaway model for the #12322 durability guard.

    Inherits Base (and therefore ``eager_defaults=True`` plus the shared
    ``created_at``/``updated_at`` columns) but is NOT registered with the LLC
    e2e harness, so no other test can mutate its column defaults to client-side
    Python values. That keeps the guard exercising the *real* server-side
    onupdate + RETURNING path regardless of test ordering.
    """

    __tablename__ = "eager_defaults_probe_12322"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)


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
async def test_eager_defaults_populates_updated_at_on_update_without_refresh():
    """#12322 durability guard for Base's ``eager_defaults=True``.

    On a dedicated table (immune to cross-test mutation) prove that after an
    UPDATE ``flush()`` — with NO manual ``session.refresh`` — the onupdate
    ``updated_at`` is populated (not expired), so a *sync* attribute read does
    not raise ``MissingGreenlet``. Also asserts the UPDATE actually carried a
    ``RETURNING updated_at`` clause on the sqlite test dialect, which is the
    exact mechanism that kills the recurring bug class (#12209/#12309). A
    regression that drops ``eager_defaults`` fails this test.
    """
    engine = create_async_engine("sqlite+aiosqlite://")
    update_statements: list[str] = []

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def _capture(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        if statement.lstrip().upper().startswith("UPDATE"):
            update_statements.append(statement)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[_EagerDefaultsProbe.__table__])
    sf = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)

    row_id = uuid.uuid4().hex
    async with sf() as session:
        session.add(_EagerDefaultsProbe(id=row_id, name="orig"))
        await session.flush()
        assert session.get_bind().dialect.update_returning is True
        await session.commit()

    async with sf() as session:
        probe = (
            await session.execute(select(_EagerDefaultsProbe).where(_EagerDefaultsProbe.id == row_id))
        ).scalar_one()
        before = probe.updated_at
        probe.name = "changed"
        await session.flush()  # UPDATE, no manual refresh
        fresh = probe.updated_at  # sync access must NOT raise MissingGreenlet
        await session.commit()

    await engine.dispose()

    assert isinstance(fresh, datetime)
    assert fresh >= before
    # The onupdate column was fetched inline with the UPDATE, not via a later
    # refresh SELECT — that RETURNING is what keeps updated_at unexpired.
    assert any("RETURNING" in s.upper() and "UPDATED_AT" in s.upper() for s in update_statements)


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
