# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""No (method, path) is registered twice in either app (#16908, #17325).

Starlette answers a request from the FIRST route that matches, so a second registration of the same
(method, path) is unreachable -- dead code that reads as a live endpoint, and a duplicate OpenAPI operation.
Which copy won was decided by the order of two lists in two files, and nothing checked it.

The BACKEND is read from the real router objects: ``load_core_routers()`` and ``load_optional_routers()`` are the
two calls ``app_factory.py`` mounts from, and ``autobot_shared/api_routing/router_routes.effective_routes()``
resolves nested ``include_router`` with its prefix. The design is the one commit ``f4e2d6badb`` (#16908) built and
never landed; this revives it against the current loaders and replaces the AST guard, because two guards for one
property is a fork. The AST read it replaces was blind to ``add_api_route``, loop-built routes and computed
prefixes, and counted a router mounted twice as one entry. Here every occurrence is counted.

The SLM backend is read the same way: ``main.py`` builds its ``app`` at import, so the app's own router tree is
walked. Each app is dumped by ``repo_tests/_dump_real_routes.py`` in a child interpreter, because both apps ship
top-level ``api`` and ``config`` packages and cannot share a process (#17325, #19033).

What it cannot see, stated so a green run reads correctly: the three routers ``app_factory.py`` mounts
directly (``/v1`` OpenAI and Anthropic compat, ``/.well-known`` JWKS), and any route added after import. A route whose mount path cannot be recovered is asserted empty, never skipped.
"""

from __future__ import annotations

import collections
import functools
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from repo_tests._dump_real_routes import registered_routes as _registered
from repo_tests._paths import repo_root

_BACKEND = "autobot-backend"
_SLM = "autobot-slm-backend"
_ROOT = repo_root()

#: Population floors, measured 2026-10-24 under Python 3.14.6 / fastapi 0.141.1: backend 276 registry entries and
#: 2567 routes; SLM 56 top-level entries and 428 routes. Each floor leaves ~20% headroom.
FLOORS = {_BACKEND: (220, 2000), _SLM: (45, 340)}  # (registrations, routes)

#: Both children import a whole app; a hung import must fail the guard, not stall the shard (#17325).
_DUMP_TIMEOUT_S = 300


@dataclass(frozen=True)
class OrderedRoute:
    """One registered route: the method, the full served path, and the handler that answers it."""

    method: str
    path: str
    site: str


def registered_routes(entries: list[tuple[Any, str, Any, str]]) -> tuple[list[OrderedRoute], list[str]]:
    routes, unrecoverable = _registered(entries)
    return [OrderedRoute(*row) for row in routes], unrecoverable


@functools.lru_cache(maxsize=4)
def _dumps(root: Path) -> dict[str, dict[str, Any]]:
    """Both apps' JSON, dumped by two child interpreters running at once (the backend import dominates).

    A failed child fails the guard loudly; it never reads as an empty app.
    """
    script = str(root / "repo_tests" / "_dump_real_routes.py")
    kinds = {_BACKEND: "backend", _SLM: "slm"}
    procs = {
        app: subprocess.Popen(
            [sys.executable, script, kind, str(root)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        for app, kind in kinds.items()
    }
    out: dict[str, dict[str, Any]] = {}
    for app, proc in procs.items():
        try:
            stdout, stderr = proc.communicate(timeout=_DUMP_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            _kill_all(procs.values())
            pytest.fail(f"{app}: route dump did not finish within {_DUMP_TIMEOUT_S}s")
        assert proc.returncode == 0, f"{app}: route dump failed rc={proc.returncode}\n{stderr[-2000:]}"
        out[app] = json.loads(stdout.strip().splitlines()[-1])
    return out


def _kill_all(procs: Any) -> None:
    """Kill and reap every child, so a timed-out dump leaves no interpreter behind."""
    for proc in procs:
        proc.kill()
    for proc in procs:
        proc.communicate()


def _dump(root: Path, app: str) -> dict[str, Any]:
    return _dumps(root)[app]


def _read(root: Path) -> dict[str, tuple[list[OrderedRoute], list[str]]]:
    return {
        app: ([OrderedRoute(*row) for row in dump["routes"]], dump["unrecoverable"])
        for app in (_BACKEND, _SLM)
        for dump in (_dump(root, app),)
    }


def duplicates(routes: list[OrderedRoute]) -> dict[tuple[str, str], list[str]]:
    """``(method, path)`` -> the registering sites, for every pair registered more than once.

    Counts occurrences, not distinct sites: the same router mounted twice has ONE site and two entries.
    """
    seen: dict[tuple[str, str], list[str]] = collections.defaultdict(list)
    for route in routes:
        seen[(route.method, route.path)].append(route.site)
    return {key: sites for key, sites in seen.items() if len(sites) > 1}


@pytest.mark.parametrize("app", [_BACKEND, _SLM])
def test_no_route_is_registered_twice(app: str) -> None:
    routes, unrecoverable = _read(_ROOT)[app]
    assert not unrecoverable, f"{app}: could not recover the mount path of {unrecoverable[:5]}"
    dupes = duplicates(routes)
    assert not dupes, "\n".join(f"{m} {p} registered by {', '.join(sites)}" for (m, p), sites in sorted(dupes.items()))


@pytest.mark.parametrize("app", [_BACKEND, _SLM])
def test_the_reader_reached_the_app(app: str) -> None:
    """Reach first, routes second: a broken import must not let the guard pass by finding nothing."""
    assert reach_shortfall(_dump(_ROOT, app), FLOORS[app]) == []


def reach_shortfall(dump: dict[str, Any], floors: tuple[int, int]) -> list[str]:
    """Why *dump* does not show the reader reached its app; empty when it did.

    The floors catch a broken import that empties a whole group; ``optional_failed`` catches the one optional
    router the loader swallowed, which the ~20% floor headroom would let through. It is read from the registry's
    own per-entry load results, so the expected router list has one home: the registry configs.
    """
    registrations, route_floor = floors
    findings = [f"optional router not loaded: {entry}" for entry in dump["optional_failed"]]
    if dump["registrations"] <= registrations:
        findings.append(f"registrations {dump['registrations']} <= floor {registrations}")
    if len(dump["routes"]) <= route_floor:
        findings.append(f"routes {len(dump['routes'])} <= floor {route_floor}")
    return findings


def test_a_dump_below_the_floors_is_a_finding() -> None:
    dump = {"registrations": 3, "routes": [["GET", "/api/x", "s"]], "optional_failed": ["feature:x: ImportError"]}
    assert len(reach_shortfall(dump, (10, 10))) == 3


def test_a_dump_above_the_floors_is_not() -> None:
    dump = {"registrations": 11, "routes": [["GET", "/api/x", "s"]] * 11, "optional_failed": []}
    assert reach_shortfall(dump, (10, 10)) == []


# -- the guard proved by plant --------------------------------------------------------------------------


def _r(method: str, path: str, site: str) -> OrderedRoute:
    return OrderedRoute(method, path, site)


def test_the_same_router_mounted_twice_is_caught() -> None:
    """The set-collapse blind spot: one site, two registrations, was one entry and so was invisible."""
    routes = [_r("GET", "/api/x", "api.x:10"), _r("GET", "/api/x", "api.x:10")]
    assert duplicates(routes) == {("GET", "/api/x"): ["api.x:10", "api.x:10"]}


def test_distinct_routes_and_methods_are_not_duplicates() -> None:
    routes = [_r("GET", "/api/x", "m:1"), _r("POST", "/api/x", "m:2"), _r("GET", "/api/y", "m:3")]
    assert duplicates(routes) == {}


def test_a_duplicate_websocket_route_is_caught() -> None:
    """A WebSocket route only collides with another WebSocket route, never with a GET at the same path."""
    from fastapi import APIRouter

    router = APIRouter()
    router.add_api_websocket_route("/ws", lambda ws: None)
    router.add_api_websocket_route("/ws", lambda ws: None)
    router.add_api_route("/ws", lambda: None, methods=["GET"])
    routes, _ = registered_routes([(router, "", [], "w")])
    assert set(duplicates(routes)) == {("WEBSOCKET", "/api/ws")}


# -- the real-router read proved by plant (#17325) -------------------------------------------------------


def _router_with(path: str, prefix: str = "") -> Any:
    from fastapi import APIRouter

    router = APIRouter(prefix=prefix)
    router.add_api_route(path, lambda: None, methods=["GET"])
    return router


def _nested(child: Any) -> Any:
    from fastapi import APIRouter

    parent = APIRouter()
    parent.include_router(child, prefix="/inner")
    return parent


def test_a_duplicate_inside_an_included_sub_router_is_caught() -> None:
    """The case the AST guard missed: one route reached through ``include_router`` with its own prefix."""
    flat = _router_with("/inner/dup")
    nested = _nested(_router_with("/dup"))
    routes, unrecoverable = registered_routes([(flat, "/x", [], "flat"), (nested, "/x", [], "nested")])
    assert not unrecoverable
    assert set(duplicates(routes)) == {("GET", "/api/x/inner/dup")}


def test_a_two_level_include_prefix_is_recovered_whole() -> None:
    routes, unrecoverable = registered_routes([(_nested(_nested(_router_with("/leaf", "/own"))), "/p", [], "deep")])
    assert not unrecoverable
    assert [r.path for r in routes] == ["/api/p/inner/inner/own/leaf"]


def test_a_wrapper_hiding_its_prefix_is_unrecoverable_never_dropped() -> None:
    """A deferred-inclusion wrapper with no ``include_context`` hides its prefix: reported, not skipped."""
    from types import SimpleNamespace

    parent = SimpleNamespace(routes=[SimpleNamespace(original_router=_router_with("/hidden"))], prefix="")
    routes, unrecoverable = registered_routes([(parent, "/x", [], "wrapped")])
    assert routes == []
    assert unrecoverable == ["wrapped:/hidden"]


def test_the_same_router_registered_twice_by_the_registry_is_caught() -> None:
    router = _router_with("/dup")
    routes, _ = registered_routes([(router, "/x", [], "a"), (router, "/x", [], "a")])
    assert len(duplicates(routes)[("GET", "/api/x/dup")]) == 2


# -- which handler answers each formerly shared path (#18721) ---------------------------------------------


@pytest.mark.parametrize(
    ("method", "path", "handler"),
    [
        ("POST", "/api/voice/realtime/tools/call", "api.realtime_session.call_realtime_tool"),
        ("GET", "/api/llc/agent/context/{item_id}", "llc.api.agent_api.get_item_context"),
        ("GET", "/api/llc/context/{item_id}", "llc.api.context.get_context"),
    ],
)
def test_the_full_app_order_has_one_named_handler_per_path(method: str, path: str, handler: str) -> None:
    """The route list is in registration order, so a single entry here is the only handler Starlette can pick."""
    routes, _ = _read(_ROOT)[_BACKEND]
    sites = [r.site for r in routes if (r.method, r.path) == (method, path)]
    assert len(sites) == 1 and sites[0].endswith(handler), (method, path, sites)
