# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The four read-only routers of #16375 slice S1 refuse an anonymous caller.

`repo_tests/config_router_auth_coverage_test.py` proves each gate is DECLARED --
it reads the AST. It cannot see whether the dependency actually REFUSES anyone,
and a declared gate that admits everyone is the shape this repository keeps
finding. So, per router, in the pattern of `chat_knowledge_wiring_test.py`:

* the dependency is on the router object, so a route added later inherits it;
* a request whose user does not resolve is refused;
* an authenticated request is NOT refused by the gate (the contrast case -- a
  gate refusing everyone would be a broken module, not a secured one).

The handlers are not the subject, and some of them reach out (`/summary` fetches
over HTTP). So the refusal test stops at the gate -- dependencies resolve before
the handler runs -- and the contrast mounts the router's OWN dependency list on
a probe route, which asks exactly "does this gate admit a signed-in user"
without running a handler that needs a live service.
"""

from __future__ import annotations

import importlib

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from api.user_management.dependencies import get_current_user

#: module -> a parameterless GET route on it. Prefixes are irrelevant here: the
#: gate lives on the router, so any mount carries it.
ROUTERS = {
    "api.analytics_reporting": "/summary",
    "api.project": "/status",
    "api.registry": "/routers",
    "api.self_capabilities": "/capabilities",
}


class _NoUser:
    def get_user_from_request(self, request):
        return None


def _make_app(module_name: str) -> FastAPI:
    app = FastAPI()
    app.include_router(importlib.import_module(module_name).router)
    return app


@pytest.mark.parametrize("module_name", sorted(ROUTERS))
class TestTheRouterIsGated:
    """#16375 slice S1: every route requires an authenticated caller."""

    def test_the_gate_is_on_the_router(self, module_name):
        router = importlib.import_module(module_name).router
        gates = [d.dependency for d in router.dependencies]
        assert get_current_user in gates, (
            f"{module_name}: the gate is not on the router object -- per-route gating is "
            f"one forgotten decorator away from an anonymous route"
        )

    def test_a_request_whose_user_does_not_resolve_is_refused(self, module_name, monkeypatch):
        # Pinned to "nobody", not left ambient: `get_auth_middleware` is process-global
        # and other tests stub it with a canned user. The pin lands where
        # dependencies.py looks the name up, since it `from`-imports it.
        monkeypatch.setattr("api.user_management.dependencies.get_auth_middleware", lambda: _NoUser())
        app = _make_app(module_name)
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get(ROUTERS[module_name])
        assert response.status_code in (401, 403), (
            f"{module_name}{ROUTERS[module_name]}: a caller with no resolvable user got "
            f"{response.status_code} -- before #16375 every route here answered anonymously"
        )

    def test_an_authenticated_request_passes_the_gate(self, module_name):
        gated = importlib.import_module(module_name).router
        probe = APIRouter(dependencies=list(gated.dependencies))

        @probe.get("/probe")
        async def _probe():
            return {"ok": True}

        app = FastAPI()
        app.include_router(probe)
        app.dependency_overrides[get_current_user] = lambda: {"username": "tester", "role": "user"}
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/probe")
        assert response.status_code == 200, (
            f"{module_name}: an authenticated caller was refused by the router's own gate "
            f"({response.status_code}) -- a gate refusing everyone is a broken module"
        )
