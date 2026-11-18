# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#19812: the env's URL holds encoded credentials; psycopg2 needs the real ones."""

from migrations.utils import parse_db_url


def test_encoded_credentials_reach_psycopg2_decoded() -> None:
    url = "postgresql+asyncpg://u%40x:a%40%3A%2F%25b@db.local:5432/name"  # pragma: allowlist secret
    params = parse_db_url(url)
    assert (params["user"], params["password"]) == ("u@x", "a@:/%b")
    assert (params["host"], params["port"], params["database"]) == ("db.local", 5432, "name")


def test_a_url_without_a_password_still_has_none() -> None:
    assert parse_db_url("postgresql://u@db.local:5432/name")["password"] is None
