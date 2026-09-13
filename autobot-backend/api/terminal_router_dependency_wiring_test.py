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

from autobot_shared.api_routing.mount_graph import build_graph

# --- clean-interpreter route/dependency enumeration (#14998, #15087) ---
#
# Every structural gate assertion below reads from this, never from an
# in-process ``terminal_router.routes`` walk bound at collection time.
#
# #15087 recorded such a walk finding **zero** matching routes under
# ``python-suite shard 12/12`` (CI job 98074498060) while passing locally, and
# read that as ``sys.modules`` pollution from a neighbouring test. It is not
# pollution. The mechanism is the fastapi version CI resolves (#15093):
# ``api/terminal.py`` ends with ``router.include_router(admin_router)``, and
# under fastapi >= 0.139 ``include_router`` **defers** -- it appends a single
# ``_IncludedRouter`` wrapper whose ``path`` is ``None`` instead of copying the
# child's routes onto the parent. The top level of ``api.terminal.router`` is
# therefore three entries there (the two WebSocket routes plus that wrapper --
# dumped verbatim by CI job 98088603289) against 26 on the older fastapi this
# repo resolves locally (#15091). Filtering those three by path for anything
# owned by ``admin_router`` -- every HTTP route, and the four tool routes a
# further level down -- yields precisely the reported empty set,
# ``StopIteration`` and "found 0".
#
# "Only under shard 12/12" was not a neighbour effect either.
# ``repo_tests/stable_shard.py`` assigns a module by sha256 of its own path, so
# shard 12 is the only shard that ever runs those files: there was no other
# shard for the result to differ from, and no polluter to find.
#
# A subprocess that imports ``api.terminal`` fresh and enumerates a **mounted
# app** is immune to both halves -- it asks what the application serves, which
# is the same question on either version.

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


@pytest.fixture(scope="session")
def terminal_tools_include_prefix() -> str:
    """The literal ``prefix=`` argument at ``api/terminal.py:198``, read from
    source rather than guessed at (#15126).

    ``_walk`` above cannot recover this: the value is consumed by
    ``include_router`` and never lands on a public attribute of the deferred
    wrapper it leaves behind (see ``mount_graph.py``'s module docstring for the
    one, private, unstable place it *does* land). The static mount graph reads
    the call site itself, so it means the same thing on every FastAPI shape.
    """
    backend_root = Path(__file__).resolve().parents[1]
    graph = build_graph(backend_root)
    edges = [
        e for e in graph.edges if e.parent == "api.terminal:admin_router" and e.child == "api.terminal_tools:router"
    ]
    assert edges, (
        "the api.terminal:admin_router -> api.terminal_tools:router mount "
        "(api/terminal.py:198) was not found in the static mount graph -- "
        "either the site moved or discovery regressed"
    )
    assert len(edges) == 1, f"expected exactly one such mount, found {len(edges)}: {edges}"
    prefix = edges[0].prefix
    assert prefix == "/terminal", (
        f"api/terminal.py:198's include-time prefix resolved to {prefix!r}, not "
        "'/terminal' -- either the literal argument at that call site changed, "
        "or Mount.prefix extraction regressed"
    )
    return prefix


class TestTerminalRouterDependencyWiring:
    """Structural proof of the fix: the admin dependency moved off the WS
    routes and stayed on the HTTP ones. This is the assertion #14998 itself
    is about.
    """

    def test_websocket_routes_carry_no_admin_dependency(self, terminal_route_spec):
        """The #14998 fix itself -- stated as an absence, so it needs a witness.

        ``_run_terminal_route_dump`` already refuses a dump with zero *routes*.
        Nothing until now refused a dump with zero *dependencies*, and that is
        the enumeration this assertion actually reads. An always-empty
        dependency list is not hypothetical: fastapi 0.141.1 reports a
        dependency inherited through ``include_router(dependencies=)`` as
        empty on the route object (CI job 98114928835), the same deferral that
        produced #15087. Under one, "the admin Depends is absent from the WS
        routes" holds for every router ever written, and this test reports the
        fix intact without having checked it. The witness below is the
        cheapest thing that cannot be true of an empty enumeration.
        """
        gated = sorted(path for path, deps in terminal_route_spec.items() if _ADMIN_DEP in deps)
        assert gated, (
            f"no route in the clean-import dump carries {_ADMIN_DEP} at all -- "
            "the dump is not resolving dependencies, so the absence asserted "
            "below is vacuous and proves nothing about the #14998 fix"
        )

        for path in ("/ws/{session_id}", "/ws/ssh/{host_id}"):
            assert path in terminal_route_spec, f"route {path} missing from a clean import"
            assert _ADMIN_DEP not in terminal_route_spec[path], f"{path} must not carry the router-level admin Depends"

    def test_http_routes_keep_the_admin_dependency(self, terminal_route_spec):
        assert "/" in terminal_route_spec, "route / missing from a clean import"
        assert _ADMIN_DEP in terminal_route_spec["/"], "HTTP routes must keep check_admin_permission"


