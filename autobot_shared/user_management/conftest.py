# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A seeded in-memory RBAC database for the #18259 role-permission tests.

The four RBAC tables are copied onto a PRIVATE ``MetaData`` with stub
``organizations``/``users`` tables for their foreign keys, so nothing is added to
the shared ``Base.metadata`` (each service maps its own concrete ``users`` table
there, and a stub would collide with it later in the same interpreter).
"""

import uuid
from dataclasses import dataclass, field

import pytest_asyncio
from sqlalchemy import Boolean, Column, MetaData, String, Table, Uuid, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from autobot_shared.user_management.models.role import Permission, Role, RolePermission, UserRole


@dataclass
class GrantDb:
    """A session on the seeded database plus the ids the seed created."""

    session: AsyncSession
    roles: dict[str, uuid.UUID] = field(default_factory=dict)
    users: dict[str, uuid.UUID] = field(default_factory=dict)

    async def add_role(
        self, name: str, permissions: list[str], org_id: uuid.UUID | None = None, is_system: bool | None = None
    ) -> uuid.UUID:
        """Insert a role granting *permissions* (each created if new); system unless it has an org."""
        role_id = uuid.uuid4()
        system = org_id is None if is_system is None else is_system
        await self.session.execute(
            Role.__table__.insert().values(id=role_id, name=name, org_id=org_id, is_system=system, priority=0)
        )
        for perm_name in permissions:
            perm_id = await self._permission_id(perm_name)
            await self.session.execute(RolePermission.__table__.insert().values(role_id=role_id, permission_id=perm_id))
        self.roles[name] = role_id
        return role_id

    async def _permission_id(self, name: str) -> uuid.UUID:
        table = Permission.__table__
        found = (await self.session.execute(table.select().where(table.c.name == name))).first()
        if found:
            return found.id
        perm_id = uuid.uuid4()
        resource, _, action = name.partition(":")
        await self.session.execute(table.insert().values(id=perm_id, name=name, resource=resource, action=action))
        return perm_id

    async def add_sso_link(self, username: str, *, admin: bool, provider: str = "corp-idp") -> uuid.UUID:
        """Insert a user, a provider and an SSO link between them; returns the link id."""
        user_id, provider_id, link_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        await self.session.execute(
            text("INSERT INTO users (id, username, is_platform_admin) VALUES (:i, :u, :a)"),
            {"i": user_id.hex, "u": username, "a": admin},
        )
        await self.session.execute(
            text("INSERT INTO sso_providers (id, name, provider_type) VALUES (:i, :n, 'oauth2')"),
            {"i": provider_id.hex, "n": provider},
        )
        await self.session.execute(
            text("INSERT INTO user_sso_links (id, user_id, provider_id) VALUES (:i, :u, :p)"),
            {"i": link_id.hex, "u": user_id.hex, "p": provider_id.hex},
        )
        return link_id

    async def add_user(self, name: str, role_names: list[str]) -> uuid.UUID:
        """Assign the named roles to a fresh user id."""
        user_id = uuid.uuid4()
        for role_name in role_names:
            await self.session.execute(
                UserRole.__table__.insert().values(user_id=user_id, role_id=self.roles[role_name])
            )
        self.users[name] = user_id
        return user_id


def _private_metadata() -> MetaData:
    metadata = MetaData()
    Table("organizations", metadata, Column("id", Uuid, primary_key=True))
    Table(
        "users",
        metadata,
        Column("id", Uuid, primary_key=True),
        Column("username", String(100)),
        Column("is_platform_admin", Boolean, default=False),
    )
    # SSO tables reduced to the columns the admin-link audit reads (#18338); the real
    # ones carry JSONB, which SQLite cannot create.
    Table("sso_providers", metadata, Column("id", Uuid, primary_key=True), Column("name", String(100)),
          Column("provider_type", String(50)))  # fmt: skip
    Table("user_sso_links", metadata, Column("id", Uuid, primary_key=True), Column("user_id", Uuid),
          Column("provider_id", Uuid))  # fmt: skip
    for model in (Permission, Role, RolePermission, UserRole):
        model.__table__.to_metadata(metadata)
    return metadata


@pytest_asyncio.fixture
async def grant_db():
    """An empty RBAC schema in in-memory SQLite, one session, rolled back after."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(_private_metadata().create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        yield GrantDb(session)
        await session.rollback()
    await engine.dispose()
