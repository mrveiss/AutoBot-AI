# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Conftest for api-level unit tests.

Dev-host workaround: the system `multipart` package (0.0.27 installed by mcp)
conflicts with starlette's import of `python_multipart.multipart`.  Pytest
loads conftest modules before collecting test files, so this is the correct
place to install the stub — by the time any test module does
`from api.code_sync import ...` the starlette cache is already clean.

This does NOT affect CI (where the correct packages are installed in the venv).
"""

import sys
import types

if "multipart" not in sys.modules or not hasattr(sys.modules.get("multipart"), "parse_options_header"):
    # Stub multipart.multipart.parse_options_header so starlette.formparsers loads
    _mp_inner = types.ModuleType("multipart.multipart")
    _mp_inner.parse_options_header = lambda *a, **kw: (b"", {})  # type: ignore[attr-defined]
    _mp = types.ModuleType("multipart")
    _mp.multipart = _mp_inner  # type: ignore[attr-defined]
    sys.modules.setdefault("multipart", _mp)
    sys.modules.setdefault("multipart.multipart", _mp_inner)

if "python_multipart" not in sys.modules:
    _pymp_inner = types.ModuleType("python_multipart.multipart")
    _pymp_inner.parse_options_header = lambda *a, **kw: (b"", {})  # type: ignore[attr-defined]
    _pymp = types.ModuleType("python_multipart")
    _pymp.multipart = _pymp_inner  # type: ignore[attr-defined]
    sys.modules.setdefault("python_multipart", _pymp)
    sys.modules.setdefault("python_multipart.multipart", _pymp_inner)
