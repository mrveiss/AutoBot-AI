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
never comes back, and the test fails. The real gate's non-admin 403 is
``auth_middleware.check_admin_permission``'s own contract (``raise_auth_error("AUTH_0003")``).
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


def test_every_explorer_route_carries_the_admin_gate():
    """A route left on a sign-in-only gate would be missing from the admin gate's dependants."""
    from api import knowledge_chroma

    for route in knowledge_chroma.router.routes:
        calls = {dependency.call for dependency in route.dependant.dependencies}
        assert knowledge_chroma.check_admin_permission in calls, route.path


def test_an_admin_passes_the_gate():
    client = AsyncMock()
    client.list_collections = AsyncMock(return_value=[])
    with patch("api.knowledge_chroma.get_async_chromadb_client", AsyncMock(return_value=client)):
        response = _client(lambda: True).get("/knowledge/chroma/collections")

    assert response.status_code == 200
