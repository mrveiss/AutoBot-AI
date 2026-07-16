# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Fixtures for integration tests.

``real_auth_middleware`` (real auth_middleware loaded under an alias key,
#11648) moved up to tests/conftest.py in #11791 so root-level tests share it;
it remains available here through the conftest hierarchy.

JSONB/ARRAY-on-SQLite (#11687): production models use PostgreSQL-only column
types (``postgresql.JSONB`` / ``postgresql.ARRAY``) while integration tests
run ``Base.metadata.create_all`` against in-memory SQLite. SQLite's DDL
compiler has no renderer for those types, so every such test errored at
fixture setup. The ``@compiles(..., "sqlite")`` hooks below render both as
``JSON`` (SQLite has native JSON support; JSONB inherits the generic JSON
bind/result processors, so round-tripping dict/list values keeps working).
Registration is global and idempotent — a no-op for every other dialect, so
PostgreSQL DDL is untouched.
"""

from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(element, compiler, **kw):
    """Render PostgreSQL JSONB columns as JSON on SQLite test databases (#11687)."""
    return "JSON"


@compiles(ARRAY, "sqlite")
def _compile_pg_array_sqlite(element, compiler, **kw):
    """Render PostgreSQL ARRAY columns as JSON on SQLite test databases (#11687)."""
    return "JSON"
