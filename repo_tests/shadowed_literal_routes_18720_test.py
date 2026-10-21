# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A literal route must not sit behind a ``{param}`` route of the same method (#18720).

Starlette tries routes in registration order and the first FULL match wins. A ``{param}`` (or
``{x:path}``) route registered earlier captures a later literal route, so the literal handler never runs:
the anonymous embed widget got the authenticated chat handler (401), the plugin audit panel got "plugin
'audit' not found", the SLM node conflicts list got "node not found". Per-router tests mount one router and
cannot see it; this reads the REAL registration order of both apps from source
(``autobot_shared/api_routing/route_order.py``) and asks Starlette's own compiled path regex.

Two checks:

1. **Per route** -- for each of the nine literals #18720 found, the first route in the app that matches the
   concrete URL is the literal's own declaration, not a sibling.
2. **The whole population** -- over every route of both apps, no literal route is fully matched by an
   earlier route of the same method. The list of offenders is empty and must stay empty.

What this cannot see, stated so an empty result reads correctly: routes added by ``add_api_route`` or in a
loop, a router mounted with a computed ``prefix=``, and anything outside ``/api`` mounts
(``/v1``, ``/.well-known``). A source it could not resolve is reported by :func:`_apps`, never counted as
"no routes".
"""

from __future__ import annotations

import functools
from dataclasses import dataclass
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare
from starlette.routing import compile_path

from autobot_shared.api_routing.route_order import (
    OrderedRoute,
    RouteOrder,
    backend_routes,
    shadowed_literals,
    slm_routes,
)

_BACKEND = "autobot-backend"
_SLM = "autobot-slm-backend"
_ROOT = repo_root()


@dataclass(frozen=True)
class _App:
    routes: list[OrderedRoute]
    modules: list[str]
    unresolved: list[str]


@functools.lru_cache(maxsize=4)
def _apps(root: Path) -> dict[str, _App]:
    out = {}
    for name, tree, reader in ((_BACKEND, _BACKEND, backend_routes), (_SLM, _SLM, slm_routes)):
        order = RouteOrder(root / tree)
        routes = reader(order)
        out[name] = _App(routes, [f"{tree}/{m}" for m in order.parsed], list(order.unresolved))
    return out


def _modules(root: Path) -> list[str]:
    return [m for app in _apps(root).values() for m in app.modules]


#: Measured on origin/main + this change: 361 backend + 53 SLM router modules read.
REACH = declare(
    "shadowed-literal-routes",
    discover=_modules,
    floor=394,
    growth=40,
    what="router modules read to rebuild registration order",
    roots=(_BACKEND, _SLM),
)


def first_match(routes: list[OrderedRoute], method: str, url: str) -> OrderedRoute | None:
    """The route Starlette would pick for *method* *url*: the first full match in order."""
    for route in routes:
        if route.method == method and compile_path(route.path)[0].match(url):
            return route
    return None


#: (app, method, concrete URL, the template that must win, module that must own it)
_LITERALS = [
    (_BACKEND, "POST", "/api/chats/embed/message", "/api/chats/embed/message", "api.chat_embed"),
    (_BACKEND, "GET", "/api/plugins/audit", "/api/plugins/audit", "plugin_manager"),
    (_BACKEND, "GET", "/api/batch-jobs/status", "/api/batch-jobs/status", "api.batch_jobs"),
    (_BACKEND, "GET", "/api/batch-jobs/chat-init", "/api/batch-jobs/chat-init", "api.batch_jobs"),
    (_BACKEND, "GET", "/api/vnc-proxy/desktop/status", "/api/vnc-proxy/{vnc_type}/status", "api.vnc_proxy"),
    (_BACKEND, "GET", "/api/permissions/memory/stats", "/api/permissions/memory/stats", "api.permissions"),
    (_BACKEND, "GET", "/api/a2a/trust/peer-1/audit", "/api/a2a/trust/{peer_id:path}/audit", "api.a2a_trust"),
    (_SLM, "GET", "/api/nodes/a2a-cards", "/api/nodes/a2a-cards", "api.nodes"),
    (_SLM, "GET", "/api/nodes/conflicts", "/api/nodes/conflicts", "api.services"),
]


@pytest.mark.parametrize(("app", "method", "url", "template", "module"), _LITERALS, ids=[c[2] for c in _LITERALS])
def test_literal_is_the_route_the_app_picks(app: str, method: str, url: str, template: str, module: str) -> None:
    winner = first_match(_apps(_ROOT)[app].routes, method, url)
    assert winner is not None, f"{method} {url} matches no route at all -- the reader lost it"
    assert (winner.path, winner.site.split(":")[0]) == (template, module), (
        f"{method} {url} is answered by {winner.path} ({winner.site}), not by {template} in {module}: "
        "a param route registered earlier captures it"
    )


@pytest.mark.parametrize("app", [_BACKEND, _SLM])
def test_no_literal_route_sits_behind_a_param_route(app: str) -> None:
    apps = _apps(_ROOT)[app]
    assert not apps.unresolved, f"{app}: could not read {apps.unresolved[:5]} -- NOT the same as clean"
    hits = shadowed_literals(apps.routes)
    assert not hits, "\n".join(f"{lit.method} {lit.path} ({lit.site}) <- {par.path} ({par.site})" for lit, par in hits)


def test_the_reach_floor_holds_over_both_apps() -> None:
    examined = REACH.examined(_ROOT)
    REACH.completed(len(examined), _ROOT)
    assert len(_apps(_ROOT)[_BACKEND].routes) > 1500 and len(_apps(_ROOT)[_SLM].routes) > 200


# -- the guard proved by plant -------------------------------------------------------------------------


def _r(method: str, path: str, site: str = "m:1") -> OrderedRoute:
    return OrderedRoute(method, path, site)


def test_planted_param_before_literal_is_reported() -> None:
    routes = [_r("GET", "/api/x/{id}", "m:1"), _r("GET", "/api/x/status", "m:9")]
    assert [(lit.path, par.path) for lit, par in shadowed_literals(routes)] == [("/api/x/status", "/api/x/{id}")]


def test_planted_path_converter_swallows_a_suffix() -> None:
    routes = [_r("GET", "/api/t/{p:path}"), _r("GET", "/api/t/a/audit")]
    assert len(shadowed_literals(routes)) == 1


def test_a_param_route_behind_an_earlier_param_route_is_reported() -> None:
    """Not only literals: ``{peer:path}/audit`` behind ``{peer:path}`` is the a2a shape (#18720)."""
    routes = [_r("GET", "/api/t/{p:path}"), _r("GET", "/api/t/{p:path}/audit")]
    assert [(r.path, prior.path) for r, prior in shadowed_literals(routes)] == [
        ("/api/t/{p:path}/audit", "/api/t/{p:path}")
    ]


def test_a_param_route_declared_first_is_not_reported() -> None:
    routes = [_r("GET", "/api/t/{p:path}/audit"), _r("GET", "/api/t/{p:path}")]
    assert shadowed_literals(routes) == []


def test_literal_first_and_other_shapes_are_not_reported() -> None:
    clean = [
        [_r("GET", "/api/x/status"), _r("GET", "/api/x/{id}")],  # the fixed order
        [_r("GET", "/api/x/{id}"), _r("POST", "/api/x/status")],  # other method: Starlette keeps looking
        [_r("GET", "/api/x/{id}"), _r("GET", "/api/x/a/b")],  # {id} stops at "/"
        [_r("GET", "/api/x/a"), _r("GET", "/api/x/{id}"), _r("GET", "/api/x/a")],  # earlier identical literal won
    ]
    assert [shadowed_literals(routes) for routes in clean] == [[], [], [], []]


def test_the_reader_keeps_decorator_and_include_order(tmp_path: Path) -> None:
    """The synthetic app has the defect in both of its shapes; the reader must put it in the order Python runs."""
    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "api" / "a.py").write_text(
        "from fastapi import APIRouter\n"
        'router = APIRouter(prefix="/a")\n'
        '@router.get("/{x}")\ndef one(): ...\n'
        '@router.get("/lit")\ndef two(): ...\n',
        encoding="utf-8",
    )
    (tmp_path / "api" / "b.py").write_text(
        'from fastapi import APIRouter\nrouter = APIRouter()\n@router.get("/a/b")\ndef three(): ...\n',
        encoding="utf-8",
    )
    (tmp_path / "main.py").write_text(
        "from api.a import router as a_router\nfrom api.b import router as b_router\n"
        'app.include_router(a_router, prefix="/api")\napp.include_router(b_router, prefix="/api")\n',
        encoding="utf-8",
    )
    order = RouteOrder(tmp_path)
    routes = slm_routes(order)
    assert [r.path for r in routes] == ["/api/a/{x}", "/api/a/lit", "/api/a/b"]
    assert [lit.path for lit, _ in shadowed_literals(routes)] == ["/api/a/lit", "/api/a/b"]
    assert not order.unresolved


