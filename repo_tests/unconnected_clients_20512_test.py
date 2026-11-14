# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Relative calls through a base-URL client connect a route (#20512); a package router's mount is followed (#21428).

The route detector used to read only a literal ``/api/...``. ``slmApiClient.get('/api-keys')`` names no
``/api``, so ``/api-keys`` was baselined as dead while ``useApiKeyApi.ts`` called it. One control per
client form in ``_unconnected_clients``: a call that connects a planted route, and a decoy that must not.

The last group plants a registry-mounted package whose router is built two re-exports away from its
``__init__`` and ``include_router``s its endpoint modules: the routes are judged at their full mount path.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from repo_tests import _unconnected_code as uc
from repo_tests import _unconnected_routes as routes
from repo_tests._paths import repo_root
from repo_tests._unconnected_common import Tree

_ROUTE_FILE = "autobot-backend/api/planted_route.py"
_ROUTE_BODY = (
    'from fastapi import APIRouter\nrouter = APIRouter(prefix="/planted")\n\n\n'
    '@router.get("/orphan")\nasync def h():\n    return {}\n'
)
_PLANTED = {_ROUTE_FILE: _ROUTE_BODY, "scripts/wire.py": "import api.planted_route\n"}
_KEY = f"route:{_ROUTE_FILE}:GET /orphan"
_SLM = "autobot-slm-frontend/src"
_MAIN = "autobot-frontend/src"
_SLM_IMPORT = "import slmApiClient from '@/utils/ApiClient'\n"


def _plant(tmp_path: Path, files: dict[str, str]) -> tuple[Tree, routes.Audit]:
    for rel, body in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(body, encoding="utf-8")
    tree = Tree(list(files), lambda rel: (tmp_path / rel).read_text(encoding="utf-8"))
    return tree, routes.Audit(tmp_path, scripts_root=repo_root())


def _fired(tmp_path: Path, files: dict[str, str]) -> set[str]:
    tree, audit = _plant(tmp_path, files)
    return uc.detected(tree, audit)


_FORMS = [
    ("slmApiClient", f"{_SLM}/a.ts", _SLM_IMPORT + "slmApiClient.get('/planted/orphan')\n"),
    ("slmApiClient typed template", f"{_SLM}/a.ts", _SLM_IMPORT + "slmApiClient.post<X>(`/planted/${id}`, d)\n"),
    ("new SlmApiClient", f"{_SLM}/a.ts", "const c = new SlmApiClient()\nc.delete('/planted/orphan')\n"),
    (
        "makeAxiosCompatClient",
        f"{_SLM}/a.ts",
        "const client = makeAxiosCompatClient({})\nclient.put('/planted/orphan', d)\n",
    ),
    (
        "createAutobotBackendClient",
        f"{_SLM}/a.ts",
        "const client = createAutobotBackendClient()\nawait client.get<T>('/planted/orphan')\n",
    ),
    ("getSlmApiBase template", f"{_SLM}/a.vue", "fetch(`${getSlmApiBase()}/planted/orphan`)\n"),
    ("main apiClient", f"{_MAIN}/a.ts", "apiClient.get('/planted/orphan')\n"),
    ("main useApiClient", f"{_MAIN}/a.ts", "const api = useApiClient()\nawait api.get('/planted/orphan')\n"),
]


@pytest.mark.parametrize(("label", "rel", "body"), _FORMS, ids=[f[0] for f in _FORMS])
def test_a_relative_client_call_connects_a_planted_route(tmp_path: Path, label: str, rel: str, body: str) -> None:
    assert _KEY not in _fired(tmp_path, {**_PLANTED, rel: body}), label


