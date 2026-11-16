# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The route detector of the unconnected-code gate judges a route where it is served, by real callers (#20910).

Split from ``unconnected_code_gate_20512_test.py`` (the gate and its baseline rules), which holds the population
tests. Each case here plants a tree and states its control: the same shape that must NOT connect, or must not be
read, so a passing case cannot be a detector that matched nothing.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from repo_tests import _unconnected_routes as routes
from repo_tests._paths import repo_root
from repo_tests._unconnected_gate_fixtures import _ROUTE, _ROUTER, _WIRED, _fired, _plant, _state


class _NormMod:
    @staticmethod
    def norm_path(path: str) -> str:
        return path


def test_route_candidates_have_no_phantom_forms_20910() -> None:
    """Every candidate is mount + own prefix + path, with or without a registry mount: no form drops the own prefix."""
    cand = routes._candidates
    assert cand(_NormMod, "/x", "/own", ["/api"]) == ("/api/own/x",)
    assert cand(_NormMod, "/x", "", ["/api"]) == ("/api/x",)
    assert cand(_NormMod, "/x", "/own", [routes._UNREGISTERED_MOUNT]) == ("/own/x",)
    assert cand(_NormMod, "", "", [routes._UNREGISTERED_MOUNT]) == ("/",)


_PLANS_REL = "autobot-backend/api/planted_plans.py"
_PLANS = (
    'from fastapi import APIRouter\nrouter = APIRouter(prefix="/workflow-plans")\n\n\n'
    '@router.get("{path}")\nasync def h():\n    return {{}}\n'
)
_LLC_MOUNT = {
    "autobot-backend/initialization/router_registry/planted.py": 'R = [("api.planted_plans", "/llc", ["llc"], "plans")]\n'
}
_UNRELATED_LLC_CALLER = {"scripts/probe.py": 'URL = "/api/llc/work-items/{item_id}"\n'}


@pytest.mark.parametrize(
    ("label", "mount", "path", "served"),  # served: the mount and own prefix the route is really under
    [
        ("registry mount: reg + path lost the own prefix", _LLC_MOUNT, "/{plan_key}/gate", "/llc/workflow-plans"),
        ("no registry mount: the bare path dropped it", {}, "/llc/{plan_key}/gate", "/workflow-plans"),
    ],
)
def test_a_prefixed_route_with_no_caller_is_flagged_beside_an_unrelated_caller_20910(
    tmp_path: Path, label: str, mount: dict[str, str], path: str, served: str
) -> None:
    """#20910: `/api/llc/work-items/{id}` must not connect a `/workflow-plans` route through `/api/llc/{p}/gate`."""
    files = {_PLANS_REL: _PLANS.format(path=path), **mount, **_UNRELATED_LLC_CALLER}
    tree, audit = _plant(tmp_path, files)
    key = f"{_PLANS_REL}:GET {path}"
    assert routes.unconnected(tree, audit) == [key], label
    # Control: the old own-prefix-less candidate IS reached by that caller, so the first assert fails on old code.
    assert routes.unconnected(tree, audit, sites=[(_PLANS_REL, "GET", path, ("/llc/{p}/gate",))]) == [], label
    # Connected twin: a caller of the path the route is really served at connects it.
    real = {"scripts/real.py": f'URL = "/api{served}{path}"\n'}
    assert routes.unconnected(*_plant(tmp_path, {**files, **real})) == [], label


_SLM = "autobot-slm-backend"
_NESTED = {
    f"{_SLM}/main.py": 'from api import parent_router\n\napp.include_router(parent_router, prefix="/api")\n',
    f"{_SLM}/api/__init__.py": (
        "from .child import router as child_router\nfrom .parent import router as parent_router\n"
        "parent_router.include_router(child_router)\n"
    ),
    f"{_SLM}/api/parent.py": 'from fastapi import APIRouter\nrouter = APIRouter(prefix="/monitoring")\n',
    f"{_SLM}/api/child.py": _ROUTER.format(prefix="gpu", verb="get", path="nodes"),
    "scripts/probe.py": 'URL = "/api/monitoring/gpu/nodes"\n',
}


