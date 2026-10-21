# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""No (method, path) is registered twice in either app (#16908, #17325).

Starlette answers a request from the FIRST route that matches, so a second registration of the same
(method, path) is unreachable -- dead code that reads as a live endpoint, and a duplicate OpenAPI operation.
Which copy won was decided by the order of two lists in two files, and nothing checked it.

This guard reads the routes the way the running app registers them: ``autobot_shared/api_routing/route_order.py``
flattens each app in registration order, ``include_router`` composition and ``@router.api_route`` included
(the same read the #18720 shadow guard uses). It replaces the earlier AST guard, which had two blind spots
this one closes:

* it keyed ``module:var`` into a SET, so a router mounted twice under the same name collapsed to one entry
  (``chat_embed``, ``admin_retention_policies``, ``voice_bundle_user``, llc ``agent_hires``);
* it could not see ``include_router`` at all (``chat_sessions``, ``knowledge_boards``,
  ``knowledge_search_aggregator``, ``voice_bundle_admin``).

Here every occurrence is counted, so a repeat is a repeat whatever module or router object produced it.

What it cannot see, stated so a green run reads correctly: routes added by ``add_api_route`` or a loop, a
router mounted with a computed ``prefix=``, and anything outside the ``/api`` mounts. Source it could not
resolve is asserted empty, never counted as "no routes".
"""

from __future__ import annotations

import collections
import functools
from pathlib import Path

import pytest
from repo_tests._paths import repo_root

from autobot_shared.api_routing.route_order import (
    OrderedRoute,
    RouteOrder,
    backend_routes,
    slm_routes,
)

_BACKEND = "autobot-backend"
_SLM = "autobot-slm-backend"
_ROOT = repo_root()

#: Handler-level duplicates: two DIFFERENT implementations on one (method, path), not a double mount.
#: Resolving them is a judgement (they differ in declared auth and capability), owned by #18721 -- decision
#: pending. SHRINK-ONLY: entries leave when #18721 lands, and none may be added; a new duplicate is what
#: this guard is for.
#: Measured 2026-10-21: 364 backend and 53 SLM source files parsed; floors leave ~20% headroom.
BACKEND_PARSED_FLOOR = 290
SLM_PARSED_FLOOR = 42
KNOWN_DUPLICATES = {
    ("POST", "/api/voice/realtime/tools/call"): "#18721",
    ("GET", "/api/llc/agent/context/{item_id}"): "#18721",
}


#: app name -> source files the read parsed (the reach of the sweep), filled by ``_read``.
_PARSED: dict[str, int] = {}


@functools.lru_cache(maxsize=4)
def _read(root: Path) -> dict[str, tuple[list[OrderedRoute], list[str]]]:
    out = {}
    for name, reader in ((_BACKEND, backend_routes), (_SLM, slm_routes)):
        order = RouteOrder(root / name)
        out[name] = (reader(order), list(order.unresolved))
        _PARSED[name] = len(order.parsed)
    return out


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
    routes, unresolved = _read(_ROOT)[app]
    assert not unresolved, f"{app}: could not read {unresolved[:5]} -- this guard has NOT checked them"
    new = {k: v for k, v in duplicates(routes).items() if k not in KNOWN_DUPLICATES}
    assert not new, "\n".join(f"{m} {p} registered by {', '.join(sites)}" for (m, p), sites in sorted(new.items()))


def test_the_allowlist_only_lists_duplicates_that_still_exist() -> None:
    """A stale entry silently re-licenses the collision it named."""
    live = {key for routes, _ in _read(_ROOT).values() for key in duplicates(routes)}
    gone = set(KNOWN_DUPLICATES) - live
    assert not gone, f"these are fixed; remove them from KNOWN_DUPLICATES: {sorted(gone)}"


def test_the_allowlist_names_its_owning_issue() -> None:
    assert all(owner.startswith("#") for owner in KNOWN_DUPLICATES.values())


def test_the_reader_reached_both_apps() -> None:
    apps = _read(_ROOT)
    # Reach is the source files parsed, not the routes found: a route count can stay high while whole
    # modules silently stop being read. The route floors stay as a second, independent instrument.
    assert _PARSED[_BACKEND] > BACKEND_PARSED_FLOOR and _PARSED[_SLM] > SLM_PARSED_FLOOR, dict(_PARSED)
    assert len(apps[_BACKEND][0]) > 1500 and len(apps[_SLM][0]) > 200, "the route read has drifted and is blind"


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


def _planted_app(tmp_path: Path, main_body: str) -> list[OrderedRoute]:
    """A miniature SLM app: ``api.child`` has one route, ``api.parent`` composes it with include_router."""
    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "api" / "child.py").write_text(
        'from fastapi import APIRouter\nrouter = APIRouter()\n@router.get("/dup")\ndef one(): ...\n',
        encoding="utf-8",
    )
    (tmp_path / "api" / "parent.py").write_text(
        "from fastapi import APIRouter\nfrom api.child import router as child_router\n"
        "router = APIRouter()\nrouter.include_router(child_router)\n",
        encoding="utf-8",
    )
    (tmp_path / "main.py").write_text(
        "from api.child import router as child_router\nfrom api.parent import router as parent_router\n" + main_body,
        encoding="utf-8",
    )
    order = RouteOrder(tmp_path)
    routes = slm_routes(order)
    assert not order.unresolved
    return routes


def test_a_double_mount_through_include_router_is_caught(tmp_path: Path) -> None:
    """Contrast with the AST guard this replaces, which missed exactly this (#17325).

    ``parent`` already includes ``child``; ``main`` mounts ``child`` again directly.
    """
    routes = _planted_app(
        tmp_path, 'app.include_router(parent_router, prefix="/api")\napp.include_router(child_router, prefix="/api")\n'
    )
    assert duplicates(routes) == {("GET", "/api/dup"): ["api.child:3", "api.child:3"]}


def test_a_single_mount_through_include_router_is_clean(tmp_path: Path) -> None:
    routes = _planted_app(tmp_path, 'app.include_router(parent_router, prefix="/api")\n')
    assert [r.path for r in routes] == ["/api/dup"]
    assert duplicates(routes) == {}


def test_the_same_router_included_twice_into_one_parent_is_caught(tmp_path: Path) -> None:
    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "api" / "child.py").write_text(
        'from fastapi import APIRouter\nrouter = APIRouter()\n@router.get("/dup")\ndef one(): ...\n', encoding="utf-8"
    )
    (tmp_path / "api" / "parent.py").write_text(
        "from fastapi import APIRouter\nfrom api.child import router as child_router\n"
        "router = APIRouter()\nrouter.include_router(child_router)\nrouter.include_router(child_router)\n",
        encoding="utf-8",
    )
    (tmp_path / "main.py").write_text(
        'from api.parent import router as parent_router\napp.include_router(parent_router, prefix="/api")\n',
        encoding="utf-8",
    )
    routes = slm_routes(RouteOrder(tmp_path))
    assert len(duplicates(routes)[("GET", "/api/dup")]) == 2


def test_a_duplicate_websocket_route_is_caught(tmp_path: Path) -> None:
    """The AST guard this replaced counted ``@router.websocket``; the route read must too."""
    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "api" / "w.py").write_text(
        'from fastapi import APIRouter\nrouter = APIRouter()\n@router.websocket("/ws")\nasync def a(ws): ...\n'
        '@router.get("/ws")\ndef b(): ...\n',
        encoding="utf-8",
    )
    (tmp_path / "main.py").write_text(
        "from api.w import router as w_router\n"
        'app.include_router(w_router, prefix="/api")\napp.include_router(w_router, prefix="/api")\n',
        encoding="utf-8",
    )
    dupes = duplicates(slm_routes(RouteOrder(tmp_path)))
    assert set(dupes) == {("WEBSOCKET", "/api/ws"), ("GET", "/api/ws")}
