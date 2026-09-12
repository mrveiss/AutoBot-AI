# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Hard-deleting a user, or an organization, no longer 500s (#16464).

Before this migration, ``terminal_activities``/``file_activities``/
``browser_activities``/``desktop_activities``/``secret_usage`` all declared
``ForeignKey("users.id", ondelete="CASCADE")`` in the ORM (models/activities.py)
but the tables themselves did not exist on any properly-migrated database (the
orphaned database/migrations/ chain, never applied). Deleting a user with a
CASCADE constraint pointing at a nonexistent table raises
``UndefinedTableError`` -- not "no rows to cascade", a hard failure, because
Postgres cannot even evaluate whether the missing table has matching rows.

Organizations compound this: ``users.org_id`` is itself
``ForeignKey("organizations.id", ondelete="CASCADE")``
(migrations/versions/20251224_001_initial_user_management.py), so deleting an
organization cascades into its member users, which cascades again into the
same missing tables. One organization delete, two layers of the same defect.

Raw SQL throughout (not the ORM) so this test exercises exactly what a hard
delete does at the database level, independent of any ORM relationship
mapping gaps on the Python side.
"""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.migrations.conftest import requires_postgres, run_alembic

pytestmark = [pytest.mark.migration_gate, requires_postgres]

_ACTIVITY_TABLES = (
    "terminal_activities",
    "file_activities",
    "browser_activities",
    "desktop_activities",
)

#: A value for each column type a required activity column may have. A NOT NULL
#: column of any other type fails ``_required_columns`` by name, so a column a
#: future migration makes required is noticed here, never silently left out.
_PLACEHOLDER_BY_TYPE = {
    "text": "cascade-test",
    "character varying": "cascade-test",
}


async def _required_columns(conn, table: str) -> dict:
    """Every NOT NULL column of *table* without a default, bar ``user_id``, with a placeholder.

    Read from the migrated schema itself -- the only thing the INSERT has to
    satisfy -- so the fixture follows whatever the migration declares.
    """
    result = await conn.execute(
        text(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = :table "
            "AND is_nullable = 'NO' AND column_default IS NULL AND column_name <> 'user_id'"
        ),
        {"table": table},
    )
    required = {}
    for name, data_type in result:
        assert data_type in _PLACEHOLDER_BY_TYPE, f"{table}.{name} is NOT NULL ({data_type}); add a placeholder"
        required[name] = _PLACEHOLDER_BY_TYPE[data_type]
    return required


async def _insert_activity(conn, table: str, user_id: uuid.UUID) -> None:
    """Insert one *table* row for *user_id*, supplying every column the schema requires."""
    required = await _required_columns(conn, table)
    columns = ", ".join(["user_id", *required])
    values = ", ".join([":user_id", *(f":{name}" for name in required)])
    # No caller input: the table is a literal from this module, the columns come from information_schema.
    statement = text(f"INSERT INTO {table} ({columns}) VALUES ({values})")  # nosec B608
    await conn.execute(statement, {"user_id": user_id, **required})


async def test_hard_deleting_a_user_cascades_through_every_orphaned_table(fresh_db_url):
    assert run_alembic(["upgrade", "head"], fresh_db_url).returncode == 0
    engine = create_async_engine(fresh_db_url)
    try:
        user_id = uuid.uuid4()
        secret_id = uuid.uuid4()

        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO users (id, email, username, is_active, is_verified, "
                    "mfa_enabled, is_platform_admin) "
                    "VALUES (:id, :email, :username, true, false, false, false)"
                ),
                {"id": user_id, "email": "cascade-test@example.com", "username": "cascade-test"},
            )
            for table in _ACTIVITY_TABLES:
                await _insert_activity(conn, table, user_id)
            await conn.execute(
                text(
                    "INSERT INTO secret_usage "
                    "(id, secret_id, user_id, activity_type, activity_id) "
                    "VALUES (gen_random_uuid(), :secret_id, :user_id, 'terminal', gen_random_uuid())"
                ),
                {"secret_id": secret_id, "user_id": user_id},
            )
            await conn.execute(
                text("INSERT INTO session_collaborations (session_id, owner_id) " "VALUES (:session_id, :user_id)"),
                {"session_id": f"chat-{user_id.hex[:16]}", "user_id": user_id},
            )

        # The hard delete itself: exactly what a real admin hard-delete does
        # (OrganizationService/UserService: session.delete(user), no manual
        # pre-cleanup of related rows -- the CASCADE constraint is the cleanup).
        async with engine.begin() as conn:
            await conn.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})

        async with engine.connect() as conn:
            for table in _ACTIVITY_TABLES + ("secret_usage",):
                query = text(f"SELECT count(*) FROM {table} WHERE user_id = :id")  # nosec B608
                count = (await conn.execute(query, {"id": user_id})).scalar()
                assert count == 0, f"{table} row survived the cascade delete"

            collab_count = (
                await conn.execute(
                    text("SELECT count(*) FROM session_collaborations WHERE owner_id = :id"),
                    {"id": user_id},
                )
            ).scalar()
            assert collab_count == 0, "session_collaborations row survived the cascade delete"
    finally:
        await engine.dispose()


async def test_hard_deleting_an_organization_cascades_through_its_users_and_their_activity(fresh_db_url):
    assert run_alembic(["upgrade", "head"], fresh_db_url).returncode == 0
    engine = create_async_engine(fresh_db_url)
    try:
        org_id = uuid.uuid4()
        user_id = uuid.uuid4()

        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO organizations (id, name, slug, max_users, is_active) "
                    "VALUES (:id, :name, :slug, -1, true)"
                ),
                {"id": org_id, "name": "cascade-test-org", "slug": f"cascade-test-org-{org_id.hex[:8]}"},
            )
            await conn.execute(
                text(
                    "INSERT INTO users (id, org_id, email, username, is_active, is_verified, "
                    "mfa_enabled, is_platform_admin) "
                    "VALUES (:id, :org_id, :email, :username, true, false, false, false)"
                ),
                {
                    "id": user_id,
                    "org_id": org_id,
                    "email": "cascade-org-test@example.com",
                    "username": "cascade-org-test",
                },
            )
            await _insert_activity(conn, "terminal_activities", user_id)

        # organization -> user (users.org_id CASCADE) -> activity row
        # (terminal_activities.user_id CASCADE): one delete, two cascade hops,
        # both through tables this PR ports.
        async with engine.begin() as conn:
            await conn.execute(text("DELETE FROM organizations WHERE id = :id"), {"id": org_id})

        async with engine.connect() as conn:
            user_count = (
                await conn.execute(text("SELECT count(*) FROM users WHERE id = :id"), {"id": user_id})
            ).scalar()
            assert user_count == 0, "user row survived the organization cascade delete"

            activity_count = (
                await conn.execute(
                    text("SELECT count(*) FROM terminal_activities WHERE user_id = :id"), {"id": user_id}
                )
            ).scalar()
            assert activity_count == 0, "terminal_activities row survived the two-hop cascade delete"
    finally:
        await engine.dispose()
