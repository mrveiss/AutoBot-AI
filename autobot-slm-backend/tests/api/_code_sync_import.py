# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shared import helper for the ``test_code_sync_*`` unit tests (#12572).

Dev-host / combined-run problem
-------------------------------
The root conftest (#3499) stubs ``models`` and ``models.schemas`` as
``MagicMock``s.  ``api/code_sync.py`` decorates routes with
``response_model=CodeSyncStatusResponse`` (etc.), and FastAPI validates the
response model against a real Pydantic type *at decoration time* — a MagicMock
raises ``FastAPIError`` during module import (i.e. at pytest collection).

Each test file therefore installs minimal real ``BaseModel`` stand-ins for
``models.schemas`` before importing ``api.code_sync``, then restores the
original ``models`` entries so the stand-ins never leak into later-collected
directories (#11794 — ``tests/services`` real-loads ``services/auth.py`` whose
``from models.schemas import TokenResponse`` must not see our narrow stubs).

Why a shared helper (the #12572 leak)
-------------------------------------
``tests/services/conftest.py`` swaps the ``models`` MagicMock for a real hollow
``ModuleType`` package (so real submodules import).  When ``tests/api`` and
``tests/services`` are collected together, that conftest runs first, so by the
time a ``test_code_sync_*`` file is collected ``sys.modules["models"]`` is a
plain module — not a MagicMock.  The per-file guards keyed on
``isinstance(models, MagicMock)`` then evaluate ``False`` and skip installing
the stand-ins, while ``models.schemas`` is *still* a MagicMock → the three
files fail collection order-dependently.

This helper keys the decision on ``models.schemas`` (the object actually used
by the router), AST-derives the class list from ``api/code_sync.py`` so it can
never rot, forces a fresh ``api.code_sync`` import when it installs stand-ins,
and restores the original ``models`` entries afterwards.
"""

from __future__ import annotations

import ast
import importlib
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_CODE_SYNC_SRC = _BACKEND_ROOT / "api" / "code_sync.py"


def _schema_class_names() -> list[str]:
    """Every name imported ``from models.schemas`` in api/code_sync.py.

    AST-derived (not hand-maintained) so a new schema import can never rot the
    stand-in list — same rot-proof pattern the root conftest uses for the
    ``services.*`` stubs (#11575, #11794).
    """
    tree = ast.parse(_CODE_SYNC_SRC.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "models.schemas":
            names |= {alias.name for alias in node.names}
    return sorted(names)


def _schemas_are_real() -> bool:
    """True when ``models.schemas`` already exposes real Pydantic response models.

    Keyed on ``models.schemas`` (what the router decorates against) rather than
    the ``models`` parent — the parent may be a real hollow package installed by
    ``tests/services/conftest.py`` while ``models.schemas`` is still a MagicMock.
    """
    from pydantic import BaseModel

    schemas = sys.modules.get("models.schemas")
    if schemas is None or isinstance(schemas, MagicMock):
        return False
    sentinel = getattr(schemas, "CodeSyncStatusResponse", None)
    return isinstance(sentinel, type) and issubclass(sentinel, BaseModel)


def import_code_sync() -> types.ModuleType:
    """Import ``api.code_sync`` with real Pydantic schema stand-ins in place.

    Installs minimal ``BaseModel`` stand-ins for ``models.schemas`` only when the
    real models are absent (dev host / stubbed conftest), imports the router with
    them bound, then restores the pre-call ``models`` / ``models.schemas``
    entries so the stand-ins do not leak into later-collected directories.
    """
    if str(_BACKEND_ROOT) not in sys.path:
        sys.path.insert(0, str(_BACKEND_ROOT))

    # A cached api.code_sync is always good: a bad import (MagicMock response
    # models) raises FastAPIError and never caches.  Reuse the single instance
    # so every test_code_sync_* file — and any patch("api.code_sync.X") — targets
    # the SAME module object (distinct instances would make patches miss, #12572).
    cached = sys.modules.get("api.code_sync")
    if cached is not None:
        return cached

    if _schemas_are_real():
        return importlib.import_module("api.code_sync")

    from pydantic import BaseModel as _BaseModel

    snapshot = {key: sys.modules.get(key) for key in ("models", "models.schemas")}

    schemas = types.ModuleType("models.schemas")
    for class_name in _schema_class_names():
        setattr(schemas, class_name, type(class_name, (_BaseModel,), {}))

    models = sys.modules.get("models")
    if models is None or isinstance(models, MagicMock):
        models = types.ModuleType("models")
    models.schemas = schemas  # type: ignore[attr-defined]
    sys.modules["models"] = models
    sys.modules["models.schemas"] = schemas

    # Not cached (an earlier bad import would not have cached) — exec fresh with
    # the stand-ins bound, then restore the original models entries.
    try:
        module = importlib.import_module("api.code_sync")
    finally:
        for key, value in snapshot.items():
            if value is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = value
        restored = sys.modules.get("models")
        restored_schemas = sys.modules.get("models.schemas")
        if restored is not None and restored_schemas is not None and not isinstance(restored, MagicMock):
            restored.schemas = restored_schemas  # type: ignore[attr-defined]

    return module
