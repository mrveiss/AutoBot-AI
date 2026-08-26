# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Route-level guard tests for the terminal WebSocket 500 (#14998).

``terminal_websocket_auth_test.py`` and ``ssh_terminal_websocket_auth_test.py``
call the decorated handler *functions* directly (``await terminal_websocket(ws,
session_id)``). That bypasses FastAPI's routing and dependency-resolution layer
entirely, so neither file could ever have caught #14998: a router-level
``Depends(check_admin_permission)`` (``Request``-typed) 500s the handshake
inside ``solve_dependencies``, before the handler is ever invoked -- a failure
mode a handler-direct call cannot reach. This file drives the routes the way a
real client does, through ``starlette.testclient.TestClient``, which runs the
actual ASGI app including route matching and dependency resolution.

Covers:
- Structural proof the merged router puts ``check_admin_permission`` on the
  HTTP routes (including the tool-execution routes, #15084) and NOT on either
  ``@router.websocket`` route (the fix itself). Sourced from a clean
  subprocess import (see ``_dump_routes_main`` below) rather than an
  in-process one: under ``python-suite`` shard 12/12, an in-process
  ``api.terminal.router`` was observed with zero routes (CI job 98074498060),
  something earlier in the same pytest-xdist worker having left ``sys.modules``
  in a state this module's own collection-time import inherited. A fresh
  interpreter is immune to that regardless of its cause (mirrors the
  subprocess-per-class pattern in
  ``autobot_shared/user_management/models/core_test.py``).
- A real handshake on ``/ws/{session_id}``: authenticated owner connects,
  unauthenticated caller is refused before ``accept()``.
- A real handshake on ``/ws/ssh/{host_id}``: authenticated admin connects,
  unauthenticated caller is refused before ``accept()``.
- The HTTP routes on the same router still reject a non-admin caller
  (dependency_overrides, in-process -- this needs object identity with the
  live app/router, so it cannot move to a subprocess).
- Contrast mutation: an isolated router shaped exactly like the reported bug
  (router-level ``Depends`` of a ``Request``-typed callable, owning a
  ``@router.websocket`` route) fails the handshake with the same ``TypeError``
  ``solve_dependencies`` raises; the split-router shape this fix uses does not.
"""

import json
import os
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, WebSocket
from starlette.testclient import TestClient

from api.terminal import check_admin_permission
from api.terminal import router as terminal_router
from api.terminal import session_manager, ssh_terminal_manager

_original_accept = WebSocket.accept


async def _spy_accept(self, *args, **kwargs):
    """A real function (not a Mock) so instance attribute lookup binds ``self``
    the normal descriptor way -- see #14998 investigation notes. Records every
    call and still performs the real accept so the "connects" tests observe a
    genuine handshake, not a short-circuited one.
    """
    _spy_accept.calls.append(self)
    return await _original_accept(self, *args, **kwargs)


_spy_accept.calls = []


@contextmanager
def _accept_spy():
    _spy_accept.calls = []
    with patch.object(WebSocket, "accept", new=_spy_accept):
        yield _spy_accept.calls


@contextmanager
def _no_ws_credentials():
    """See api/terminal_websocket_auth_test.py::_no_ws_credentials -- same
    union of credential sources must be closed off for "unauthenticated".
    """
    with (
        patch("auth_middleware.authenticate_websocket", new=AsyncMock(return_value=None)),
        patch("auth_middleware.verify_internal_api_key", return_value=False),
        patch("auth_middleware.get_auth_middleware") as mock_get_auth_middleware,
    ):
        mock_get_auth_middleware.return_value.get_user_from_request.return_value = None
        yield


@pytest.fixture
def terminal_app():
    """A real FastAPI app mounting the production terminal router, exactly as
    ``initialization/router_registry/terminal_routers.py`` does (minus the
    ``/api/terminal`` prefix, irrelevant to dependency resolution).
    """
    app = FastAPI()
    app.include_router(terminal_router)
    return app


@pytest.fixture
def terminal_client(terminal_app):
    return TestClient(terminal_app, raise_server_exceptions=False)


# --- clean-interpreter route/dependency enumeration (#14998, shard-12 pollution) ---
#
# Every structural gate assertion below reads from this, never from the
# in-process ``terminal_router`` bound at collection time: that name observed
# zero routes under python-suite shard 12/12 (CI job 98074498060) even though
# this file passes in isolation -- some earlier-collected test in the same
# xdist worker leaves shared state (import machinery or the router object
# itself) in a way this file's own module-level import inherits. Filed as
# #15087, unidentified polluter. A subprocess that imports ``api.terminal``
# fresh sidesteps the mechanism entirely rather than needing to name it.

_ADMIN_DEP = "auth_middleware.check_admin_permission"

#: Matched by suffix, not by full path. Under fastapi 0.141.1 the prefix passed
#: to ``include_router`` is applied at request-routing time and is on neither the
#: deferred wrapper's ``.prefix`` nor the original router's -- three CI runs
#: (98110125325, 98112466169) confirmed it is not recoverable by introspection.
#: The prefix is incidental to what this guard exists to prove: that the four
#: routes which install packages and run system commands carry the admin check.
#: Each suffix must match exactly one route, so the looser match cannot become a
#: loophole.
_TOOL_SUFFIXES = (
    "/install-tool",
    "/check-tool",
    "/validate-command",
    "/package-managers",
)


class _TerminalRouteDumpError(RuntimeError):
    """The subprocess dump did not return a trustworthy answer.

    Carries every diagnostic available -- interpreter/framework versions and
    the subprocess's full stdout/stderr -- so a CI failure names the cause
    instead of a downstream assertion naming only its symptom (#14998 job
    98083466678: the terse "'/terminal/check-tool' missing" message hid that
    the dump had only returned 3 of 26 routes, one with no identifiable path,
    with nothing said about why).
    """


def _run_terminal_route_dump() -> list:
    """Import api.terminal in a fresh subprocess and return its route list.

    Bootstraps via ``-c`` and a dotted import (``api.terminal_websocket_route_test``)
    rather than executing this file's own path directly: running a script
    prepends *its own directory* (``api/``) to ``sys.path[0]``, and that
    directory holds ``api/secrets.py`` -- which then shadows the stdlib
    ``secrets`` module the very first thing FastAPI imports needs, crashing
    with a circular-import ``ImportError`` before ``api.terminal`` is ever
    reached. ``-c`` sets ``sys.path[0]`` to ``""`` (cwd) instead, which does
    not collide.

    Never returns a partial answer quietly: a non-zero exit, unparsable
    stdout, a missing/malformed ``routes`` list, an empty result, or any
    route entry the dump could not attach a path to, all raise
    ``_TerminalRouteDumpError`` with the interpreter/framework versions and
    the subprocess's raw stdout/stderr attached.
    """
    backend_root = Path(__file__).resolve().parents[1]
    repo_root = backend_root.parent
    # autobot_shared/ is a sibling of autobot-backend/, not nested under it
    # (mirrors pytest.ini's `pythonpath = . autobot-backend autobot_shared ...`).
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(repo_root), str(backend_root)]))
    bootstrap = "import api.terminal_websocket_route_test as m; m._dump_routes_main()"
    result = subprocess.run(
        [sys.executable, "-c", bootstrap],
        capture_output=True,
        text=True,
        cwd=str(backend_root),
        env=env,
        timeout=60,
    )

    def _fail(reason: str, spec_repr: str = "") -> None:
        raise _TerminalRouteDumpError(
            f"{reason}\n"
            f"subprocess exit code: {result.returncode}\n"
            f"{spec_repr}"
            f"--- subprocess stdout ---\n{result.stdout}\n"
            f"--- subprocess stderr ---\n{result.stderr}"
        )

    if result.returncode != 0:
        _fail("terminal route dump subprocess exited non-zero")

    # get_logger's default handler writes startup noise (e.g. the error-catalog
    # load line) to stdout ahead of the JSON -- take the last line so that
    # incidental logging can't break the parse.
    stdout_lines = [ln for ln in result.stdout.strip().splitlines() if ln.strip()]
    if not stdout_lines:
        _fail("terminal route dump subprocess produced no stdout at all")

    try:
        spec = json.loads(stdout_lines[-1])
    except json.JSONDecodeError as exc:
        _fail(f"terminal route dump subprocess stdout was not parseable JSON: {exc}")

    routes = spec.get("routes") if isinstance(spec, dict) else None
    versions = (
        f"python: {spec.get('python', '<unreported>')!r}\n"
        f"fastapi: {spec.get('fastapi', '<unreported>')!r}\n"
        f"starlette: {spec.get('starlette', '<unreported>')!r}\n"
        if isinstance(spec, dict)
        else ""
    )
    if not isinstance(routes, list):
        _fail(f"terminal route dump returned no usable 'routes' list: {spec!r}", versions)

    unidentified = [r for r in routes if not isinstance(r, dict) or r.get("path") is None]
    if unidentified:
        _fail(
            f"terminal route dump returned {len(routes)} route(s), of which "
            f"{len(unidentified)} had no identifiable path -- a route the dump "
            "cannot name is a parse failure, not a route, and is never folded "
            "into the path->dependencies mapping.\n"
            f"raw routes: {json.dumps(routes, indent=2)}\n" + versions,
        )

    if not routes:
        _fail("terminal route dump subprocess returned zero routes", versions)

    return routes


@pytest.fixture(scope="session")
def terminal_route_spec() -> dict:
    """path -> sorted list of fully-qualified dependency names, from a clean
    subprocess import. Non-vacuity (and every other partial-answer shape) is
    enforced inside ``_run_terminal_route_dump`` -- every test consuming this
    fixture fails loudly, with the raw dump attached, never silently passing
    on a truncated or unparsable result.
    """
    routes = _run_terminal_route_dump()
    return {r["path"]: r["dependencies"] for r in routes}


class TestTerminalRouterDependencyWiring:
    """Structural proof of the fix: the admin dependency moved off the WS
    routes and stayed on the HTTP ones. This is the assertion #14998 itself
    is about.
    """

    def test_websocket_routes_carry_no_admin_dependency(self, terminal_route_spec):
        for path in ("/ws/{session_id}", "/ws/ssh/{host_id}"):
            assert path in terminal_route_spec, f"route {path} missing from a clean import"
            assert _ADMIN_DEP not in terminal_route_spec[path], f"{path} must not carry the router-level admin Depends"

    def test_http_routes_keep_the_admin_dependency(self, terminal_route_spec):
        assert "/" in terminal_route_spec, "route / missing from a clean import"
        assert _ADMIN_DEP in terminal_route_spec["/"], "HTTP routes must keep check_admin_permission"


class TestTerminalToolRoutesKeepTheirGate:
    """`api/terminal_tools.py` declares no dependency of its own (#15084):
    those four routes install packages and run system commands, and have only
    ever been protected by inheriting the parent router's admin check.
    Splitting that parent for the WebSocket fix moved every HTTP route onto
    `admin_router` -- and would have handed these to anonymous callers had the
    include site not moved with them.
    """

    @staticmethod
    def _match(spec, suffix):
        """The single route whose path ends with *suffix*, or an explicit failure.

        Asserting uniqueness is what keeps a suffix match honest: two routes
        ending the same way would let a gated one vouch for an ungated one.
        """
        hits = [p for p in spec if p and p.endswith(suffix)]
        assert len(hits) == 1, f"expected exactly one route ending {suffix}, found {sorted(hits)} in {sorted(spec)}"
        return hits[0]

    def test_every_tool_route_is_present(self, terminal_route_spec):
        """Non-vacuity: if the routes move, the gate assertions below guard nothing."""
        assert terminal_route_spec, "the route dump was empty -- every assertion below would pass vacuously"
        for suffix in _TOOL_SUFFIXES:
            self._match(terminal_route_spec, suffix)

    @pytest.mark.parametrize("suffix", _TOOL_SUFFIXES)
    def test_tool_route_keeps_the_admin_dependency(self, terminal_route_spec, suffix):
        path = self._match(terminal_route_spec, suffix)
        assert _ADMIN_DEP in terminal_route_spec[path], (
            f"{path} runs system commands and has no dependency of its own -- "
            "it must stay on a router that carries the admin check"
        )


class TestTerminalWebsocketRouteHandshake:
    """Real handshake on /ws/{session_id} via TestClient -- not a handler call."""

    @pytest.fixture
    def owned_session_id(self):
        import uuid

        session_id = str(uuid.uuid4())
        session_manager.session_configs[session_id] = {
            "session_id": session_id,
            "owner": "alice",
            "security_level": "standard",
        }
        yield session_id
        session_manager.session_configs.pop(session_id, None)

    def test_authenticated_owner_connects(self, terminal_client, owned_session_id):
        """#14960 AC3, made checkable: the real route accepts the owner."""
        fake_terminal = MagicMock()
        fake_terminal.cleanup = AsyncMock()

        with (
            patch("auth_middleware.authenticate_websocket", new=AsyncMock(return_value={"username": "alice"})),
            patch("api.terminal._init_terminal_handler", new=AsyncMock(return_value=fake_terminal)),
            patch("api.terminal._run_terminal_message_loop", new=AsyncMock()),
            _accept_spy() as calls,
        ):
            with terminal_client.websocket_connect(f"/ws/{owned_session_id}") as ws:
                pass

        assert len(calls) == 1

    def test_unauthenticated_caller_is_refused_not_500(self, terminal_client, owned_session_id):
        """#14998: before the fix this handshake 500s inside solve_dependencies
        for EVERY caller, admin or not. After the fix, an unauthenticated
        caller reaches the explicit per-route guard and is refused cleanly.
        """
        from starlette.websockets import WebSocketDisconnect

        with _no_ws_credentials(), _accept_spy() as calls:
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with terminal_client.websocket_connect(f"/ws/{owned_session_id}"):
                    pass

        assert exc_info.value.code == 1008
        assert len(calls) == 0


class TestSshTerminalWebsocketRouteHandshake:
    """Real handshake on /ws/ssh/{host_id} via TestClient -- not a handler call."""

    def test_authenticated_admin_connects(self, terminal_client):
        fake_terminal = MagicMock()
        fake_terminal.start = AsyncMock(return_value=False)

        with (
            patch(
                "auth_middleware.authenticate_websocket",
                new=AsyncMock(return_value={"username": "admin-bob", "role": "admin"}),
            ),
            patch("api.terminal._setup_ssh_terminal", new=AsyncMock(return_value=fake_terminal)),
            patch.object(ssh_terminal_manager, "close_session", new=AsyncMock()),
            _accept_spy() as calls,
        ):
            with terminal_client.websocket_connect("/ws/ssh/prod-host-1") as ws:
                pass

        assert len(calls) == 1

    def test_unauthenticated_caller_is_refused_not_500(self, terminal_client):
        from starlette.websockets import WebSocketDisconnect

        with _no_ws_credentials(), _accept_spy() as calls:
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with terminal_client.websocket_connect("/ws/ssh/prod-host-1"):
                    pass

        assert exc_info.value.code == 1008
        assert len(calls) == 0


class TestTerminalHttpRouteAdminGate:
    """The HTTP routes on this router keep check_admin_permission, exercised
    through the real ASGI request path via FastAPI's dependency_overrides --
    the standard way to prove a specific dependency actually gates a route
    without depending on this test harness's always-pass auth stub. Stays
    in-process (unlike the structural checks above): dependency_overrides
    needs object identity with the live app/router under test.
    """

    def test_non_admin_is_rejected(self, terminal_app, terminal_client):
        def _deny():
            raise HTTPException(status_code=403, detail="Admin permission required for this operation")

        terminal_app.dependency_overrides[check_admin_permission] = _deny
        try:
            response = terminal_client.get("/")
        finally:
            terminal_app.dependency_overrides.pop(check_admin_permission, None)

        assert response.status_code == 403

    def test_admin_reaches_the_handler(self, terminal_app, terminal_client):
        terminal_app.dependency_overrides[check_admin_permission] = lambda: True
        try:
            response = terminal_client.get("/")
        finally:
            terminal_app.dependency_overrides.pop(check_admin_permission, None)

        assert response.status_code == 200


class TestRouterLevelDependsBreaksWebSocketScope:
    """Contrast mutation (#14998): reproduces the reported cause in isolation,
    with a genuinely ``Request``-typed dependency (the test harness's
    ``auth_middleware`` stub deliberately uses a no-arg signature to dodge an
    unrelated FastAPI validation issue -- #10472 -- so it can't reproduce this
    one). Proves both that the broken shape fails, and that the shape this fix
    uses does not.
    """

    @staticmethod
    def _admin_dep(request: Request) -> bool:
        return True

    def test_router_level_request_typed_depends_breaks_the_handshake(self):
        """The exact shape #14998 reports: one router, dependencies=[...] at
        construction, owning a @router.websocket route. Mirrors terminal.py
        before this fix.
        """
        broken_router = APIRouter(dependencies=[Depends(self._admin_dep)])

        @broken_router.websocket("/ws/broken")
        async def _ws_broken(websocket: WebSocket):
            await websocket.accept()
            await websocket.close()

        app = FastAPI()
        app.include_router(broken_router)
        client = TestClient(app, raise_server_exceptions=False)

        with pytest.raises(TypeError):
            with client.websocket_connect("/ws/broken"):
                pass

    def test_split_router_shape_does_not_break_the_handshake(self):
        """The shape this fix uses: the WS route stays on a router carrying no
        dependencies; the same admin Depends only reaches an HTTP-only router
        merged in afterward. Mirrors terminal.py's router/admin_router split.
        """
        plain_router = APIRouter()
        admin_router = APIRouter(dependencies=[Depends(self._admin_dep)])

        @plain_router.websocket("/ws/fixed")
        async def _ws_fixed(websocket: WebSocket):
            await websocket.accept()
            await websocket.close()

        @admin_router.get("/http-fixed")
        def _http_fixed():
            return {"ok": True}

        plain_router.include_router(admin_router)

        app = FastAPI()
        app.include_router(plain_router)
        client = TestClient(app, raise_server_exceptions=False)

        with client.websocket_connect("/ws/fixed"):
            pass


def _dump_routes_main() -> None:
    """Subprocess entrypoint (see ``_run_terminal_route_dump`` above): import
    ``api.terminal`` in a fresh interpreter and print its routes as JSON.

    Kept in this module, like ``core_test.py``'s ``_main``, so the isolation
    the tests need travels with them rather than living in a separate script.

    Reports each route's concrete type name alongside its path/dependencies,
    and the resolved fastapi/starlette/python versions, so a truncated result
    carries enough evidence in one subprocess call to diagnose without a
    second round-trip. That is how the defect below was found.

    Enumerates a **mounted app**, not the bare ``APIRouter``. Under fastapi
    0.141.1 / starlette 1.6.0 (what CI resolves), ``include_router`` no longer
    flattens the child's routes into ``parent.routes`` eagerly -- it appends a
    single deferred ``_IncludedRouter`` entry with no ``path``, and the child's
    routes materialise only when an app mounts it. Reading ``router.routes``
    there returned 3 entries instead of 26 (job 98088603289) while every route
    was perfectly fine at runtime. Mounting first is correct on both versions,
    and asks the question the guard actually cares about: what does the
    application serve, and with which dependencies.
    """
    import sys as _sys

    import fastapi as _fastapi
    import starlette as _starlette

    import api.terminal as terminal_module

    def _dep_names(route) -> list:
        """Every dependency callable on a leaf route, fully merged.

        ``route.dependant.dependencies`` is the set FastAPI actually resolves,
        already including anything inherited from the routers the route was
        included through -- which is exactly the question a gate check asks.
        ``route.dependencies`` is the un-merged declaration and is the fallback.
        """
        dependant = getattr(route, "dependant", None)
        if dependant is not None:
            return sorted(
                f"{dep.call.__module__}.{dep.call.__qualname__}"
                for dep in getattr(dependant, "dependencies", [])
                if getattr(dep, "call", None) is not None
            )
        return sorted(
            f"{dep.dependency.__module__}.{dep.dependency.__qualname__}"
            for dep in getattr(route, "dependencies", [])
            if getattr(dep, "dependency", None) is not None
        )

    wrapper_attrs: list = []

    def _walk(container, prefix: str) -> list:
        """Flatten deferred ``_IncludedRouter`` wrappers into real routes.

        Under fastapi 0.141.1 neither ``include_router`` nor mounting an app
        flattens eagerly: both leave a wrapper whose ``.original_router`` holds
        the real routes, and whose own path is ``None``. Same idiom the repo
        already uses in ``llc/tests/test_roles_routes_registered.py``,
        ``api/codebase_analytics/endpoints/impact_endpoint_test.py`` and
        ``api/self_capabilities_integration_test.py`` -- copied here rather than
        invented, though the fact that four files now carry it by hand is its
        own problem.
        """
        found = []
        for route in getattr(container, "routes", []) or []:
            original = getattr(route, "original_router", None)
            if original is not None:
                # The prefix passed to ``include_router`` is not on the wrapper's
                # ``.prefix`` -- CI job 98110125325 found ``/install-tool`` where
                # ``/terminal/install-tool`` was expected. Take whichever of the
                # two carries it, and report the wrapper's attributes so the next
                # run names the right one instead of costing another round-trip.
                sub_prefix = getattr(route, "prefix", "") or getattr(original, "prefix", "") or ""
                wrapper_attrs.append(
                    {
                        "type": type(route).__name__,
                        "wrapper_prefix": getattr(route, "prefix", None),
                        "original_prefix": getattr(original, "prefix", None),
                        "attrs": sorted(a for a in dir(route) if not a.startswith("_")),
                    }
                )
                found.extend(_walk(original, prefix + sub_prefix))
                continue
            path = getattr(route, "path", None)
            found.append(
                {
                    "path": None if path is None else prefix + path,
                    "type": type(route).__name__,
                    "dependencies": _dep_names(route),
                }
            )
        return found

    app = _fastapi.FastAPI()
    app.include_router(terminal_module.router)

    routes = [r for r in _walk(app, "") if not (r["path"] or "").startswith(("/openapi.json", "/docs", "/redoc"))]
    print(
        json.dumps(
            {
                "routes": routes,
                "wrappers": wrapper_attrs,
                "python": _sys.version,
                "fastapi": getattr(_fastapi, "__version__", "unknown"),
                "starlette": getattr(_starlette, "__version__", "unknown"),
            }
        )
    )


if __name__ == "__main__":
    _dump_routes_main()
