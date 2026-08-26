# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Route-level admin gate tests for api/terminal_tools.py (#15084).

Before this fix, ``api.terminal_tools.router`` declared no dependency of its
own. It is mounted at two independent points:

- ``api/terminal.py`` includes it onto ``admin_router``
  (``Depends(check_admin_permission)`` at construction), so requests routed
  through ``/terminal/...`` were gated -- but only because of *where*
  ``terminal.py`` happened to include it, proved by
  ``terminal_websocket_route_test.py::TestTerminalToolRoutesKeepTheirGate``.
- ``initialization/router_registry/terminal_routers.py`` separately registers
  the same router object as its own top-level entry with an empty prefix,
  mounted by ``app_factory.py`` via a bare ``app.include_router(router,
  prefix=f"/api{prefix}", tags=tags)`` -- no ``dependencies=`` passed. That
  mount had no gate at all: install-tool, check-tool, validate-command and
  package-managers were reachable anonymously.

This file drives that second, previously-unauthenticated mount directly --
``api.terminal_tools.router`` included alone into a fresh app, the same shape
``terminal_routers.py`` uses -- through a real ``TestClient`` request, not by
introspecting the route object (empty under fastapi 0.141.1 for genuinely
gated routes; see the module docstring in ``terminal_websocket_route_test.py``
for why introspection cannot answer this question on that version).
"""

import pytest
from fastapi import APIRouter, FastAPI, HTTPException
from starlette.testclient import TestClient

from api.terminal_tools import check_admin_permission
from api.terminal_tools import router as tools_router

#: Paths as api.terminal_tools.router serves them on its own, unprefixed.
_TOOL_ROUTES = (
    ("post", "/install-tool"),
    ("post", "/check-tool"),
    ("post", "/validate-command"),
    ("get", "/package-managers"),
)


def _request(client, method: str, path: str):
    """Issue *method* at *path*, sending a body only where one is accepted.

    ``TestClient.get()`` takes no ``json=`` -- passing one raises ``TypeError``
    rather than returning a status, which would read as a routing failure.
    """
    if method == "get":
        return client.get(path)
    return getattr(client, method)(path, json={})


@pytest.fixture
def tools_app():
    """Mount ``api.terminal_tools.router`` exactly as
    ``initialization/router_registry/terminal_routers.py`` +
    ``app_factory.py`` do at the top level: no ``dependencies=`` passed to
    ``include_router``, nothing else on the app. This is the mount point that
    had no gate at all before #15084.
    """
    app = FastAPI()
    app.include_router(tools_router)
    return app


@pytest.fixture
def tools_client(tools_app):
    return TestClient(tools_app, raise_server_exceptions=False)


class TestTerminalToolsStandaloneMountIsGated:
    """#15084: the router now carries its own admin dependency, so it stays
    gated no matter which parent includes it -- proved here against the
    router mounted completely alone, which is the shape that was previously
    reachable anonymously.
    """

    @pytest.mark.parametrize("method,path", _TOOL_ROUTES)
    def test_route_refuses_a_non_admin(self, tools_app, tools_client, method, path):
        def _deny():
            raise HTTPException(status_code=403, detail="Admin permission required for this operation")

        tools_app.dependency_overrides[check_admin_permission] = _deny
        try:
            response = _request(tools_client, method, path)
        finally:
            tools_app.dependency_overrides.pop(check_admin_permission, None)

        assert response.status_code == 403, (
            f"{path} installs packages / runs system commands and must stay gated on its own "
            f"router regardless of mount point, got {response.status_code}"
        )

    @pytest.mark.parametrize("method,path", _TOOL_ROUTES)
    def test_route_is_actually_served(self, tools_app, tools_client, method, path):
        """Non-vacuity: a 404 would make the refusal above pass for the wrong
        reason -- an unrouted path never reaches a dependency."""
        tools_app.dependency_overrides[check_admin_permission] = lambda: True
        try:
            response = _request(tools_client, method, path)
        finally:
            tools_app.dependency_overrides.pop(check_admin_permission, None)

        assert response.status_code != 404, f"{path} is not served at all -- the gate test above proves nothing"


class TestDependencyFreeRouterDoesNotRefuseAnyone:
    """Contrast, kept in-suite as a permanent regression guard: a router
    shaped exactly like ``terminal_tools.py`` before #15084 -- same route,
    but constructed with no ``dependencies=`` of its own -- reaches the
    handler for anyone. Proves the assertions above are actually sensitive to
    the fix rather than passing for an unrelated reason. The full contrast
    (mutating ``terminal_tools.py`` itself and re-running the named tests
    above) is exercised manually per #15084's testing requirements and is not
    checked in, since it requires editing production source.
    """

    def test_bare_router_serves_a_non_admin(self):
        bare_router = APIRouter(tags=["terminal-tools"])

        @bare_router.get("/package-managers")
        def _package_managers():
            return {"detected": None, "available": [], "package_managers": {}}

        app = FastAPI()
        app.include_router(bare_router)
        client = TestClient(app, raise_server_exceptions=False)

        response = client.get("/package-managers")
        assert response.status_code == 200, (
            "a router with no dependency of its own must reach the handler for anyone -- "
            "this is the exact pre-fix shape #15084 reports"
        )
