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
from typing import Awaitable, Callable

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_KEY = "k" * 32


def _gate(name: str = "get_current_user_or_registry_service"):
    src = (_ROOT / "services" / "auth.py").read_text(encoding="utf-8")
    wanted = ("_internal_key_or_user", name)
    fns = [n for n in ast.parse(src).body if getattr(n, "name", "") in wanted]
    seen = {}

    async def get_current_user(credentials):
        seen["credentials"] = credentials
        return {"sub": "admin"}

    class _HTTPException(Exception):
        def __init__(self, status_code, detail, headers=None):
            self.status_code = status_code

    async def _enforce(request, user, permissions):
        seen["enforced"] = (request, user, permissions)
        if seen.get("deny"):
            raise _HTTPException(403, "denied")
        return {**user, "enforced": True}

    ns = {
        "verify_internal_api_key": lambda provided: provided == _KEY,
        "get_current_user": get_current_user,
        "HTTPException": _HTTPException,
        "status": SimpleNamespace(HTTP_401_UNAUTHORIZED=401),
        "HTTPAuthorizationCredentials": object,
        "Header": lambda *a, **k: None,
        "Depends": lambda *a, **k: None,
        "_optional_security": None,
        "Callable": Callable,
        "Awaitable": Awaitable,
        "Request": object,
        "Permission": SimpleNamespace(SERVICE_MANAGEMENT="service.management"),
        "_permission_gate": SimpleNamespace(enforce=_enforce),
    }
    exec(compile(ast.Module(fns, []), "auth.py", "exec"), ns)
    return ns[name], seen


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


def test_extra_gate_is_awaited_with_the_user_and_its_result_returned() -> None:
    gate, _ = _gate()
    calls = []

    async def extra(user):
        calls.append(user)
        return {"gated": True}

    assert asyncio.run(gate.__globals__["_internal_key_or_user"]("wrong", "bearer", extra)) == {"gated": True}
    assert calls == [{"sub": "admin"}]


def test_extra_gate_403_propagates() -> None:
    gate, _ = _gate()

    async def extra(user):
        raise gate.__globals__["HTTPException"](403, "denied")

    with pytest.raises(Exception) as exc:
        asyncio.run(gate.__globals__["_internal_key_or_user"]("wrong", "bearer", extra))
    assert exc.value.status_code == 403


def test_internal_key_short_circuits_before_extra_gate() -> None:
    gate, seen = _gate()
    called = []

    async def extra(user):
        called.append(user)
        return user

    out = asyncio.run(gate.__globals__["_internal_key_or_user"](_KEY, None, extra))
    assert out == {"internal_service": True, "role": "service"} and not called and "credentials" not in seen


def test_service_management_dependency_enforces_the_permission_for_a_human() -> None:
    gate, seen = _gate("require_service_management_or_internal")
    out = asyncio.run(gate("req", "wrong", "bearer"))
    assert out == {"sub": "admin", "enforced": True}
    assert seen["enforced"] == ("req", {"sub": "admin"}, ("service.management",))


def test_service_management_dependency_propagates_a_403_and_lets_the_key_through() -> None:
    gate, seen = _gate("require_service_management_or_internal")
    assert asyncio.run(gate("req", _KEY, None)) == {"internal_service": True, "role": "service"}
    assert "enforced" not in seen
    seen["deny"] = True
    with pytest.raises(Exception) as exc:
        asyncio.run(gate("req", "wrong", "bearer"))
    assert exc.value.status_code == 403