class TestTerminalRouteDumpIsComplete:
    """#15087: the dump reached every level of the merged router, not just the top.

    The defect this guards against reads a router's ``.routes`` and stops
    there. Under fastapi >= 0.139 that is three entries for this module and
    the answer looks plausible -- the two WebSocket routes are genuinely at
    the top level, so nothing is obviously missing and nothing raises. Every
    gate assertion downstream then sweeps a surface with no HTTP routes in it
    and reports whatever an empty sweep reports.

    ``api.terminal`` nests three deep, which makes it a usable canary: a route
    declared on ``router``, a route declared on ``admin_router`` (included into
    ``router``), and a route from ``api.terminal_tools``' router (included into
    ``admin_router``). Naming one route per level means a walk that stops early
    fails saying *which* level it lost, instead of a downstream gate assertion
    naming only its own symptom.
    """

    #: One route per nesting level: ``(needle, owner)``. The third level
    #: (``api.terminal_tools``' router) has its own test below rather than a
    #: parametrize entry here, because it needs
    #: ``terminal_tools_include_prefix`` to match exactly instead of by suffix
    #: (#15126).
    _LEVELS = (
        ("/ws/{session_id}", "router -- declared directly, present even without flattening"),
        ("/", "admin_router -- included into router at the end of api/terminal.py"),
    )

    @pytest.mark.parametrize("needle,owner", _LEVELS)
    def test_the_dump_reaches_every_nesting_level(self, terminal_route_spec, needle, owner):
        assert needle in terminal_route_spec, (
            f"the dump holds no route at {needle}. That route is owned by "
            f"{owner}, so the walk never reached that inclusion at all. Every "
            "dependency assertion in this module sweeps that shortened surface.\n"
            f"dump held {len(terminal_route_spec)} route(s): {sorted(terminal_route_spec)}"
        )

    def test_the_dump_reaches_the_third_nesting_level(self, terminal_route_spec, terminal_tools_include_prefix):
        """``api.terminal_tools``' router, included into ``admin_router``, three deep.

        Matched exactly rather than by suffix (#15126): either the dump already
        holds the full served path (eager fastapi, #15091), or it holds that
        path with exactly the statically-derived include-time prefix removed
        (deferred fastapi, #15093) -- never merely "ends with".
        """
        served = "/terminal/package-managers"
        short = served[len(terminal_tools_include_prefix) :]
        assert served in terminal_route_spec or short in terminal_route_spec, (
            f"the dump holds neither {served!r} nor {short!r}. api.terminal_tools' "
            "router, included into admin_router, was never reached.\n"
            f"dump held {len(terminal_route_spec)} route(s): {sorted(terminal_route_spec)}"
        )