def test_a_route_under_a_nested_router_is_judged_at_its_parents_mount_20910(tmp_path: Path) -> None:
    """A registry-less backend's include graph: `/gpu` nested in `/monitoring`, mounted at `/api` by main.py."""
    tree, audit = _plant(tmp_path, _NESTED)
    mounts = audit.registry_prefixes(_SLM)
    assert mounts == {f"{_SLM}/api/parent.py": ["/api"], f"{_SLM}/api/child.py": ["/api/monitoring"]}, mounts
    assert routes.unconnected(tree, audit) == [], "the real 4-segment caller connects the nested route"
    # Control: the parent-less candidate the gate used to build does not match that caller.
    parentless = [(f"{_SLM}/api/child.py", "GET", "/nodes", ("/gpu/nodes",))]
    assert routes.unconnected(tree, audit, sites=parentless) == [f"{_SLM}/api/child.py:GET /nodes"]


_SLM_CALLER = "autobot-slm-frontend/src/composables/usePlanted.ts"
_IMPORT = "import { slmApiClient } from '@/utils/ApiClient'\n"
_LEDGER_WRAPPER = (
    "const BASE = '{base}'\nfunction read<T>(path: string) {{\n  return slmApiClient.rawRequest(`${{BASE}}${{path}}`)\n}}\n"
    "read<number>('/orphan')\n"
)
_METHOD_WRAPPER = (
    "async function apiRequest<T>(method: 'GET' | 'PUT', path: string) {{\n  return slmApiClient.get<T>(path)\n}}\n"
    "apiRequest<{{ total: number }}>('GET', '{path}')\n"
)


def _route_keys(tmp_path: Path, files: dict[str, str]) -> set[str]:
    return {k for k in _fired(tmp_path, files) if k.startswith("route:")}


@pytest.mark.parametrize(
    ("label", "caller", "control"),
    [
        (
            "named path constant",
            "const ORPHAN = '/planted/orphan'\nslmApiClient.post(ORPHAN, {})\n",
            "const ORPHAN = '/planted/other'\nslmApiClient.post(ORPHAN, {})\n",
        ),
        (
            "template-constant base",
            "const BASE = '/planted'\nslmApiClient.rawRequest(`${BASE}/orphan`)\n",
            "const BASE = '/elsewhere'\nslmApiClient.rawRequest(`${BASE}/orphan`)\n",
        ),
        (
            "local wrapper adding a constant prefix",
            _LEDGER_WRAPPER.format(base="/planted"),
            _LEDGER_WRAPPER.format(base="/planted").replace("slmApiClient.rawRequest", "fetch"),
        ),
        (
            "local wrapper taking the method first",
            _METHOD_WRAPPER.format(path="/planted/orphan"),
            _METHOD_WRAPPER.format(path="/planted/other"),
        ),
    ],
)
def test_a_client_call_through_a_constant_or_a_local_wrapper_connects_the_route_20910(
    tmp_path: Path, label: str, caller: str, control: str
) -> None:
    """`slmApiClient.post(NAME)`, `${BASE}/x`, `read('/x')` and `apiRequest('GET', '/x')` are calls of `/api/x`."""
    key = "route:autobot-backend/api/planted_route.py:GET /orphan"
    assert _route_keys(tmp_path, {**_ROUTE, **_WIRED, _SLM_CALLER: _IMPORT + caller}) == set(), label
    # Control: the same file shape naming another path, or handing the path to no client, leaves it unconnected.
    assert _route_keys(tmp_path, {**_ROUTE, **_WIRED, _SLM_CALLER: _IMPORT + control}) == {key}, label


_NEIGHBOURS = (
    "function label(path: string): string {\n  return path.trim()\n}\n"
    "async function load(path: string): Promise<{ ok: boolean }> {\n  return slmApiClient.get(path)\n}\n"
)


@pytest.mark.parametrize(("callee", "flagged"), [("label", True), ("load", False)])
def test_a_function_is_a_wrapper_only_by_its_own_body_20910(tmp_path: Path, callee: str, flagged: bool) -> None:
    """`label(path)` sits just above the real wrapper `load(path)`: only `load`'s body hands the path to a client."""
    caller = _IMPORT + _NEIGHBOURS + f"{callee}('/planted/orphan')\n"
    key = "route:autobot-backend/api/planted_route.py:GET /orphan"
    assert _route_keys(tmp_path, {**_ROUTE, **_WIRED, _SLM_CALLER: caller}) == ({key} if flagged else set())


