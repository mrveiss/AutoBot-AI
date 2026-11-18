# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The one way to put credentials into a PostgreSQL URL (#19812)."""

from __future__ import annotations

from urllib.parse import quote


def build_postgres_dsn(scheme: str, user: str, password: str, host: str, port: str | int, database: str) -> str:
    """A URL whose user and password survive ``@``, ``:``, ``/`` and ``%``.

    Written raw, those characters end the credentials early, so the client connects to the wrong host or
    fails to parse. No password gives no ``:``, for a server that authenticates another way.
    """
    credentials = quote(user, safe="")
    if password:
        credentials += ":" + quote(password, safe="")
    return f"{scheme}://{credentials}@{host}:{port}/{database}"
