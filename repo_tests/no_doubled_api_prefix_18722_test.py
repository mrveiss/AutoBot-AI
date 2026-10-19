# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No router below ``/api`` declares a path or prefix that starts with ``/api`` (#18722).

Every router under ``autobot-backend/api`` and ``autobot-slm-backend/api`` is mounted below
``/api``. A decorator such as ``@router.get("/api/cache/stats")`` is therefore served at
``/api/system/api/cache/stats``: thirteen routes shipped that way. The detector reads the syntax
tree, so a docstring or comment showing such a path is not a declaration.

A route is a router's when its receiver is a ``*router`` name, a name the module binds from
``APIRouter(...)`` (``r = APIRouter()``), or -- conservatively -- any other name used as a route
decorator. A name bound from ``FastAPI(...)`` is the app itself: ``@app.get("/api/health")`` is a
root route, correct, and never flagged.

A segment named ``/api-keys`` or ``/api-endpoints`` is a different word, not the doubled prefix:
the match is ``/api`` followed by ``/`` or the end of the string.

``_ALLOWED`` is the explicit exception list (``(file, path) -> reason``). It is empty: the one
module that still names the doubled paths, as the sources of a 308 shim, does so in a dict
handed to ``add_deprecated_redirects``, not in a decorator, so it is not a declaration.
"""

from __future__ import annotations

import ast
import functools
import re

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_ROOTS = ("autobot-backend/api", "autobot-slm-backend/api")
_DOUBLED = re.compile(r"^/api(/|$)")
_ROUTE_METHODS = frozenset(
    {"get", "post", "put", "delete", "patch", "head", "options", "websocket", "api_route", "add_api_route"}
)
_ROUTER_NAME = re.compile(r"(^|_)router$")

#: ``(repo-relative file, declared path) -> reason``. Empty by design; see the module docstring.
_ALLOWED: dict[tuple[str, str], str] = {}


def _is_source_python(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    return rel.endswith(".py") and not (name.endswith("_test.py") or name.startswith("test_") or "/tests/" in rel)


def _population(root) -> list[str]:
    try:
        tracked = tracked_paths(root, *_ROOTS)
    except EmptyEnumeration:
        return []
    return [rel for rel in tracked if _is_source_python(rel)]


REACH = declare(
    "doubled-api-prefix-scan",
    discover=_population,
    # Mid-window, from REACH.window(); the arithmetic is on the PR, not here.
    floor=473,
    what="non-test python source",
    roots=_ROOTS,
    growth=60,
)


def _str_const(node: ast.AST | None) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _ctor_name(call: ast.Call) -> str | None:
    func = call.func
    return func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else None


def _bound_names(tree: ast.AST, ctor: str) -> frozenset[str]:
    """Names assigned from a ``<ctor>(...)`` call in this module (``r = APIRouter()``)."""
    names: set[str] = set()
    for node in ast.walk(tree):
        value = getattr(node, "value", None)
        if not (isinstance(node, (ast.Assign, ast.AnnAssign)) and isinstance(value, ast.Call)):
            continue
        if _ctor_name(value) != ctor:
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        names.update(t.id for t in targets if isinstance(t, ast.Name))
    return frozenset(names)


def _decorator_calls(tree: ast.AST) -> frozenset[int]:
    """``id()`` of every call used as a decorator -- the position a route is declared from."""
    return frozenset(
        id(d)
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        for d in node.decorator_list
        if isinstance(d, ast.Call)
    )


def _is_route_call(call: ast.Call, routers: frozenset[str], apps: frozenset[str], decorators: frozenset[int]) -> bool:
    """A route declaration on a router: a ``*router`` name, a name bound from ``APIRouter(...)``,
    or -- conservatively -- any receiver not bound from ``FastAPI(...)`` when it is a decorator.
    An app-level ``@app.get("/api/x")`` is a root route and is never doubled."""
    func = call.func
    if not (isinstance(func, ast.Attribute) and func.attr in _ROUTE_METHODS):
        return False
    base = func.value
    if not isinstance(base, ast.Name) or base.id in apps:
        return False
    return base.id in routers or bool(_ROUTER_NAME.search(base.id)) or id(call) in decorators


def _declared_path(call: ast.Call) -> str | None:
    """The first-argument (or ``path=``) string of a route call, else None."""
    if call.args:
        return _str_const(call.args[0])
    return next((_str_const(k.value) for k in call.keywords if k.arg == "path"), None)


def _is_router_ctor(call: ast.Call) -> bool:
    return _ctor_name(call) == "APIRouter"


def _is_router_include(call: ast.Call, apps: set[str]) -> bool:
    """``<router>.include_router(sub, prefix=...)``; on the FastAPI app, ``/api`` is the root mount."""
    func = call.func
    if not (isinstance(func, ast.Attribute) and func.attr == "include_router"):
        return False
    return not (isinstance(func.value, ast.Name) and func.value.id in apps)


def doubled_paths(source: str) -> list[str]:
    """Every route path and ``APIRouter(prefix=...)`` in `source` that starts with ``/api``."""
    tree = ast.parse(source)
    routers, apps = _bound_names(tree, "APIRouter"), _bound_names(tree, "FastAPI")
    decorators = _decorator_calls(tree)
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if _is_route_call(node, routers, apps, decorators):
            path = _declared_path(node)
        elif _is_router_ctor(node) or _is_router_include(node, apps):
            path = next((_str_const(k.value) for k in node.keywords if k.arg == "prefix"), None)
        else:
            continue
        if path is not None and _DOUBLED.match(path):
            found.append(path)
    return found


@functools.lru_cache(maxsize=1)
def _offenders() -> tuple[tuple[str, str], ...]:
    root = repo_root()
    hits = []
    for rel in REACH.examined(root):
        text = (root / rel).read_text(encoding="utf-8")
        if "/api" not in text:
            continue
        hits.extend((rel, p) for p in doubled_paths(text) if (rel, p) not in _ALLOWED)
    return tuple(hits)


#: The planted control: the exact shapes that shipped, each of which the detector must flag.
_PLANTED = (
    ('@router.get("/api/cache/stats")\nasync def f(): ...\n', ["/api/cache/stats"]),
    (
        '@router.post("/api/knowledge/facts/{fact_id}/share")\nasync def f(): ...\n',
        ["/api/knowledge/facts/{fact_id}/share"],
    ),
    ('router = APIRouter(tags=["x"], prefix="/api")\n', ["/api"]),
    ('router.add_api_route(path="/api/x", endpoint=f)\n', ["/api/x"]),
    ('@my_router.websocket("/api/ws")\nasync def f(): ...\n', ["/api/ws"]),
    # An APIRouter bound to a name that does not end in ``router`` (the gap the reviewer named).
    ('r = APIRouter()\n@r.get("/api/x")\nasync def f(): ...\n', ["/api/x"]),
    ('import fastapi\napi = fastapi.APIRouter()\n@api.post("/api/y")\nasync def f(): ...\n', ["/api/y"]),
    ('r: APIRouter = APIRouter()\nr.add_api_route("/api/z", f)\n', ["/api/z"]),
    # Unknown receiver used as a route decorator: flagged conservatively.
    ('@mystery.get("/api/q")\nasync def f(): ...\n', ["/api/q"]),
    # Composition: a router included into another router under an ``/api`` prefix (CodeRabbit, #18827).
    ('router.include_router(sub, prefix="/api/x")\n', ["/api/x"]),
)

#: Contrast: shapes that must NOT be flagged.
_CLEAN = (
    '@router.get("/cache/stats")\nasync def f(): ...\n',
    '@router.get("/api-keys")\nasync def f(): ...\n',
    'router = APIRouter(prefix="/api-endpoints")\n',
    '"""@router.get("/api/cache/stats")"""\nx = 1\n',
    '# @router.get("/api/cache/stats")\nx = 1\n',
    'client.get("/api/health")\n',
    # FastAPI(...) is the app itself: ``/api/health`` there is a root route, not a doubled one.
    'app = FastAPI()\n@app.get("/api/health")\nasync def f(): ...\n',
    'import fastapi\nsrv = fastapi.FastAPI()\n@srv.get("/api/health")\nasync def f(): ...\n',
    # Not a decorator and not a known router: a call, not a declaration.
    'resp = session.get("/api/health")\n',
    'add_deprecated_redirects(router, {("GET", "/api/cache/stats"): "/cache/stats"})\n',
    # The app's own include is the root mount, not a doubled prefix.
    'app = FastAPI()\napp.include_router(sub, prefix="/api")\n',
    'router.include_router(sub, prefix="/cache")\n',
)


@pytest.mark.parametrize(("source", "expected"), _PLANTED)
def test_the_detector_flags_each_planted_doubled_declaration(source: str, expected: list[str]) -> None:
    assert doubled_paths(source) == expected


@pytest.mark.parametrize("source", _CLEAN)
def test_the_detector_leaves_clean_shapes_alone(source: str) -> None:
    assert doubled_paths(source) == []


def test_the_scan_is_not_vacuous() -> None:
    """A tree of routers is the input: fewer than 100 route-declaring modules is a blind scan."""
    root = repo_root()
    routers = sum(1 for rel in REACH.examined(root) if "APIRouter" in (root / rel).read_text(encoding="utf-8"))
    assert routers >= 100, f"only {routers} modules under the api/ roots build an APIRouter"


def test_no_router_declares_a_path_starting_with_api() -> None:
    assert not _offenders(), (
        "#18722: these declare a path or prefix starting with /api inside a router that is already "
        f"mounted under /api, so they are served at /api/<mount>/api/...: {list(_offenders())}. "
        "Drop the /api and, for a path that already shipped, add_deprecated_redirects()."
    )
