# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#10200: the SLM's first admin is linked once, and only when nobody could already be them."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from user_management.models import AuditLog, Role, User
from user_management.models.base import Base
from user_management.models.person_link import PersonLink
from user_management.services import person_link_service as service

_PERSON = service.SlmPerson(uuid.uuid4(), "Root", "root@example.test", "Root", "$2b$hash")
_ADMIN_ROLE_ID = uuid.UUID(
    "a1b2c3d4-0000-4000-8000-00000000ad01"
)  # has hex letters: an all-digit id is stored as a number by SQLite


@compiles(JSONB, "sqlite")
def _compile_jsonb_as_json_on_sqlite(element, compiler, **kw):  # noqa: ANN001
    return "JSON"


@pytest_asyncio.fixture
async def session():
    """A real session on an in-memory database, so the checks run as the queries they are."""
    engine = create_async_engine("sqlite+aiosqlite://")  # canonical: ignore py-adhoc-db-engine (test-local, in-memory)
    async with engine.begin() as conn:
        tables = [User.__table__, Role.__table__, AuditLog.__table__, PersonLink.__table__]
        await conn.run_sync(Base.metadata.create_all, tables=tables)
    try:
        sessions = async_sessionmaker(bind=engine, expire_on_commit=False)  # canonical: ignore py-adhoc-db-engine
        async with sessions() as db:
            db.add(Role(id=_ADMIN_ROLE_ID, name="admin", is_system=True))  # the system role seed.py finds by name
            await db.flush()
            yield db
    finally:
        await engine.dispose()


async def _count(session, model) -> int:
    return (await session.execute(select(func.count()).select_from(model))).scalar_one()


async def _link(session, person=_PERSON):
    user = SimpleNamespace(id=uuid.uuid4(), password_hash="random")
    users = MagicMock()
    users.return_value.create_user = AsyncMock(return_value=user)
    with patch.object(service, "UserService", users):
        status = await service.link_first_slm_admin(session, person)
    return status, user, users.return_value.create_user


async def test_a_clean_install_links_the_admin_and_keeps_their_password_and_slm_id(session) -> None:
    status, user, create = await _link(session)
    create.assert_awaited_once()
    assert status == service.LINK_OK and user.password_hash == "$2b$hash"
    assert create.await_args.kwargs["is_platform_admin"] is True
    assert create.await_args.kwargs["role_ids"] == [
        _ADMIN_ROLE_ID
    ]  # the seeded admin role, found by find_admin_role_id
    link = (await session.execute(select(PersonLink))).scalar_one()
    assert (link.slm_user_id, link.user_id) == (_PERSON.id, user.id)


async def test_re_running_creates_nothing(session) -> None:
    session.add(PersonLink(slm_user_id=_PERSON.id, user_id=None))
    await session.flush()
    status, _, create = await _link(session)
    assert status == service.LINK_OK
    create.assert_not_awaited()


async def test_someone_who_may_be_this_person_is_never_matched_automatically(session) -> None:
    session.add(User(email="root@example.test", username="root", password_hash="x"))
    await session.flush()
    status, _, create = await _link(session)
    assert status == service.LINK_OK
    create.assert_not_awaited()
    assert await _count(session, PersonLink) == 0


async def test_an_slm_without_an_admin_links_nothing(session) -> None:
    status, _, create = await _link(session, person=None)
    assert status == service.LINK_OK
    create.assert_not_awaited()
    assert await _count(session, PersonLink) == 0


async def test_a_404_from_the_slm_says_so_in_the_log() -> None:
    """A proxy's 404 reads the same as no admin, and seeding follows, so it must not be silent."""
    response = MagicMock(status=404)
    context = MagicMock(
        __aenter__=AsyncMock(return_value=response),
        __aexit__=AsyncMock(return_value=False),
    )
    http = MagicMock(get=MagicMock(return_value=context))
    client = MagicMock(_get_session=AsyncMock(return_value=http), _rest_url=lambda path: f"https://slm{path}")
    with (
        patch("services.slm_client.get_slm_client", return_value=client),
        patch.object(service, "assert_egress_policy", AsyncMock()),
        patch.object(service, "internal_api_key", return_value="k"),
        patch.object(service, "logger") as logger,
    ):
        assert await service.fetch_first_slm_admin() is None
    logger.warning.assert_called_once()


def _slm_client(status: int):
    response = MagicMock(status=status)
    context = MagicMock(__aenter__=AsyncMock(return_value=response), __aexit__=AsyncMock(return_value=False))
    http = MagicMock(get=MagicMock(return_value=context))
    client = MagicMock(_get_session=AsyncMock(return_value=http), _rest_url=lambda path: f"https://slm{path}")
    return client, http


async def test_a_missing_internal_key_is_an_error_and_sends_nothing() -> None:
    client, http = _slm_client(200)
    with (
        patch("services.slm_client.get_slm_client", return_value=client),
        patch.object(service, "assert_egress_policy", AsyncMock()),
        patch.object(service, "internal_api_key", return_value=""),
        patch.object(service, "logger") as logger,
    ):
        with pytest.raises(service.FirstAdminLinkError) as raised:
            await service.fetch_first_slm_admin()
    assert raised.value.status == service.LINK_KEY_MISSING
    http.get.assert_not_called()
    logger.error.assert_called_once()


async def test_a_403_from_the_slm_is_reported_as_an_error() -> None:
    client, http = _slm_client(403)
    with (
        patch("services.slm_client.get_slm_client", return_value=client),
        patch.object(service, "assert_egress_policy", AsyncMock()),
        patch.object(service, "internal_api_key", return_value="k"),
        patch.object(service, "logger") as logger,
    ):
        with pytest.raises(service.FirstAdminLinkError) as raised:
            await service.fetch_first_slm_admin()
    assert raised.value.status == service.LINK_REFUSED
    assert http.get.call_args.kwargs["headers"] == {"X-Internal-API-Key": "k"}
    logger.error.assert_called_once()


async def test_startup_returns_the_failure_status_and_records_it() -> None:
    err = service.FirstAdminLinkError("x", service.LINK_KEY_MISSING)
    with patch.object(service, "fetch_first_slm_admin", AsyncMock(side_effect=err)):
        assert await service.link_first_slm_admin_at_startup() == service.LINK_KEY_MISSING
    assert service.last_link_status == service.LINK_KEY_MISSING


async def test_an_slm_admin_without_a_password_hash_is_not_linked(session) -> None:
    """Linking would create an admin who cannot log in and would stop default-admin seeding."""
    no_hash = service.SlmPerson(uuid.uuid4(), "Root", "root@example.test", "Root", None)
    status, _user, create_user = await _link(session, no_hash)
    assert status == service.LINK_NO_HASH
    create_user.assert_not_awaited()