@pytest.mark.parametrize(
    ("label", "rel", "body"),
    [
        ("nothing calls it", f"{_SLM}/a.ts", "const x = 1\n"),
        ("a test file", f"{_SLM}/a.test.ts", _SLM_IMPORT + "slmApiClient.get('/planted/orphan')\n"),
        ("a comment", f"{_SLM}/a.ts", "// slmApiClient.get('/planted/orphan')\n"),
        ("a receiver that is no known client", f"{_SLM}/a.ts", "other.get('/planted/orphan')\n"),
        ("the main client's name inside the SLM app", f"{_SLM}/a.ts", "apiClient.get('/planted/orphan')\n"),
        ("a mock directory", f"{_SLM}/mocks/a.ts", "slmApiClient.get('/planted/orphan')\n"),
    ],
)
def test_a_relative_call_that_does_not_count_leaves_the_route_unconnected(
    tmp_path: Path, label: str, rel: str, body: str
) -> None:
    assert _KEY in _fired(tmp_path, {**_PLANTED, rel: body}), label


def test_the_real_slm_api_key_calls_are_seen() -> None:
    """Known positive from the live tree: ``useApiKeyApi.ts`` calls ``/api-keys`` through ``slmApiClient``."""
    root = repo_root()
    tree, audit = Tree.of_repo(root), routes.Audit(root)
    seen = routes.client_calls(tree, routes.FRONTENDS, audit.mod.norm_path, audit.mod.FE_EXCLUDE_PATTERNS)
    assert "autobot-slm-frontend/src/composables/useApiKeyApi.ts" in seen.get("/api/api-keys", set())
    # Not re-detected here (a full sweep is ~30s and the gate test already runs one): the baseline no
    # longer carries the route, and the gate fails a detected key that is not in it.
    baseline = (root / uc.BASELINE_REL).read_text(encoding="utf-8")
    assert "route:autobot-slm-backend/api/api_keys.py" not in baseline


def test_a_call_whose_path_sits_on_the_next_line_is_seen(tmp_path: Path) -> None:
    """``client.post<T>(`` with the path on the next line is how long calls are formatted (``rebootNode``)."""
    body = _SLM_IMPORT + "slmApiClient.post<{ ok: boolean }>(\n  `/planted/orphan`\n)\n"
    assert _KEY not in _fired(tmp_path, {**_PLANTED, f"{_SLM}/a.ts": body})


_PARAM_ROUTE = {
    "autobot-backend/api/planted_param.py": (
        'from fastapi import APIRouter\nrouter = APIRouter(prefix="/planted")\n\n\n'
        '@router.get("/{provider}/x")\nasync def h(provider: str):\n    return {}\n'
    ),
    "scripts/wire.py": "import api.planted_param\n",
}
_PARAM_KEY = "route:autobot-backend/api/planted_param.py:GET /{provider}/x"


@pytest.mark.parametrize(
    ("label", "caller", "connected"),
    [
        ("an unrelated /y/x call", {f"{_MAIN}/a.ts": "api.get('/api/y/x')\n"}, False),
        ("an unrelated wildcard caller", {f"{_MAIN}/a.ts": "api.get(`/api/devices/${id}`)\n"}, False),
        ("a caller naming the router's prefix", {f"{_MAIN}/a.ts": "api.get('/api/planted/acme/x')\n"}, True),
    ],
)
def test_a_route_starting_with_a_parameter_is_reached_only_through_its_mounted_path(
    tmp_path: Path, label: str, caller: dict[str, str], connected: bool
) -> None:
    """``/{provider}/x`` unmounted matches every two-segment call; only ``/planted/<value>/x`` is its caller (#20512)."""
    assert (_PARAM_KEY not in _fired(tmp_path, {**_PARAM_ROUTE, **caller})) is connected, label


# ---------------------------------------------------------------------------
# A route included through a package-level router is judged at its full mount path (#21428). The shape
# is `api/codebase_analytics`: the registry names a package, `__init__` re-exports the router from
# `routes.py`, which re-exports it from `router.py`, which `include_router`s the endpoint modules.
# ---------------------------------------------------------------------------

_PKG = "autobot-backend/api/pkg"
_FE = "autobot-frontend/src/api.ts"
_PLAIN = "APIRouter()"


