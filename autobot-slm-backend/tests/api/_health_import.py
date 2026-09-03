# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shared import helper for ``test_recovery_page_15462.py`` (#15462).

Same problem ``_code_sync_import.py`` solves, scoped to ``api/health.py``:
the root conftest stubs ``models.schemas`` as a ``MagicMock``, and
``api/health.py`` decorates ``@router.get("/metrics", response_model=
SystemMetrics)`` — FastAPI validates that against a real Pydantic type at
decoration time, so a bare import raises ``FastAPIError`` during collection
on a dev host / stubbed conftest. ``models.schemas_health`` (``HealthResponse``)
is never stubbed by the root conftest, so it needs no stand-in.
"""

from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

_BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _schemas_are_real() -> bool:
    from pydantic import BaseModel

    schemas = sys.modules.get("models.schemas")
    if schemas is None or isinstance(schemas, MagicMock):
        return False
    sentinel = getattr(schemas, "SystemMetrics", None)
    return isinstance(sentinel, type) and issubclass(sentinel, BaseModel)


def import_health() -> types.ModuleType:
    """Import ``api.health`` with a real ``SystemMetrics`` stand-in in place."""
    if str(_BACKEND_ROOT) not in sys.path:
        sys.path.insert(0, str(_BACKEND_ROOT))

    cached = sys.modules.get("api.health")
    if cached is not None:
        return cached

    if _schemas_are_real():
        return importlib.import_module("api.health")

    from pydantic import BaseModel as _BaseModel

    snapshot = {key: sys.modules.get(key) for key in ("models", "models.schemas")}

    schemas = types.ModuleType("models.schemas")
    schemas.SystemMetrics = type("SystemMetrics", (_BaseModel,), {})  # type: ignore[attr-defined]

    models = sys.modules.get("models")
    if models is None or isinstance(models, MagicMock):
        models = types.ModuleType("models")
        # A real __path__ so an untouched submodule import (models.schemas_health,
        # never stubbed by the root conftest) still resolves via the filesystem
        # instead of raising "models is not a package".
        models.__path__ = [str(_BACKEND_ROOT / "models")]  # type: ignore[attr-defined]
    models.schemas = schemas  # type: ignore[attr-defined]
    sys.modules["models"] = models
    sys.modules["models.schemas"] = schemas

    try:
        module = importlib.import_module("api.health")
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
