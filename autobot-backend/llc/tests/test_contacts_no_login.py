# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""A contact must never resolve through any login/session path (#13969).

Two layers, per the issue's acceptance criteria:

1. Structural: ``LLCContact`` carries no column any auth/session code could
   possibly key on (no password, no hash, no session/token field). This
   makes the absence of a login path a property of the schema, not of
   "nobody happened to wire it up yet".
2. Behavioural: creating a contact with a given email must not make that
   email resolve through ``UserService.get_user_by_email`` /
   ``UserService.authenticate`` — the exact two lookups the login endpoint
   uses. Mutation-proved: temporarily making ``ContactService.create`` also
   write a shadow ``users`` row (the precise anti-pattern #13969 forbids —
   "never a users row") turns this test red; reverting turns it green again.
"""

from __future__ import annotations

import uuid
from typing import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Importing the harness registers the SQLite compile shims for
# postgresql.JSONB / postgresql.UUID (module-level side effect).
from autobot_shared.user_management.models.role import Role, UserRole
from llc.models.contact import LLCContact
from llc.services.contact import ContactService
from llc.tests import _e2e_harness as harness
from user_management.models.base import Base
from user_management.models.user import User
from user_management.services.user_service import UserService


def test_contact_model_has_no_authentication_columns() -> None:
    """Structural guard: no password/hash/session/token column exists to fill in."""
    column_names = {c.name for c in LLCContact.__table__.columns}
    forbidden_markers = ("password", "hash", "session", "token", "otp", "mfa")
    offending = {name for name in column_names if any(marker in name.lower() for marker in forbidden_markers)}
    assert not offending, f"LLCContact must carry no auth-surface columns, found: {offending}"


def test_contact_model_has_no_foreign_key_or_relationship_to_users() -> None:
    """A column-name scan alone would pass a ``ForeignKey("users.id")`` column
    named e.g. ``owner_id`` — the single change that would actually make a
    contact resolvable as an auth identity via a join (#13969 review, cheap
    item). Assert on the schema-level constructs directly rather than
    trusting naming conventions.
    """
    assert (
        not LLCContact.__table__.foreign_keys
    ), f"LLCContact must have zero foreign keys, found: {LLCContact.__table__.foreign_keys}"
    mapper = inspect(LLCContact)
    user_relationships = [rel for rel in mapper.relationships if rel.mapper.class_.__name__ == "User"]
    assert not user_relationships, f"LLCContact must have no relationship targeting User, found: {user_relationships}"


# canonical: ignore py-adhoc-db-engine (test-local engine, in-memory only)
_SQLITE_MEMORY_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def engine() -> AsyncIterator:
    eng = create_async_engine(_SQLITE_MEMORY_URL)
    tables = [User.__table__, UserRole.__table__, Role.__table__, LLCContact.__table__]
    for table in tables:
        harness._scrub_pg_server_defaults(table)
        harness._rebind_enums_by_value(table)
        harness._clientside_timestamps(table)
    async with eng.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):  # noqa: ANN001, ANN201
    # canonical: ignore py-adhoc-db-engine (test-local session factory)
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


@pytest.mark.asyncio
async def test_contact_email_never_resolves_through_user_lookup(session_factory):  # noqa: ANN001
    """The reproduction: creating a contact must not make its email a login identity.

    Mutation-proof for this test lives in the PR verification output — making
    ``ContactService.create`` additionally ``session.add(User(email=...))``
    (the exact anti-pattern the issue forbids) turns this red.
    """
    company_id = uuid.uuid4()
    contact_email = "supplier@example.test"

    async with session_factory() as session:
        svc = ContactService()
        await svc.create(session, company_id, "Acme Supplier Contact", email=contact_email)
        await session.commit()

    async with session_factory() as session:
        user_svc = UserService(session)
        found = await user_svc.get_user_by_email(contact_email)
        authed = await user_svc.authenticate(contact_email, "any-password-whatsoever")

    assert found is None, "a contact's email resolved through the users table — it must never be a login identity"
    assert authed is None, "a contact must never be able to authenticate"


@pytest.mark.asyncio
async def test_a_real_user_with_a_different_email_is_unaffected(session_factory):  # noqa: ANN001
    """Guards against a fix that satisfies the predicate by breaking user lookup entirely."""
    async with session_factory() as session:
        session.add(
            User(
                id=uuid.uuid4(),
                email="real.employee@example.test",
                username="realemployee",
                display_name="Real Employee",
                is_active=True,
            )
        )
        await session.commit()

    async with session_factory() as session:
        user_svc = UserService(session)
        found = await user_svc.get_user_by_email("real.employee@example.test")

    assert found is not None
    assert found.email == "real.employee@example.test"