_CLIENT_LOAD = "function load(path: string) {{\n  return slmApiClient.get({arg})\n}}\n"
_NESTED_LOAD = (
    "function label(path: string) {\n  function load(path: string) {\n    return slmApiClient.get(path)\n  }\n"
    "  return path.trim()\n}\nlabel('/planted/orphan')\n"
)


@pytest.mark.parametrize(
    ("label", "trap", "plain"),
    [
        (
            "a concatenated constant is not its first literal",
            "const URL = '/planted/orphan' + '/history'\nslmApiClient.get(URL)\n",
            "const URL = '/planted/orphan'\nslmApiClient.get(URL)\n",
        ),
        (
            "a template interpolation ends inside its own literal",
            "const URL = `/planted/orphan/${id}` + `${tail}`\nslmApiClient.get(URL)\n",
            "const URL = `/planted/orphan${tail ? `?${tail}` : ''}`\nslmApiClient.get(URL)\n",
        ),
        (
            "a direct client call in a trailing comment is not a call",
            "const shown = 1 // slmApiClient.get('/planted/orphan')\n",
            "const shown = 1\nslmApiClient.get('/planted/orphan')\n",
        ),
        (
            "a transformed wrapper argument is not the parameter",
            _CLIENT_LOAD.format(arg="path + '/history'") + "load('/planted/orphan')\n",
            _CLIENT_LOAD.format(arg="path") + "load('/planted/orphan')\n",
        ),
        (
            "a reassigned constant holds its latest value",
            "let url = '/planted/orphan'\nurl = '/planted/other'\nslmApiClient.get(url)\n",
            "let url = '/planted/other'\nurl = '/planted/orphan'\nslmApiClient.get(url)\n",
        ),
        (
            "a nested function's client call is not the outer function's",
            _NESTED_LOAD,
            _CLIENT_LOAD.format(arg="path").replace("load", "label") + "label('/planted/orphan')\n",
        ),
        (
            "a wrapper call in a trailing comment is not a call",
            _CLIENT_LOAD.format(arg="path") + "const shown = 1 // load('/planted/orphan')\n",
            _CLIENT_LOAD.format(arg="path") + "const shown = 1\nload('/planted/orphan')\n",
        ),
    ],
)
def test_only_a_whole_literal_reaching_a_client_untransformed_connects_the_route_20910(
    tmp_path: Path, label: str, trap: str, plain: str
) -> None:
    """Each trap names `/planted/orphan` without calling it; its plain twin calls it (#20910 review)."""
    key = "route:autobot-backend/api/planted_route.py:GET /orphan"
    assert _route_keys(tmp_path, {**_ROUTE, **_WIRED, _SLM_CALLER: _IMPORT + trap}) == {key}, label
    assert _route_keys(tmp_path, {**_ROUTE, **_WIRED, _SLM_CALLER: _IMPORT + plain}) == set(), label


_VUE_CALLER = "autobot-slm-frontend/src/views/PlantedView.vue"
#: An odd number of template apostrophes, and a `}` in a trailing comment before the client call. Read as one .ts
#: text, `Don't` opens a string that pairs with the next quotes, the comment sits inside a "string" and survives, its
#: `}` closes the body early and the wrapper is missed. Read per file (the script only), the comment is stripped.
_VUE_SCRIPT = (
    "async function load(path: string): Promise<void> {\n"
    "  const shape = 'ok' // reply shape: }\n"
    "  return slmApiClient.get(path)\n}\nload('{path}')\n"
)
_VUE = "<template><p>Don't</p></template>\n" '<script setup lang="ts">\n' + _IMPORT + _VUE_SCRIPT + "</script>\n"


@pytest.mark.parametrize(("path", "flagged"), [("/planted/orphan", False), ("/planted/other", True)])
def test_a_vue_wrapper_is_read_from_its_script_past_template_apostrophes_20910(
    tmp_path: Path, path: str, flagged: bool
) -> None:
    """`Don't` in the template must not shift the script's strings and keep its `}` comment; another path stays out."""
    files = {**_ROUTE, **_WIRED, _VUE_CALLER: _VUE.replace("{path}", path)}
    key = "route:autobot-backend/api/planted_route.py:GET /orphan"
    assert _route_keys(tmp_path, files) == ({key} if flagged else set())


