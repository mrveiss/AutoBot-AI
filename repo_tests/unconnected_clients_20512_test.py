# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Relative calls through a base-URL client connect a route (#20512).

The route detector used to read only a literal ``/api/...``. ``slmApiClient.get('/api-keys')`` names no
``/api``, so ``/api-keys`` was baselined as dead while ``useApiKeyApi.ts`` called it. One control per
client form in ``_unconnected_clients``: a call that connects a planted route, and a decoy that must not.
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


def _fired(tmp_path: Path, files: dict[str, str]) -> set[str]:
    for rel, body in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(body, encoding="utf-8")
    tree = Tree(list(files), lambda rel: (tmp_path / rel).read_text(encoding="utf-8"))
    return uc.detected(tree, routes.Audit(tmp_path, scripts_root=repo_root()))


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
