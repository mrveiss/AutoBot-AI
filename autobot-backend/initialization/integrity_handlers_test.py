# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The integrity floor answers for every router, and overrides none (#15775).

The second half is the one worth writing: a shared handler that swallowed the
per-site answers would silently revert #15736, #15752 and #15772, and it would
do it while every test asserting "409 on a duplicate" still passed -- because
the status would still be 409, just without the field that tells the caller
*which* value collided.
"""

from __future__ import annotations

import sqlite3

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.exc import DataError, IntegrityError

from initialization.integrity_handlers import register_integrity_handlers


class _PsycopgLike(Exception):
    def __init__(self, sqlstate: str) -> None:
        super().__init__(f'duplicate key value violates unique constraint "users_email_key" ({sqlstate})')
        self.sqlstate = sqlstate


def _sqlite_unique_error() -> sqlite3.IntegrityError:
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE TABLE users (email TEXT UNIQUE)")
    connection.execute("INSERT INTO users VALUES ('a@b')")
    with pytest.raises(sqlite3.IntegrityError) as exc:
        connection.execute("INSERT INTO users VALUES ('a@b')")
    return exc.value


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    register_integrity_handlers(app)

    @app.get("/unique-pg")
    async def _unique_pg():
        raise IntegrityError("INSERT ...", {}, _PsycopgLike("23505"))

    @app.get("/foreign-key-pg")
    async def _foreign_key_pg():
        raise IntegrityError("INSERT ...", {}, _PsycopgLike("23503"))

    @app.get("/unique-sqlite")
    async def _unique_sqlite():
        raise _sqlite_unique_error()

    @app.get("/malformed-uuid")
    async def _malformed_uuid():
        raise DataError("SELECT ...", {}, _PsycopgLike("22P02"))

    @app.get("/handled-by-the-route")
    async def _handled_by_the_route():
        """A route that already knows which field collided keeps saying so."""
        try:
            raise IntegrityError("INSERT ...", {}, _PsycopgLike("23505"))
        except IntegrityError:
            raise HTTPException(status_code=409, detail="A user with this email already exists")

    return TestClient(app, raise_server_exceptions=False)


class TestTheFloor:
    def test_unique_violation_is_409(self, client: TestClient):
        response = client.get("/unique-pg")

        assert response.status_code == 409
        assert response.json()["detail"] == "A resource with these values already exists"

    def test_foreign_key_violation_is_422(self, client: TestClient):
        assert client.get("/foreign-key-pg").status_code == 422

    def test_sqlite_unique_violation_is_409_too(self, client: TestClient):
        """The dialect CI actually runs on must reach the same answer."""
        assert client.get("/unique-sqlite").status_code == 409

    def test_malformed_value_is_422(self, client: TestClient):
        response = client.get("/malformed-uuid")

        assert response.status_code == 422
        assert response.json()["detail"] == "A value is not in the expected format"


class TestNoDisclosure:
    @pytest.mark.parametrize("route", ["/unique-pg", "/foreign-key-pg", "/unique-sqlite", "/malformed-uuid"])
    def test_no_schema_detail_reaches_the_caller(self, client: TestClient, route: str):
        body = client.get(route).text

        for leaked in ("users", "email", "users_email_key", "constraint", "23505", "22P02"):
            assert leaked not in body, f"{route} leaked {leaked!r}"


class TestItIsAFloorNotAReplacement:
    def test_a_route_with_its_own_answer_keeps_it(self, client: TestClient):
        """The whole point: per-site handling names the field, and only a
        savepoint at the insert leaves the session usable. Neither is something
        an app-level handler can do, so neither may be replaced by one."""
        response = client.get("/handled-by-the-route")

        assert response.status_code == 409
        assert response.json()["detail"] == "A user with this email already exists"


class TestItIsActuallyWired:
    def test_the_app_factory_registers_the_floor(self):
        """A handler nothing installs is the same as no handler at all."""
        from app_factory import _register_exception_handlers

        app = FastAPI()
        _register_exception_handlers(app)

        assert IntegrityError in app.exception_handlers
        assert sqlite3.IntegrityError in app.exception_handlers
        assert DataError in app.exception_handlers

    def test_the_catch_all_is_still_the_last_resort(self):
        """The 500 handler must survive: everything unclassified still needs it."""
        from app_factory import _register_exception_handlers

        app = FastAPI()
        _register_exception_handlers(app)

        assert Exception in app.exception_handlers