_SSO = "autobot-slm-backend/api/sso_auth.py"


@pytest.mark.parametrize(("path", "flagged"), [("callback", False), ("other", True)])
def test_the_sso_redirect_uri_is_called_by_the_identity_provider_20910(
    tmp_path: Path, path: str, flagged: bool
) -> None:
    """GET /api/auth/sso/callback is a declared external caller; a sibling route under /auth/sso is not (control)."""
    files = {_SSO: _ROUTER.format(prefix="auth/sso", verb="get", path=path)}
    assert _route_keys(tmp_path, files) == ({f"route:{_SSO}:GET /{path}"} if flagged else set())


@pytest.mark.parametrize(("prefix", "read"), [("# Handle ", False), ("", True)])
def test_a_route_decorator_in_a_comment_is_not_a_route_20910(tmp_path: Path, prefix: str, read: bool) -> None:
    """`# Handle @router.get("/path") style` is prose; the same decorator as code is a route (control)."""
    body = (
        _ROUTE["autobot-backend/api/planted_route.py"] + f'\n{prefix}@router.get("/path")\nasync def g():\n    pass\n'
    )
    tree, audit = _plant(tmp_path, {"autobot-backend/api/planted_route.py": body})
    raws = {site[2] for site in routes.route_sites(tree, audit)}
    assert raws == ({"/orphan", "/path"} if read else {"/orphan"}), raws


@pytest.mark.parametrize(
    ("label", "path", "body"),
    [
        ("shell $VAR", "scripts/probe.sh", 'curl -s "$BACKEND_URL/api/planted/orphan"\n'),
        ("shell quoted base", "scripts/probe.sh", 'curl -s "$BASE"/api/planted/orphan\n'),
        ("shell ${VAR}", "scripts/probe.sh", "curl -s ${BASE}/api/planted/orphan\n"),
        ("python f-string", "scripts/probe.py", 'URL = f"{base}/api/planted/orphan"\n'),
        ("literal host and port", "scripts/probe.yml", "url: http://localhost:8001/api/planted/orphan\n"),
        ("jinja variable", "scripts/probe.yml", 'url: "{{ backend_url }}/api/planted/orphan"\n'),
    ],
)
def test_a_non_frontend_caller_behind_a_url_base_connects_the_route_20910(
    tmp_path: Path, label: str, path: str, body: str
) -> None:
    """`$BASE/api/x`, `f"{base}/api/x"`, `host:8001/api/x` and `{{ var }}/api/x` are calls, not prose."""
    assert _fired(tmp_path, {**_ROUTE, **_WIRED, path: body}) == set(), label


def test_a_file_path_ending_in_api_is_not_a_caller_20910(tmp_path: Path) -> None:
    """`autobot-backend/api/x.py` names a file; it must not read as a call to `/api/x.py`."""
    decoy = {"scripts/note.sh": "# edit autobot-backend/api/planted/orphan\n"}
    assert _fired(tmp_path, {**_ROUTE, **_WIRED, **decoy}) == {"route:autobot-backend/api/planted_route.py:GET /orphan"}


def test_a_router_mounted_twice_is_judged_at_every_mount_20910() -> None:
    """A router served at its registry mount and at a nested include has a candidate path per mount."""
    assert routes._candidates(_NormMod, "/x", "", ["/a", "/a/sub"]) == ("/a/sub/x", "/a/x")
    assert routes._candidates(_NormMod, "/x", "/own", ["/a", "/a/sub"]) == ("/a/own/x", "/a/sub/own/x")


def test_the_real_nested_mount_of_a_registry_router_is_seen_20910() -> None:
    """knowledge_debug.py is mounted by the registry AND `include_router`ed under /debug by knowledge.py."""
    prefixes = _state(repo_root())[1].registry_prefixes("autobot-backend")["autobot-backend/api/knowledge_debug.py"]
    assert {"/knowledge_base", "/knowledge_base/debug"} <= set(prefixes), prefixes
