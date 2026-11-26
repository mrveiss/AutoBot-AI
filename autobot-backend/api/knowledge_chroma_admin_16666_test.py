# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The raw ChromaDB explorer is admin-only (#16666).

It lists every collection and returns raw documents and metadata, so it bypasses fact
visibility entirely. The suite runs against an ``auth_middleware`` stub
(``testkit/auth_middleware_stub.py``), whose ``check_admin_permission`` approves every
caller. So, like ``tests/api/test_knowledge_cognition_auth_regression.py``, these tests
key ``dependency_overrides`` off the name this router bound at import. If a route loses
its ``Depends(check_admin_permission)``, the override can't reach it, the refusal below
never comes back, and the test fails. The last test loads the REAL ``check_admin_permission``
(``tests.conftest.load_real_auth_middleware``, the same approach as ``tests/api/test_router_auth_16375.py``)
and fakes only the identity the request carries. That drives its role logic end to end.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

_ROUTES = [
    ("GET", "/knowledge/chroma/collections", None),
    ("GET", "/knowledge/chroma/collections/docs", None),
    ("GET", "/knowledge/chroma/collections/docs/documents", None),
    ("POST", "/knowledge/chroma/collections/docs/search", {"query": "q"}),
    ("GET", "/knowledge/chroma/empty-collections", None),
    ("POST", "/knowledge/chroma/empty-collections/cleanup-requests", {"collection": "docs"}),
]


def _refuse_non_admin() -> bool:
    raise HTTPException(status_code=403, detail="Admin permission required")


def _client(gate) -> TestClient:
    from api import knowledge_chroma

    app = FastAPI()
    app.include_router(knowledge_chroma.router)
    app.dependency_overrides[knowledge_chroma.check_admin_permission] = gate
    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize(("method", "path", "body"), _ROUTES)
def test_a_non_admin_is_refused_on_every_explorer_route(method, path, body):
    response = _client(_refuse_non_admin).request(method, path, json=body)
    assert response.status_code == 403


def _served_explorer_routes() -> list:
    """The routes as the app serves them, with included routers' dependencies merged in.

    Newer FastAPI keeps an ``_IncludedRouter`` entry (no ``dependant``) in ``app.routes`` and builds each
    route's effective dependant lazily; ``iter_route_contexts`` yields those. Older FastAPI flattens into
    ``APIRoute`` entries directly.
    """
    from fastapi.routing import APIRoute

    from api import knowledge_chroma

    app = FastAPI()
    app.include_router(knowledge_chroma.router)
    try:
        from fastapi.routing import iter_route_contexts

        candidates = list(iter_route_contexts(app.routes))
    except ImportError:
        candidates = [route for route in app.routes if isinstance(route, APIRoute)]
    return [
        route
        for route in candidates
        if isinstance(getattr(route, "original_route", route), APIRoute) and route.path.startswith("/knowledge/chroma")
    ]


def test_every_explorer_route_carries_the_admin_gate():
    """A route left on a sign-in-only gate would be missing from the admin gate's dependants."""
    from api import knowledge_chroma

    routes = _served_explorer_routes()
    paths = {route.path for route in routes}
    assert "/knowledge/chroma/empty-collections" in paths, "the empty-collections routes must be served"
    for route in routes:
        calls = {dependency.call for dependency in route.dependant.dependencies}
        assert knowledge_chroma.check_admin_permission in calls, route.path


def test_an_admin_passes_the_gate():
    client = AsyncMock()
    client.list_collections = AsyncMock(return_value=[])
    with patch("api.knowledge_chroma.get_async_chromadb_client", AsyncMock(return_value=client)):
        response = _client(lambda: True).get("/knowledge/chroma/collections")

    assert response.status_code == 200


@pytest.mark.parametrize(
    ("user", "expected"),
    [(None, 401), ({"username": "u", "role": "user"}, 403), ({"username": "a", "role": "admin"}, 200)],
)
def test_the_real_admin_gate_refuses_non_admins(monkeypatch, user, expected):
    from types import SimpleNamespace

    from tests.conftest import load_real_auth_middleware

    real = load_real_auth_middleware()
    monkeypatch.setattr(real, "get_auth_middleware", lambda: SimpleNamespace(get_user_from_request=lambda _r: user))
    client = AsyncMock()
    client.list_collections = AsyncMock(return_value=[])
    with patch("api.knowledge_chroma.get_async_chromadb_client", AsyncMock(return_value=client)):
        response = _client(real.check_admin_permission).get("/knowledge/chroma/collections")

    assert response.status_code == expected
