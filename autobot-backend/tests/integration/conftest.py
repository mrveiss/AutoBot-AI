# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Fixtures for integration tests.

The backend root conftest stubs ``auth_middleware`` in ``sys.modules`` (its
module-level ``__getattr__`` mints a fresh MagicMock per attribute access), so
integration tests that exercise the REAL middleware fallback chain (run-JWT /
device-JWT path guards, GH#6473 / GH#9493) would silently assert on mocks.

``real_auth_middleware`` loads the real module under an ALIAS key so the stub
— and every other test relying on it — stays untouched (no ``sys.modules``
pollution of the canonical name). Issue #11648.

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

import importlib.util
import sys
from pathlib import Path

import pytest
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles

_BACKEND_ROOT = Path(__file__).parent.parent.parent
_REAL_AM_KEY = "_integration_real_auth_middleware"


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(element, compiler, **kw):
    """Render PostgreSQL JSONB columns as JSON on SQLite test databases (#11687)."""
    return "JSON"


@compiles(ARRAY, "sqlite")
def _compile_pg_array_sqlite(element, compiler, **kw):
    """Render PostgreSQL ARRAY columns as JSON on SQLite test databases (#11687)."""
    return "JSON"


@pytest.fixture(scope="session")
def real_auth_middleware():
    """The REAL ``auth_middleware`` module, loaded under an alias key."""
    if _REAL_AM_KEY in sys.modules:
        return sys.modules[_REAL_AM_KEY]
    spec = importlib.util.spec_from_file_location(_REAL_AM_KEY, _BACKEND_ROOT / "auth_middleware.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_REAL_AM_KEY] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(_REAL_AM_KEY, None)
        raise
    return module
