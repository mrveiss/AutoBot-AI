# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Structural proof of the terminal router's dependency wiring (#14998).

Split out of ``terminal_websocket_route_test.py`` (#14961): that file had
grown past the 600-line guard, and the seam its own docstring already
described is the one taken here. Two questions lived in one module -- *which
dependencies does the mounted router attach to which routes* (answered by
importing ``api.terminal`` in a clean subprocess and enumerating the mounted
app), and *what does a real client experience on the wire* (answered by
``TestClient`` handshakes). The first needs no fixtures, no fakeredis and no
auth stubbing; the second needs all three. They are now separate modules.

This module holds the first: the router-level ``Depends(check_admin_permission)``
must be absent from both ``@router.websocket`` routes (the #14998 fix itself)
and present on the HTTP routes. The subprocess entrypoint ``_dump_routes_main``
lives here too, so the isolation the assertions depend on travels with them.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

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

    Bootstraps via ``-c`` and a dotted import (``api.terminal_router_dependency_wiring_test``)
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
    bootstrap = "import api.terminal_router_dependency_wiring_test as m; m._dump_routes_main()"
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
                sub_prefix = getattr(route, "prefix", "") or getattr(original, "prefix", "") or ""
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
                "python": _sys.version,
                "fastapi": getattr(_fastapi, "__version__", "unknown"),
                "starlette": getattr(_starlette, "__version__", "unknown"),
            }
        )
    )


if __name__ == "__main__":
    _dump_routes_main()
