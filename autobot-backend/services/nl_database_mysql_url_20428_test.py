# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#20428: the MySQL path gives the server the real credentials, not the URL's encoded form."""

from __future__ import annotations

from services.nl_database_service import _mysql_connect_args


def test_encoded_credentials_are_decoded() -> None:
    args = _mysql_connect_args("mysql://u%40x:a%40%3A%2F%25b@db.local:3307/name")  # pragma: allowlist secret
    assert (args["user"], args["password"]) == ("u@x", "a@:/%b")
    assert (args["host"], args["port"], args["db"]) == ("db.local", 3307, "name")


def test_no_credentials_and_the_default_port_are_left_as_they_are() -> None:
    args = _mysql_connect_args("mysql://db.local/name")
    assert args["user"] is None and args["password"] is None and args["port"] == 3306
