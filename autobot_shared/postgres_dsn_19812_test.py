# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Credentials with URL characters survive into a PostgreSQL URL (#19812)."""

from __future__ import annotations

from urllib.parse import unquote, urlsplit

import pytest

from autobot_shared.postgres_dsn import build_postgres_dsn


@pytest.mark.parametrize("password", ["a@b", "a:b", "a/b", "a%b", "@:/%", "plain", "a%40b", "p w#?"])
def test_a_password_parses_back_to_itself_and_the_host_stays_the_host(password: str) -> None:
    parts = urlsplit(build_postgres_dsn("postgresql", "user", password, "db.local", 5432, "name"))
    assert unquote(parts.password) == password
    assert (parts.hostname, parts.port, parts.path) == ("db.local", 5432, "/name")


def test_a_user_with_url_characters_parses_back() -> None:
    parts = urlsplit(build_postgres_dsn("postgresql", "a@b", "p", "h", "1", "d"))
    assert unquote(parts.username) == "a@b" and parts.hostname == "h"


def test_no_password_gives_no_separator() -> None:
    assert build_postgres_dsn("postgresql+asyncpg", "user", "", "h", 1, "d") == "postgresql+asyncpg://user@h:1/d"
