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
"""

import importlib.util
import sys
from pathlib import Path

import pytest

_BACKEND_ROOT = Path(__file__).parent.parent.parent
_REAL_AM_KEY = "_integration_real_auth_middleware"


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
