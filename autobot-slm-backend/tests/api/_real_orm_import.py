# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shared real-sqlalchemy / real-schemas import helper for ``tests/api`` (#15640).

Third sibling of ``_code_sync_import.py`` and ``_health_import.py``, answering
the same problem those two answer: the root conftest stubs ``sqlalchemy``,
``models.database`` and ``models.schemas`` as ``MagicMock``s for import-time
safety, and ``api/services.py`` decorates its routes with
``response_model=ServiceListResponse`` (etc.) — FastAPI validates a response
model against a real Pydantic type at decoration time, so a bare import raises
``FastAPIError`` during collection.

Where those two install *fieldless* Pydantic stand-ins, this helper swaps the
REAL modules in for the duration of the import. Its callers need the genuine
article rather than a stand-in:

* ``test_restart_all_session_lifetime_15611.py`` asserts which objects cross a
  background boundary, and ``isinstance(item, Service)`` against a MagicMock is
  vacuously true for anything at all. It also drives a real in-memory engine.
* ``test_service_logs_timeout_vs_empty_15640.py`` asserts the *content* of the
  200 answer, and a fieldless stand-in silently drops the ``logs=""`` it is
  handed — which is precisely the empty-vs-incomplete ambiguity under test.

``sys.modules`` is restored after every swap, so the stubs stay in place for
every other test module (#11794 — ``tests/services`` real-loads
``services/auth.py``, whose ``from models.schemas import TokenResponse`` must
not see anything installed here).
"""

from __future__ import annotations

import contextlib
import importlib
import importlib.util
import sys
from pathlib import Path

SLM_ROOT = Path(__file__).resolve().parents[2]
if str(SLM_ROOT) not in sys.path:
    sys.path.insert(0, str(SLM_ROOT))

_SQLALCHEMY_MODULES = ("sqlalchemy", "sqlalchemy.ext", "sqlalchemy.ext.asyncio", "sqlalchemy.orm")


def _is_sqlalchemy_key(name: str) -> bool:
    return name == "sqlalchemy" or name.startswith("sqlalchemy.")


def load_real_module(name: str, path: Path):
    """Exec *path* under canonical *name* (registered so relative imports work)."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules[name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _build_real_modules() -> dict:
    """One-time real sqlalchemy + models.database/models.schemas snapshot.

    The root conftest stubs these as MagicMocks for import-time safety. The real
    packages are loaded once here and swapped in on demand, so a router is
    exercised against genuine ORM machinery rather than mock identity.
    """
    saved = {name: mod for name, mod in sys.modules.items() if _is_sqlalchemy_key(name)}
    saved.update({name: sys.modules.get(name) for name in ("models.database", "models.schemas")})
    for name in list(saved):
        sys.modules.pop(name, None)
    try:
        for name in _SQLALCHEMY_MODULES:
            importlib.import_module(name)
        importlib.import_module("sqlalchemy.dialects.sqlite")
        load_real_module("models.database", SLM_ROOT / "models" / "database.py")
        load_real_module("models.schemas", SLM_ROOT / "models" / "schemas.py")
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


REAL_MODULES = _build_real_modules()


@contextlib.contextmanager
def real_modules_swapped():
    """Temporarily put the real sqlalchemy/models modules into sys.modules."""
    saved = {name: sys.modules.get(name) for name in REAL_MODULES}
    sys.modules.update(REAL_MODULES)
    try:
        yield
    finally:
        for name, mod in saved.items():
            if mod is not None:
                sys.modules[name] = mod
            else:
                sys.modules.pop(name, None)


def import_modules_with_real_orm(import_names: tuple, path_loaded: dict | None = None) -> tuple:
    """Import *import_names* against the real ORM, restoring ``sys.modules`` after.

    ``path_loaded`` maps a dotted name to the file it must be exec'd from, for
    modules a normal import cannot reach: ``services`` is itself a MagicMock
    rather than a package, so ``services.service_restart`` has to be loaded by
    file spec and re-bound onto that stub. Those are loaded first, so a module
    in *import_names* that imports one of them binds the real object.

    Returns the loaded modules — ``path_loaded`` first, in declaration order,
    then *import_names* — as references the caller holds directly. Nothing is
    left behind in ``sys.modules``, so the stubs every other test module relies
    on are exactly as they were.
    """
    path_loaded = path_loaded or {}
    touched = tuple(path_loaded) + tuple(import_names)
    saved = {name: sys.modules.get(name) for name in touched}
    try:
        with real_modules_swapped():
            loaded = [load_real_module(name, path) for name, path in path_loaded.items()]
            for name in import_names:
                sys.modules.pop(name, None)
                loaded.append(importlib.import_module(name))
            return tuple(loaded)
    finally:
        for name, mod in saved.items():
            if mod is not None:
                sys.modules[name] = mod
            else:
                sys.modules.pop(name, None)