def _router_module(ctor: str, paths: tuple[str, ...] = (), imports: str = "", mounts: str = "") -> str:
    routes_ = "".join(f'\n\n@router.get("{p}")\nasync def h{i}():\n    return {{}}\n' for i, p in enumerate(paths))
    return f"from fastapi import APIRouter\n{imports}router = {ctor}\n{mounts}{routes_}"


def _package(endpoints: dict[str, str], hub: str, mount: str = "/mount") -> dict[str, str]:
    registry = f'ROUTERS = [\n    ("api.pkg", "{mount}", ["pkg"], "pkg"),\n]\n'
    files = {
        "autobot-backend/initialization/router_registry/feature.py": registry,
        f"{_PKG}/__init__.py": "from .routes import router\n",
        f"{_PKG}/routes.py": "from .router import router\n",
        f"{_PKG}/router.py": hub,
        f"{_PKG}/endpoints/__init__.py": "",
    }
    return {**files, **{f"{_PKG}/endpoints/{name}.py": body for name, body in endpoints.items()}}


_HUB = _router_module(
    _PLAIN,
    imports="from .endpoints import alpha, beta\n",
    mounts="router.include_router(alpha.router)\nrouter.include_router(beta.router)\n",
)
_TWO = {"alpha": _router_module(_PLAIN, ("/stats/deep",)), "beta": _router_module(_PLAIN, ("/solo",))}
_ALPHA, _BETA = f"route:{_PKG}/endpoints/alpha.py:GET /stats/deep", f"route:{_PKG}/endpoints/beta.py:GET /solo"


def _fired_routes(tmp_path: Path, files: dict[str, str]) -> set[str]:
    return {k for k in _fired(tmp_path, files) if k.startswith("route:")}


@pytest.mark.parametrize(
    ("label", "caller", "expected"),
    [
        ("the full path of a nested route is called", "get('/api/mount/stats/deep')", {_BETA}),
        ("the full path of a single-segment route is called", "get('/api/mount/solo')", {_ALPHA}),
        ("no caller at all: the detector can still fail", "", {_ALPHA, _BETA}),
        ("only the unmounted forms are called", "get('/api/stats/deep')\nget('/api/solo')", {_ALPHA, _BETA}),
        ("an unrelated /api/<name> literal", "get(`/api/${name}`)", {_ALPHA, _BETA}),
    ],
)
def test_routes_behind_a_package_router_chain_are_judged_at_their_mount_path_21428(
    tmp_path: Path, label: str, caller: str, expected: set[str]
) -> None:
    files = {**_package(_TWO, _HUB), **({_FE: caller + "\n"} if caller else {})}
    assert _fired_routes(tmp_path, files) == expected, label


def _leaf_hub(own: str, mounts: str, imports: str) -> str:
    return _router_module(f'APIRouter(prefix="{own}")' if own else _PLAIN, imports=imports, mounts=mounts)


@pytest.mark.parametrize(
    ("label", "caller", "fires"),
    [
        ("every prefix level named", "/api/mount/v1/inc/own/leaf", False),
        ("the include prefix missing", "/api/mount/v1/own/leaf", True),
        ("the hub's own prefix missing", "/api/mount/inc/own/leaf", True),
    ],
)
def test_the_own_prefix_and_the_include_prefix_both_compose_21428(
    tmp_path: Path, label: str, caller: str, fires: bool
) -> None:
    hub = _leaf_hub("/v1", 'router.include_router(alpha.router, prefix="/inc")\n', "from .endpoints import alpha\n")
    alpha = _router_module('APIRouter(prefix="/own")', ("/leaf",))
    files = {**_package({"alpha": alpha}, hub), _FE: f"get('{caller}')\n"}
    assert _fired_routes(tmp_path, files) == ({f"route:{_PKG}/endpoints/alpha.py:GET /leaf"} if fires else set()), label


