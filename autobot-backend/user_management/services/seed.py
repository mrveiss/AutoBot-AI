# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Default admin seed function (#10199, epic #10193).

Seeds a real admin account into ``autobot_users`` at startup from the
operator-configured password (``AUTOBOT_ADMIN_PASSWORD``).

Guards:
- Skipped when ``AUTOBOT_ADMIN_PASSWORD`` is not set (no default shipped).
- Idempotent: skipped when any ``is_platform_admin=True`` user or a user
  with the configured username already exists.
"""

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import get_config
from user_management.models import Role, User
from user_management.services.base_service import TenantContext
from user_management.services.user_service import DuplicateUserError, UserService

logger = get_logger(__name__)

_ADMIN_ROLE_NAME = "admin"


async def _find_admin_role_id(session: AsyncSession):
    """Return the UUID of the system 'admin' role, or None if not yet seeded."""
    result = await session.execute(select(Role).where(Role.name == _ADMIN_ROLE_NAME, Role.is_system.is_(True)))
    role = result.scalar_one_or_none()
    return role.id if role is not None else None


async def _any_admin_exists(session: AsyncSession, username: str) -> bool:
    """
    Return True when seeding should be skipped:
    - any is_platform_admin=True user exists (regardless of username), OR
    - a user with the configured admin username exists (non-admin duplicate).
    """
    result = await session.execute(
        select(User)
        .where(
            or_(
                User.is_platform_admin.is_(True),
                User.username == username.lower(),
            )
        )
        .where(User.deleted_at.is_(None))
    )
    return result.scalar_one_or_none() is not None


async def seed_default_admin(session: AsyncSession) -> None:
    """
    Seed a default platform-admin user from ``AUTOBOT_ADMIN_PASSWORD`` (#10199).

    Must be called inside an open ``AsyncSession`` that belongs to a live
    Postgres-backed transaction (caller responsibility — see lifespan.py).

    Behaviour:
    - No configured password → warn and return.
    - Admin already exists → info log and return (idempotent).
    - Otherwise → create via UserService with ``is_platform_admin=True`` and
      the system 'admin' role assigned.
    """
    cfg = get_config()
    password = cfg.auth.admin_password
    username = cfg.auth.admin_username or "admin"

    if not password:
        logger.warning(
            "Admin seed: AUTOBOT_ADMIN_PASSWORD is not set — "
            "no default admin account will be created. "
            "Set this env var to seed an admin on first boot."
        )
        return

    if await _any_admin_exists(session, username):
        logger.info(
            "Admin seed: admin user or username '%s' already exists — skipping (idempotent).",
            username,
        )
        return

    admin_role_id = await _find_admin_role_id(session)
    role_ids = [admin_role_id] if admin_role_id is not None else None
    if admin_role_id is None:
        logger.warning(
            "Admin seed: system 'admin' role not found in DB — " "admin user will be created without a role assignment."
        )

    svc = UserService(session=session, context=TenantContext())
    try:
        user = await svc.create_user(
            email=f"{username}@autobot.local",
            username=username,
            password=password,
            display_name="Administrator",
            is_platform_admin=True,
            role_ids=role_ids,
        )
        logger.info(
            "Admin seed: created default admin user '%s' (id=%s).",
            username,
            user.id,
        )
    except DuplicateUserError:
        logger.info(
            "Admin seed: '%s' already exists (race/duplicate) — skipping.",
            username,
        )
