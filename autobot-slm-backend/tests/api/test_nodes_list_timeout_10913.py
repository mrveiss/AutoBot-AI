# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression test: GET /api/nodes must not hang on a slow/stale DB (#10913).

Root cause: ``list_nodes`` ran its DB query + service-count lookup inline
with no bound, so a stale/hung DB connection (e.g. a silently-dropped WSL2
idle socket, #10491) could block the whole request indefinitely — clients
observed a curl ``000`` after 45s.

Fix: the DB-bound body was extracted to ``_query_nodes_page`` and wrapped in
``asyncio.wait_for(..., timeout=_NODES_LIST_TIMEOUT)`` (mirrors the
``_ROLES_LIST_TIMEOUT`` precedent in ``api/roles.py``, #11360) so a slow
backend fails fast with ``504 Gateway Timeout`` instead of hanging.

Follows the code_version_test.py real-module-swap pattern (#11737): the
slm-backend root conftest stubs ``sqlalchemy``/``models.database``/
``models.schemas`` as MagicMocks for import-time safety, so ``api.nodes``
is imported inside ``_real_modules_swapped()`` to get the real FastAPI/
pydantic machinery ``asyncio.wait_for`` and ``HTTPException`` need.
"""

from __future__ import annotations

import asyncio
import contextlib
import importlib
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

_SLM_ROOT = Path(__file__).parent.parent.parent
if str(_SLM_ROOT) not in sys.path:
    sys.path.insert(0, str(_SLM_ROOT))

_SQLALCHEMY_MODULES = ("sqlalchemy", "sqlalchemy.ext", "sqlalchemy.ext.asyncio", "sqlalchemy.orm")


def _is_sqlalchemy_key(name: str) -> bool:
    return name == "sqlalchemy" or name.startswith("sqlalchemy.")


def _load_real_module(name: str, path: Path):
    """Exec *path* under canonical *name* (registered so relative imports work)."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules[name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _build_real_modules() -> dict:
    """One-time real sqlalchemy + models.database/models.schemas snapshot.

    Mirrors tests/services/code_version_test.py's module-level setup: the
    root conftest stubs these as MagicMocks for import-time safety, so the
    real packages are loaded once here and swapped in on demand.
    """
    saved = {name: mod for name, mod in sys.modules.items() if _is_sqlalchemy_key(name)}
    saved.update({name: sys.modules.get(name) for name in ("models.database", "models.schemas")})
    for name in list(saved):
        sys.modules.pop(name, None)
    try:
        for name in _SQLALCHEMY_MODULES:
            importlib.import_module(name)
        importlib.import_module("sqlalchemy.dialects.sqlite")
        _load_real_module("models.database", _SLM_ROOT / "models" / "database.py")
        _load_real_module("models.schemas", _SLM_ROOT / "models" / "schemas.py")
        return {name: mod for name, mod in sys.modules.items() if _is_sqlalchemy_key(name)} | {
            "models.database": sys.modules["models.database"],
            "models.schemas": sys.modules["models.schemas"],
        }
    finally:
        for name in [n for n in sys.modules if _is_sqlalchemy_key(n)]:
            del sys.modules[name]
        sys.modules.pop("models.database", None)
        sys.modules.pop("models.schemas", None)
        for name, mod in saved.items():
            if mod is not None:
                sys.modules[name] = mod
            else:
                sys.modules.pop(name, None)


_REAL_MODULES = _build_real_modules()


@contextlib.contextmanager
def _real_modules_swapped():
    """Temporarily put the real sqlalchemy/models modules into sys.modules."""
    saved = {name: sys.modules.get(name) for name in _REAL_MODULES}
    sys.modules.update(_REAL_MODULES)
    try:
        yield
    finally:
        for name, mod in saved.items():
            if mod is not None:
                sys.modules[name] = mod
            else:
                sys.modules.pop(name, None)


def _load_nodes_module():
    """Import the real ``api.nodes`` module under the real-module swap."""
    with _real_modules_swapped():
        sys.modules.pop("api.nodes", None)
        return importlib.import_module("api.nodes")


class TestListNodesTimeout:
    """GET /nodes bounds the DB round-trip so it can't hang (#10913)."""

    @pytest.mark.asyncio
    async def test_returns_504_promptly_when_db_hangs(self):
        """A hung db.execute() must not block the endpoint past the timeout."""
        nodes_module = _load_nodes_module()
        nodes_module._NODES_LIST_TIMEOUT = 0.05  # keep the test itself fast

        async def _hang(*_args, **_kwargs):
            await asyncio.sleep(10)  # far longer than _NODES_LIST_TIMEOUT

        mock_db = AsyncMock()
        mock_db.execute.side_effect = _hang

        start = time.monotonic()
        with pytest.raises(HTTPException) as exc_info:
            await nodes_module.list_nodes(
                db=mock_db,
                _={"admin": True, "role": "admin"},
                status_filter=None,
                page=1,
                per_page=20,
            )
        elapsed = time.monotonic() - start

        assert exc_info.value.status_code == 504
        # Bounded well under the 10s hang -- proves wait_for actually cancelled it.
        assert elapsed < 2.0, f"list_nodes took {elapsed:.2f}s -- timeout did not bound it"

    @pytest.mark.asyncio
    async def test_fast_path_still_returns_page(self):
        """A normal (fast) DB round-trip is unaffected by the wait_for wrapper."""
        nodes_module = _load_nodes_module()
        nodes_module._NODES_LIST_TIMEOUT = 5.0

        expected = nodes_module.NodeListResponse(nodes=[], total=0, page=1, per_page=20)

        async def _fast_query(*_args, **_kwargs):
            return expected

        nodes_module._query_nodes_page = _fast_query

        result = await nodes_module.list_nodes(
            db=AsyncMock(),
            _={"admin": True, "role": "admin"},
            status_filter=None,
            page=1,
            per_page=20,
        )

        assert result is expected