@pytest.mark.parametrize(("caller", "fires"), [("/api/mount/outer/mid/leaf", False), ("/api/mount/outer/leaf", True)])
def test_a_router_included_two_levels_down_keeps_every_prefix_21428(tmp_path: Path, caller: str, fires: bool) -> None:
    hub = _leaf_hub("", "router.include_router(outer.router)\n", "from .endpoints import outer\n")
    outer = _leaf_hub("/outer", 'router.include_router(inner.router, prefix="/mid")\n', "from . import inner\n")
    files = {**_package({"outer": outer, "inner": _router_module(_PLAIN, ("/leaf",))}, hub), _FE: f"get('{caller}')\n"}
    assert _fired_routes(tmp_path, files) == ({f"route:{_PKG}/endpoints/inner.py:GET /leaf"} if fires else set())


def test_a_re_export_cycle_and_an_include_cycle_both_terminate_21428(tmp_path: Path) -> None:
    # `routes.py` and `router.py` re-export each other: no file builds the router, so nothing is mounted.
    looped = _package({}, "from .routes import router\n")
    _, audit = _plant(tmp_path, looped)
    assert audit.registry_prefixes("autobot-backend") == {}
    # `alpha` and `beta` include each other: each is mounted once and the walk stops.
    pair = {
        "alpha": _router_module(_PLAIN, imports="from . import beta\n", mounts="router.include_router(beta.router)\n"),
        "beta": _router_module(_PLAIN, imports="from . import alpha\n", mounts="router.include_router(alpha.router)\n"),
    }
    _, audit = _plant(tmp_path, _package(pair, _HUB))
    mounted = audit.registry_prefixes("autobot-backend")
    assert {rel: ps for rel, ps in mounted.items() if rel.startswith(_PKG)} == {
        f"{_PKG}/router.py": ["/mount"],
        f"{_PKG}/endpoints/alpha.py": ["/mount"],
        f"{_PKG}/endpoints/beta.py": ["/mount"],
    }


def test_the_codebase_analytics_shape_resolves_and_leaves_an_uncalled_route_flagged_21428(tmp_path: Path) -> None:
    """Parenthesised and aliased imports, a router built with `dependencies=`, trailing comments on the includes."""
    guarded = "APIRouter(\n    dependencies=[Depends(check_admin_permission)],\n)"
    imports = "from .endpoints import ownership  # Issue #248\n"
    imports += "from .endpoints import (\n    charts,  # Issue #1\n    stats,\n)\n"
    imports += "from .endpoints import queue as queue_router\n"
    mounts = "router.include_router(charts.router)\nrouter.include_router(stats.router)  # Issue #2\n"
    mounts += "router.include_router(ownership.router)\nrouter.include_router(queue_router.router)\n"
    endpoints = {
        "charts": _router_module(_PLAIN, ("/analytics/charts",)),
        "stats": _router_module(_PLAIN, ("/embedding-stats",)),
        "queue": _router_module(_PLAIN, ("/index/queue",)),
        "ownership": _router_module('APIRouter(prefix="/ownership")', ("/expertise",)),
    }
    hub = _router_module(guarded, imports=imports, mounts=mounts)
    callers = "get('/api/analytics/codebase/analytics/charts')\nget('/api/analytics/codebase/index/queue')\n"
    callers += "get(`/api/${page}`)\n"
    fired = _fired_routes(tmp_path, {**_package(endpoints, hub, "/analytics/codebase"), _FE: callers})
    assert fired == {
        f"route:{_PKG}/endpoints/stats.py:GET /embedding-stats",
        f"route:{_PKG}/endpoints/ownership.py:GET /expertise",
    }


def test_the_real_package_router_mounts_are_seen_21428() -> None:
    """The three package shapes on the live tree: a hub two re-exports down, a `router.py` hub, a router in `__init__`."""
    root = repo_root()
    mounts = routes.Audit(root, scripts_root=root).registry_prefixes("autobot-backend")
    assert "/analytics/codebase" in mounts["autobot-backend/api/codebase_analytics/endpoints/charts.py"]
    assert "/redis" in mounts["autobot-backend/api/redis_mcp/router.py"]
    assert "" in mounts["autobot-backend/llc/api/__init__.py"]
