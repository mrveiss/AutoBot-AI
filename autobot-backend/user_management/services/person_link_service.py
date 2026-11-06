# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Link the SLM's first admin to a main-app user when the main app is installed (#10200).

Only a clean case links by itself: no link yet and nobody in the main store who could already be
this person. Anything else is a match a human has to approve (#17038), so it is left unlinked.
Company membership follows from the company: whoever creates it becomes its owner, and a fresh
install has none yet.
"""

import secrets
import uuid
from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.http_egress_guard import assert_egress_policy
from autobot_shared.logging_manager import get_logger
from autobot_shared.node_proxy import internal_api_key
from user_management.models import User
from user_management.models.person_link import PersonLink
from user_management.services.base_service import TenantContext
from user_management.services.seed import find_admin_role_id
from user_management.services.user_service import UserService

logger = get_logger(__name__)

_FIRST_ADMIN_PATH = "/api/internal/first-admin"

LINK_OK = "ok"  # linked, already linked, or left for a person to match
LINK_FAILED = "failed"  # the SLM could not be read; the admin is NOT linked and seeding follows
LINK_KEY_MISSING = "internal_key_missing"  # no internal API key configured; nothing was sent
LINK_REFUSED = "slm_refused_internal_key"  # the SLM answered 403: its key differs from ours

last_link_status: str | None = None  # read by callers and the admin UI; None until startup ran


class FirstAdminLinkError(RuntimeError):
    """The SLM's first admin could not be read; carries the status a caller reports."""

    def __init__(self, message: str, status: str) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class SlmPerson:
    id: uuid.UUID
    username: str
    email: str
    display_name: str | None
    password_hash: str | None


async def fetch_first_slm_admin() -> SlmPerson | None:
    """The SLM's first admin. None if the SLM has none yet; raises if it cannot be read."""
    from services.slm_client import get_slm_client

    client = get_slm_client()
    if client is None:
        raise RuntimeError("SLM control link is not initialised")
    session = await client._get_session()
    url = client._rest_url(_FIRST_ADMIN_PATH)
    await assert_egress_policy(url)
    key = internal_api_key()
    if not key:  # never send an empty header: the SLM answers 403 and the link is skipped unseen
        message = "Person link: no internal API key is configured, so the SLM's first admin cannot be read"
        logger.error(message)
        raise FirstAdminLinkError(message, LINK_KEY_MISSING)
    async with session.get(url, headers={"X-Internal-API-Key": key}, allow_redirects=False) as response:
        if response.status == 403:
            message = "Person link: the SLM refused the internal API key (403); backend and SLM keys differ"
            logger.error(message)
            raise FirstAdminLinkError(message, LINK_REFUSED)
        if response.status == 404:  # logged: a misrouted 404 looks the same, and seeding follows
            logger.warning("Person link: the SLM answered 404 for its first admin; treating it as none yet")
            return None
        response.raise_for_status()
        data = await response.json()
    return SlmPerson(
        id=uuid.UUID(data["id"]),
        username=data["username"],
        email=data["email"],
        display_name=data.get("display_name"),
        password_hash=data.get("password_hash"),
    )


async def _main_store_may_hold_them(session: AsyncSession, person: SlmPerson) -> bool:
    query = select(User.id).where(
        User.deleted_at.is_(None),
        or_(
            User.is_platform_admin.is_(True),
            User.username == person.username.lower(),
            User.email == person.email.lower(),
        ),
    )
    return (await session.execute(query.limit(1))).first() is not None


async def _create_linked_admin(session: AsyncSession, person: SlmPerson) -> User:
    """Create the main-app user with the SLM's hash, so this person keeps their password."""
    role_id = await find_admin_role_id(session)  # the seeded system role, found once in seed.py
    user = await UserService(session=session, context=TenantContext()).create_user(
        email=person.email,
        username=person.username,
        password=secrets.token_urlsafe(32),  # replaced below; create_user takes no hash
        display_name=person.display_name,
        is_platform_admin=True,
        role_ids=[role_id] if role_id else None,
    )
    user.password_hash = person.password_hash
    session.add(PersonLink(slm_user_id=person.id, user_id=user.id))
    await session.flush()
    return user


async def link_first_slm_admin(session: AsyncSession, person: SlmPerson | None) -> bool:
    """Create and link the main-app user for *person*; True if it did. Re-running creates nothing."""
    if person is None or (await session.execute(select(PersonLink.id).limit(1))).first() is not None:
        return False
    if await _main_store_may_hold_them(session, person):
        logger.warning("Person link: %s may already be a main-app user; left for a person to match", person.username)
        return False
    if not person.password_hash:  # a linked admin with no hash can't log in, and linking stops default-admin seeding
        logger.error(
            "Person link: SLM admin %s has no password hash; left unlinked so seeding keeps a usable admin",
            person.username,
        )
        return False
    user = await _create_linked_admin(session, person)
    logger.info("Person link: SLM admin %s linked to main-app user %s", person.username, user.id)
    return True


async def link_first_slm_admin_at_startup() -> str:
    """Its own transaction: all of the link or none of it, and a failure can't touch seeding's session.

    An unreachable SLM must not stop the main app starting; seeding still runs. The outcome is
    returned and kept in ``last_link_status``; every failure is logged at error level.
    """
    global last_link_status
    from user_management.database import get_async_session_factory

    status = LINK_OK
    try:
        person = await fetch_first_slm_admin()
        async with get_async_session_factory()() as session, session.begin():
            await link_first_slm_admin(session, person)
    except FirstAdminLinkError as exc:  # already logged at error level where it was raised
        status = exc.status
    except Exception as exc:
        status = LINK_FAILED
        logger.error("Person link: could not link the SLM's first admin: %s", type(exc).__name__)
    last_link_status = status
    return status
