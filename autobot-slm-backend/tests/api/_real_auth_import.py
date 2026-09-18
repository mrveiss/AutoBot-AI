# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shared loader for the REAL ``services/auth.py`` (#16040).

The root conftest stubs ``services.auth`` (``api/code_sync.py`` imports it),
along with ``config``, ``sqlalchemy`` and ``models.schemas``. A test that needs
the genuine dependencies, not a mock of them, loads the file by path under the
light stand-ins its import needs, keeps the module object, and then puts back
every ``sys.modules`` entry it touched (#11478, #11794). This is the technique
``test_auth_me_16385.py`` documents. Four test files still carry a private copy
of it; this module is the shared one (#16988 moves them onto it).
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

_BACKEND = Path(__file__).resolve().parents[2]

#: Imported by ``services/auth.py`` at load time, and stood in for here.
_STUBS = (
    "models.schemas",
    "user_management.models.user",
    "services.jwks_verifier",
    "sqlalchemy",
    "sqlalchemy.ext",
    "sqlalchemy.ext.asyncio",
    "sqlalchemy.orm",
)
#: Loaded for real, by path, in this order.
_REAL = ("services.token_denylist", "services.auth")


def _exec_by_path(name: str) -> types.ModuleType:
    path = _BACKEND / Path(*name.split(".")).with_suffix(".py")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules[name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def load_real_auth(secret_key: str, expire_minutes: int = 30) -> types.ModuleType:
    """Return the real ``services.auth`` module, leaving ``sys.modules`` as it found it."""
    for root in (_BACKEND, _BACKEND.parent):
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
    managed = ("config", *_STUBS, *_REAL)
    before = {name: sys.modules[name] for name in managed if name in sys.modules}
    try:
        config = MagicMock()
        config.settings.secret_key = secret_key
        config.settings.access_token_expire_minutes = expire_minutes
        sys.modules["config"] = config
        for name in _STUBS:
            sys.modules[name] = MagicMock()
        return [_exec_by_path(name) for name in _REAL][-1]
    finally:
        for name in managed:
            if name in before:
                sys.modules[name] = before[name]
            else:
                sys.modules.pop(name, None)