def _api_route_app(tmp_path: Path, body: str) -> RouteOrder:
    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "api" / "p.py").write_text(
        "from fastapi import APIRouter\nrouter = APIRouter(prefix='/p')\n" + body, encoding="utf-8"
    )
    (tmp_path / "main.py").write_text(
        "from api.p import router as p_router\n" 'app.include_router(p_router, prefix="/api")\n', encoding="utf-8"
    )
    return RouteOrder(tmp_path)


def test_api_route_routes_are_read_and_a_catch_all_before_the_root_is_reported(tmp_path: Path) -> None:
    """``@router.api_route`` was invisible to the reader (#17325): the SLM personality proxy hid behind it."""
    order = _api_route_app(
        tmp_path,
        '@router.api_route("/{path:path}", methods=["GET", "POST"])\ndef a(): ...\n'
        '@router.api_route("/", methods=["GET"])\ndef b(): ...\n',
    )
    routes = slm_routes(order)
    assert [(r.method, r.path) for r in routes] == [
        ("GET", "/api/p/{path:path}"),
        ("POST", "/api/p/{path:path}"),
        ("GET", "/api/p/"),
    ]
    assert [(lit.method, lit.path) for lit, _ in shadowed_literals(routes)] == [("GET", "/api/p/")]


def test_api_route_with_non_literal_methods_is_unresolved_not_dropped(tmp_path: Path) -> None:
    order = _api_route_app(tmp_path, '@router.api_route("/x", methods=METHODS)\ndef a(): ...\n')
    assert slm_routes(order) == []
    assert any("non-literal route path or methods" in u for u in order.unresolved)


def test_api_route_without_methods_is_a_get_route(tmp_path: Path) -> None:
    """FastAPI defaults ``api_route`` to GET when ``methods=`` is omitted: readable, not unresolved."""
    order = _api_route_app(tmp_path, '@router.api_route("/x")\ndef a(): ...\n')
    assert [(r.method, r.path) for r in slm_routes(order)] == [("GET", "/api/p/x")]
    assert not order.unresolved
