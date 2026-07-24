# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Issue #12293: backend must not silently crash-loop on DB credential misconfig.

Pins init_database()'s fail-fast vs bounded-retry behaviour:

* A *permanent* credential/authorization error (bad password, missing role,
  missing database) fails fast with ZERO retries and a clear RuntimeError —
  retrying can never help, so the process exits with a distinct signal instead
  of looping forever.
* A *transient* error (DB still coming up) is retried a BOUNDED number of times
  and then either succeeds or gives up with a clear RuntimeError.
"""

import types
from unittest.mock import AsyncMock

import pytest

import user_management.database as db


def _fake_config():
    """Minimal stand-in for DeploymentConfig with postgres enabled."""
    return types.SimpleNamespace(
        mode=types.SimpleNamespace(value="single_company"),
        postgres_enabled=True,
        postgres_host="db-host",
        postgres_port=5432,
        postgres_db="autobot",
        postgres_user="autobot_app",
    )


class _AuthError(Exception):
    """Stand-in for asyncpg.InvalidPasswordError (SQLSTATE 28P01)."""

    sqlstate = "28P01"


class TestPermanentErrorClassification:
    def test_auth_sqlstate_is_permanent(self):
        assert db._is_permanent_db_error(_AuthError("password authentication failed")) is True

    def test_wrapped_auth_error_is_permanent(self):
        # SQLAlchemy-style wrapping: OperationalError -> asyncpg error via __cause__.
        try:
            try:
                raise _AuthError("password authentication failed for user")
            except _AuthError as inner:
                raise RuntimeError("(sqlalchemy) connect failed") from inner
        except RuntimeError as wrapped:
            assert db._is_permanent_db_error(wrapped) is True

    def test_invalid_catalog_is_permanent(self):
        class _NoDb(Exception):
            sqlstate = "3D000"

        assert db._is_permanent_db_error(_NoDb("database does not exist")) is True

    def test_connection_refused_is_transient(self):
        assert db._is_permanent_db_error(ConnectionRefusedError("connection refused")) is False

    def test_timeout_is_transient(self):
        assert db._is_permanent_db_error(TimeoutError("timed out")) is False


class TestInitDatabaseFailFast:
    @pytest.mark.asyncio
    async def test_permanent_error_fails_fast_no_retry(self, monkeypatch):
        monkeypatch.setattr(db, "get_deployment_config", _fake_config)
        monkeypatch.setattr(db, "_DB_INIT_MAX_ATTEMPTS", 5)
        monkeypatch.setattr(db, "_DB_INIT_RETRY_DELAY_SECONDS", 0.0)

        verify = AsyncMock(side_effect=_AuthError("password authentication failed for user"))
        monkeypatch.setattr(db, "_verify_postgres_connection", verify)
        sleep = AsyncMock()
        monkeypatch.setattr(db.asyncio, "sleep", sleep)

        with pytest.raises(RuntimeError) as exc:
            await db.init_database()

        # Fail fast: exactly one attempt, no sleeps, and a credential-naming message.
        assert verify.await_count == 1
        assert sleep.await_count == 0
        msg = str(exc.value).lower()
        assert "credential" in msg or "authorization" in msg
        assert "autobot_app" in str(exc.value)

    @pytest.mark.asyncio
    async def test_transient_error_retries_then_succeeds(self, monkeypatch):
        monkeypatch.setattr(db, "get_deployment_config", _fake_config)
        monkeypatch.setattr(db, "_DB_INIT_MAX_ATTEMPTS", 5)
        monkeypatch.setattr(db, "_DB_INIT_RETRY_DELAY_SECONDS", 0.0)

        # Fail transiently twice, then succeed on the third attempt.
        verify = AsyncMock(
            side_effect=[
                ConnectionRefusedError("connection refused"),
                ConnectionRefusedError("connection refused"),
                None,
            ]
        )
        monkeypatch.setattr(db, "_verify_postgres_connection", verify)
        sleep = AsyncMock()
        monkeypatch.setattr(db.asyncio, "sleep", sleep)

        await db.init_database()  # must NOT raise

        assert verify.await_count == 3
        assert sleep.await_count == 2  # one sleep between each of the two failures

    @pytest.mark.asyncio
    async def test_transient_error_bounded_then_gives_up(self, monkeypatch):
        monkeypatch.setattr(db, "get_deployment_config", _fake_config)
        monkeypatch.setattr(db, "_DB_INIT_MAX_ATTEMPTS", 3)
        monkeypatch.setattr(db, "_DB_INIT_RETRY_DELAY_SECONDS", 0.0)

        verify = AsyncMock(side_effect=ConnectionRefusedError("connection refused"))
        monkeypatch.setattr(db, "_verify_postgres_connection", verify)
        sleep = AsyncMock()
        monkeypatch.setattr(db.asyncio, "sleep", sleep)

        with pytest.raises(RuntimeError) as exc:
            await db.init_database()

        # Bounded: exactly MAX attempts, not infinite; clear "unreachable" signal.
        assert verify.await_count == 3
        assert sleep.await_count == 2  # no sleep after the final failing attempt
        assert "unreachable" in str(exc.value).lower()

    @pytest.mark.asyncio
    async def test_postgres_disabled_is_noop(self, monkeypatch):
        cfg = _fake_config()
        cfg.postgres_enabled = False
        monkeypatch.setattr(db, "get_deployment_config", lambda: cfg)

        verify = AsyncMock()
        monkeypatch.setattr(db, "_verify_postgres_connection", verify)

        await db.init_database()  # returns immediately
        assert verify.await_count == 0
