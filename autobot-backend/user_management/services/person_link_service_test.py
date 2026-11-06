# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#10200: the SLM's first admin is linked once, and only when nobody could already be them."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from user_management.services import person_link_service as service

_PERSON = service.SlmPerson(uuid.uuid4(), "Root", "root@example.test", "Root", "$2b$hash")


def _session(*firsts) -> MagicMock:
    """Each execute answers .first() with the next value."""
    session = MagicMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock(side_effect=[MagicMock(first=MagicMock(return_value=v)) for v in firsts])
    return session


async def _link(session, person=_PERSON):
    user = SimpleNamespace(id=uuid.uuid4(), password_hash="random")
    users = MagicMock()
    users.return_value.create_user = AsyncMock(return_value=user)
    with patch.object(service, "UserService", users):
        linked = await service.link_first_slm_admin(session, person)
    return linked, user, users.return_value.create_user


async def test_a_clean_install_links_the_admin_and_keeps_their_password_and_slm_id() -> None:
    session = _session(None, None, SimpleNamespace(id=uuid.uuid4()))
    linked, user, create = await _link(session)
    assert linked is True and user.password_hash == "$2b$hash"
    assert create.await_args.kwargs["is_platform_admin"] is True
    link = session.add.call_args.args[0]
    assert (link.slm_user_id, link.user_id) == (_PERSON.id, user.id)


async def test_re_running_creates_nothing() -> None:
    session = _session(SimpleNamespace(id=uuid.uuid4()))
    linked, _, create = await _link(session)
    assert linked is False
    create.assert_not_awaited()


async def test_someone_who_may_be_this_person_is_never_matched_automatically() -> None:
    session = _session(None, SimpleNamespace(id=uuid.uuid4()))
    linked, _, create = await _link(session)
    assert linked is False
    create.assert_not_awaited()
    session.add.assert_not_called()


async def test_an_slm_without_an_admin_links_nothing() -> None:
    session = _session()
    linked, _, _ = await _link(session, person=None)
    assert linked is False
    session.execute.assert_not_awaited()


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
        patch.object(service, "logger") as logger,
    ):
        assert await service.fetch_first_slm_admin() is None
    logger.warning.assert_called_once()
