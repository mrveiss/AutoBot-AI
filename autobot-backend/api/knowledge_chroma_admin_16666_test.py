# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The raw ChromaDB explorer is admin-only (#16666).

It lists every collection and returns raw documents and metadata, so it bypasses fact
visibility entirely. These tests drive the real ``check_admin_permission`` through the
router. Only the identity it reads from the request is substituted, so a regression to
a sign-in-only gate fails here.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_ROUTES = [
    ("get", "/knowledge/chroma/collections", None),
    ("get", "/knowledge/chroma/collections/docs", None),
    ("get", "/knowledge/chroma/collections/docs/documents", None),
    ("post", "/knowledge/chroma/collections/docs/search", {"query": "q"}),
]


def _client_as(user: dict | None) -> TestClient:
    from api.knowledge_chroma import router

    app = FastAPI()
    app.include_router(router)
    middleware = MagicMock()
    middleware.get_user_from_request.return_value = user
    patchers = [
        patch("auth_middleware.get_auth_middleware", return_value=middleware),
        patch("auth_middleware.verify_internal_api_key", return_value=False),
    ]
    for patcher in patchers:
        patcher.start()
    client = TestClient(app, raise_server_exceptions=False)
    client.patchers = patchers  # type: ignore[attr-defined]
    return client


@pytest.fixture
def as_user():
    clients: list[TestClient] = []

    def make(user: dict | None) -> TestClient:
        clients.append(_client_as(user))
        return clients[-1]

    yield make
    for client in clients:
        for patcher in client.patchers:  # type: ignore[attr-defined]
            patcher.stop()


@pytest.mark.parametrize(("method", "path", "body"), _ROUTES)
def test_a_signed_in_non_admin_gets_403(as_user, method, path, body):
    response = as_user({"username": "u", "role": "user"}).request(method.upper(), path, json=body)
    assert response.status_code == 403


@pytest.mark.parametrize(("method", "path", "body"), _ROUTES)
def test_an_unauthenticated_caller_gets_401(as_user, method, path, body):
    response = as_user(None).request(method.upper(), path, json=body)
    assert response.status_code == 401


def test_an_admin_passes_the_gate(as_user):
    client = AsyncMock()
    client.list_collections = AsyncMock(return_value=[])
    with patch("api.knowledge_chroma.get_async_chromadb_client", AsyncMock(return_value=client)):
        response = as_user({"username": "a", "role": "admin"}).get("/knowledge/chroma/collections")

    assert response.status_code == 200
