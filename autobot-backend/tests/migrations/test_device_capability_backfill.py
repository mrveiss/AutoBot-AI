# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Migration 20260824_084 backfills paired devices DENIED (#14964).

The whole risk of per-credential capability scoping is the backfill default: a
grant would silently convert every already-paired device into a full-control
credential, which is strictly worse than not having the feature. This test
creates a device row **while the column does not exist yet** -- upgrading only
as far as the preceding revision -- then upgrades and asserts the row cannot
exercise a single capability.

Flipping the migration's ``server_default`` to a grant, or adding a backfill
``UPDATE`` that hands out capabilities, fails here.
"""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.migrations.conftest import requires_postgres, run_alembic

pytestmark = [pytest.mark.migration_gate, requires_postgres]

_BEFORE = "20260823_083"
_THIS = "20260824_084"
_TABLE = "desktop_mobile_devices"
_NEW_COLUMNS = ("permissions", "is_approved", "revoked_at")


async def _insert_pre_migration_device(engine, device_id: uuid.UUID) -> None:
    """Insert a paired device using only the columns that existed before 084."""
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO desktop_mobile_devices "
                "(id, user_id, device_name, device_token, platform, created_at) "
                "VALUES (:id, :user_id, :name, :token, :platform, NOW())"
            ),
            {
                "id": device_id,
                "user_id": "alice",
                "name": "alice-phone",
                # Ciphertext-shaped placeholder; this column is never decrypted here.
                "token": "not-a-real-token",
                "platform": "ios",
            },
        )


async def test_a_device_paired_before_the_column_existed_is_denied_everything(fresh_db_url):
    assert run_alembic(["upgrade", _BEFORE], fresh_db_url).returncode == 0

    engine = create_async_engine(fresh_db_url)
    device_id = uuid.uuid4()
    try:
        async with engine.connect() as conn:
            present = await conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = :t AND column_name = ANY(:cols)"
                ),
                {"t": _TABLE, "cols": list(_NEW_COLUMNS)},
            )
            assert present.scalars().all() == [], (
                "the capability columns already exist at the revision before 084 -- "
                "this test would then prove nothing about the backfill"
            )

        await _insert_pre_migration_device(engine, device_id)

        assert run_alembic(["upgrade", _THIS], fresh_db_url).returncode == 0

        async with engine.connect() as conn:
            row = (
                await conn.execute(
                    text("SELECT permissions, is_approved, revoked_at " "FROM desktop_mobile_devices WHERE id = :id"),
                    {"id": device_id},
                )
            ).one()

        permissions, is_approved, revoked_at = row
        assert permissions == "[]", f"pre-migration device was backfilled with grants: {permissions!r}"
        assert is_approved is False, "pre-migration device was backfilled approved"
        assert revoked_at is None

        # The migration's own value is not enough: the production predicate has
        # to agree that this row exercises nothing.
        from autobot_shared.auth.device_capabilities import DeviceCapability, capability_granted

        assert list(DeviceCapability), "the capability enumeration is empty -- the loop below asserts nothing"
        for capability in DeviceCapability:
            assert (
                capability_granted(
                    capability=capability,
                    permissions_raw=permissions,
                    is_approved=is_approved,
                    revoked_at=revoked_at,
                )
                is False
            ), f"a device paired before 084 can exercise {capability.value}"
    finally:
        await engine.dispose()


async def test_downgrade_restores_the_pre_084_shape_and_keeps_the_row(fresh_db_url):
    """The migration is reversible and loses no data that predates it."""
    assert run_alembic(["upgrade", _THIS], fresh_db_url).returncode == 0

    engine = create_async_engine(fresh_db_url)
    device_id = uuid.uuid4()
    try:
        await _insert_pre_migration_device(engine, device_id)

        assert run_alembic(["downgrade", _BEFORE], fresh_db_url).returncode == 0

        async with engine.connect() as conn:
            remaining = await conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = :t AND column_name = ANY(:cols)"
                ),
                {"t": _TABLE, "cols": list(_NEW_COLUMNS)},
            )
            assert remaining.scalars().all() == [], "downgrade left one of its own columns behind"

            survivors = await conn.execute(
                text("SELECT user_id, device_name, platform FROM desktop_mobile_devices WHERE id = :id"),
                {"id": device_id},
            )
            assert survivors.one() == ("alice", "alice-phone", "ios"), "downgrade dropped or orphaned the device row"

        # Re-upgrading lands back on DENY, never on a grant nobody re-authorised.
        assert run_alembic(["upgrade", _THIS], fresh_db_url).returncode == 0
        async with engine.connect() as conn:
            permissions = (
                await conn.execute(
                    text("SELECT permissions FROM desktop_mobile_devices WHERE id = :id"),
                    {"id": device_id},
                )
            ).scalar()
        assert permissions == "[]"
    finally:
        await engine.dispose()