class TestTerminalRouteDumpPathReconstruction:
    """The dump's path, plus the statically-derived include-time prefix, equals
    the served path -- proven, not merely bounded as a limit (#15126).

    ``api/terminal.py:198`` is ``admin_router.include_router(tools_router,
    prefix="/terminal")``, and ``api.terminal_tools``' router carries no
    ``prefix`` of its own -- so that ``/terminal`` is purely the **include-time
    ``prefix=`` argument**. #15112 separated that term from the *including
    router's own* ``.prefix`` (recoverable from the route objects on every
    FastAPI shape) and found the include-time one unrecoverable through any
    *public* route attribute. It is not gone -- ``mount_graph.py``'s module
    docstring names the private, unstable attribute that does carry it, and why
    depending on that would be a worse bet than reading the call site.

    ``terminal_tools_include_prefix`` reads that literal from source, so it
    means the same thing on both FastAPI shapes. Reconstructing the served path
    from it and asserting equality is strictly stronger than the suffix-tolerant
    check this class replaces (formerly ``TestTerminalRouteDumpPathFidelity``):
    a suffix match cannot distinguish a correctly-recovered prefix from a
    coincidentally-matching one, and this can, because the prefix it checks
    against is independently derived rather than assumed.
    """

    #: The paths the application actually serves for the tool routes. Not an
    #: assumption: ``terminal_websocket_route_test.py``'s
    #: ``TestTerminalToolRoutesKeepTheirGate`` drives each of these through a
    #: real ``TestClient`` request and asserts a non-404 on both versions.
    _SERVED_TOOL_PATHS = (
        "/terminal/package-managers",
        "/terminal/install-tool",
        "/terminal/check-tool",
        "/terminal/validate-command",
    )

    @pytest.mark.parametrize("served", _SERVED_TOOL_PATHS)
    def test_dump_path_reconstructs_to_the_served_path(
        self, terminal_route_spec, terminal_tools_include_prefix, served
    ):
        short = served[len(terminal_tools_include_prefix) :]
        candidates = {served, short}
        matches = [p for p in terminal_route_spec if p in candidates]
        assert matches, (
            f"{served} is served by the application, but the dump holds neither "
            f"it nor {short!r} ({terminal_tools_include_prefix!r} + {short!r} "
            f"should equal {served!r}).\n"
            f"dump held {len(terminal_route_spec)} route(s): {sorted(terminal_route_spec)}"
        )
        assert len(matches) == 1, f"{served} matched more than one dumped path, so neither identifies it: {matches}"
        recovered = terminal_tools_include_prefix + matches[0] if matches[0] == short else matches[0]
        assert recovered == served, f"reconstructed {recovered!r} does not equal the served path {served!r}"


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
        the real routes, and whose own path is ``None``. This was one of four
        hand-rolled copies of that idiom; #15112 replaced the other three
        (``llc/tests/test_roles_routes_registered.py``,
        ``api/codebase_analytics/endpoints/impact_endpoint_test.py``,
        ``api/self_capabilities_integration_test.py``) with the shared
        ``autobot_shared.api_routing.router_routes`` traversal and left this one
        in place deliberately, gated on this issue (#15126).

        **This function's reconstructed prefix is still not trustworthy on its
        own, and a caller must not key an assertion on one without the help
        below.** Two different terms both read as "prefix" and only one of
        them survives deferral (#15112): the *including router's own*
        ``.prefix`` stays on the parent object and is recoverable, while an
        include-time ``prefix=`` **argument** is consumed at include time and
        is not exposed on any *public* attribute of the wrapper this function
        reads -- ``sub_prefix`` then resolves empty and the path comes back
        short. (It is not gone outright: verified against fastapi 0.141.1's own
        ``routing.py``, the private ``_IncludedRouter.include_context.prefix``
        carries the combined value. That is an internal, underscore-prefixed
        pair with no cross-version stability guarantee, so nothing here reads
        it -- see ``mount_graph.py`` for the same finding stated once, not
        copied.) ``api/terminal.py:198`` uses the include-time kind, so CI job
        98211256874 dumped ``/package-managers`` for a route the application
        serves at ``/terminal/package-managers``, while the eager fastapi this
        repo resolves locally (#15091) dumps it prefixed.

        Nothing in this module reads a *raw* prefixed path from ``_walk`` alone
        for that reason. ``TestTerminalRouteDumpPathReconstruction`` below
        supplies the missing piece from the static mount graph
        (``mount_graph.Mount.prefix``, read straight from
        ``api/terminal.py:198``) instead of guessing at a wrapper attribute or
        forking a private copy of that graph (#15093).
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
