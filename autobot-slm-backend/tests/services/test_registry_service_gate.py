# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#22144: the five routes the main backend's VNC registry client calls accept the internal service key.

`services.auth` is stubbed by the suite's conftest, so the real dependency is compiled from source.
A human still needs an admin session (`get_current_user`); the general service JWT is not widened.
"""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_KEY = "k" * 32


def _gate():
    src = (_ROOT / "services" / "auth.py").read_text(encoding="utf-8")
    fn = next(n for n in ast.parse(src).body if getattr(n, "name", "") == "get_current_user_or_registry_service")
    seen = {}

    async def get_current_user(credentials):
        seen["credentials"] = credentials
        return {"sub": "admin"}

    class _HTTPException(Exception):
        def __init__(self, status_code, detail, headers=None):
            self.status_code = status_code

    ns = {
        "verify_internal_api_key": lambda provided: provided == _KEY,
        "get_current_user": get_current_user,
        "HTTPException": _HTTPException,
        "status": SimpleNamespace(HTTP_401_UNAUTHORIZED=401),
        "HTTPAuthorizationCredentials": object,
        "Header": lambda *a, **k: None,
        "Depends": lambda *a, **k: None,
        "_optional_security": None,
    }
    exec(compile(ast.Module([fn], []), "auth.py", "exec"), ns)
    return ns["get_current_user_or_registry_service"], seen


def test_the_internal_key_authenticates_the_machine_caller() -> None:
    gate, seen = _gate()
    assert asyncio.run(gate(_KEY, None)) == {"internal_service": True, "role": "service"}
    assert "credentials" not in seen  # no session check ran


def test_a_human_session_still_goes_through_get_current_user() -> None:
    gate, seen = _gate()
    assert asyncio.run(gate("wrong", "bearer")) == {"sub": "admin"}
    assert seen["credentials"] == "bearer"


def test_no_key_and_no_session_is_401() -> None:
    gate, _ = _gate()
    with pytest.raises(Exception) as exc:
        asyncio.run(gate(None, None))
    assert exc.value.status_code == 401


def test_exactly_the_registry_routes_use_the_gate() -> None:
    vnc = (_ROOT / "api" / "vnc.py").read_text(encoding="utf-8")
    nodes = (_ROOT / "api" / "nodes.py").read_text(encoding="utf-8")
    assert vnc.count("Depends(get_current_user_or_registry_service)") == 4
    assert nodes.count("Depends(get_current_user_or_registry_service)") == 1
