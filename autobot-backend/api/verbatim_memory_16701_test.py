# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""GET /verbatim-memory/search and DELETE /verbatim-memory/session/{id} are
scoped to the caller (#16701). Search used to check only that the caller was
signed in and never filtered by user; any signed-in user could search every
user's verbatim conversation chunks. Delete's docstring claimed a production
middleware enforced session ownership; nothing in this file did.

Search's cross-user proof uses a real VerbatimStore over a mocked ChromaDB
collection (not a mock asserting call args), so this proves the route's own
scoping actually works end to end, not just that an argument was passed.
Delete's proof mounts the real router and overrides validate_session_ownership
the same way FastAPI would invoke it, so a refusal there is proven to happen
before the handler body ever runs.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from api.verbatim_memory import router as verbatim_router
from memory.verbatim_store import VerbatimStore
from security.session_ownership import validate_session_ownership

_STORED = [
    {"id": "a1", "text": "reset the system", "session_id": "s1", "role": "user", "user_id": "user-a"},
    {"id": "b1", "text": "reset the router", "session_id": "s2", "role": "user", "user_id": "user-b"},
]


def _make_collection(stored):
    """Minimal fake AsyncChromaCollection: $eq / $and-composite where support."""
    collection = MagicMock()

    def _conditions(where):
        if not where:
            return []
        return where["$and"] if "$and" in where else [where]

    async def _query(query_texts=None, n_results=10, where=None, include=None):
        items = stored
        for cond in _conditions(where):
            for field, op in cond.items():
                val = op.get("$eq")
                if val is not None:
                    items = [i for i in items if i.get(field) == val]
        limit = min(n_results, len(items))
        return {
            "ids": [[i["id"] for i in items[:limit]]],
            "documents": [[i["text"] for i in items[:limit]]],
            "metadatas": [[{"user_id": i.get("user_id", "")} for i in items[:limit]]],
            "distances": [[0.1 * j for j in range(limit)]],
        }

    collection.query = _query
    return collection


def _request_for(user_id: str) -> Request:
    """A minimal Request; only used to satisfy verbatim_search's signature here."""
    return MagicMock(spec=Request)


def _fake_auth_middleware(user_id: str | None):
    return SimpleNamespace(get_user_from_request=lambda _request: {"user_id": user_id} if user_id else None)


@pytest.mark.asyncio
async def test_search_never_returns_another_users_chunks():
    from api.verbatim_memory import verbatim_search

    store = VerbatimStore()
    store._collection = _make_collection(_STORED)

    with (
        patch("api.verbatim_memory.get_auth_middleware", return_value=_fake_auth_middleware("user-a")),
        patch("memory.verbatim_store.get_verbatim_store", new=AsyncMock(return_value=store)),
    ):
        result = await verbatim_search(_request_for("user-a"), q="reset", session_id=None, limit=10)

    ids = {r["id"] for r in result["results"]}
    assert ids == {"a1"}, f"user-a must not see user-b's chunk: {result['results']}"


@pytest.mark.asyncio
async def test_search_is_symmetric_for_the_other_user():
    from api.verbatim_memory import verbatim_search

    store = VerbatimStore()
    store._collection = _make_collection(_STORED)

    with (
        patch("api.verbatim_memory.get_auth_middleware", return_value=_fake_auth_middleware("user-b")),
        patch("memory.verbatim_store.get_verbatim_store", new=AsyncMock(return_value=store)),
    ):
        result = await verbatim_search(_request_for("user-b"), q="reset", session_id=None, limit=10)

    ids = {r["id"] for r in result["results"]}
    assert ids == {"b1"}, f"user-b must not see user-a's chunk: {result['results']}"


@pytest.mark.asyncio
async def test_search_requires_authentication():
    from api.verbatim_memory import verbatim_search

    with patch("api.verbatim_memory.get_auth_middleware", return_value=_fake_auth_middleware(None)):
        with pytest.raises(HTTPException) as exc_info:
            await verbatim_search(_request_for("anyone"), q="reset", session_id=None, limit=10)

    assert exc_info.value.status_code == 401


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(verbatim_router)
    return app


def test_delete_session_refuses_a_caller_who_does_not_own_it():
    """#16701: the route must run validate_session_ownership, not just 'is signed in'."""

    async def _refuse(session_id: str, request: Request):
        raise HTTPException(status_code=403, detail="not your session")

    app = _build_app()
    app.dependency_overrides[validate_session_ownership] = _refuse

    response = TestClient(app).delete("/verbatim-memory/session/s1")

    assert response.status_code == 403


def test_delete_session_allows_the_owner():
    async def _allow(session_id: str, request: Request):
        return {"user_id": "user-a"}

    app = _build_app()
    app.dependency_overrides[validate_session_ownership] = _allow

    with patch("memory.verbatim_store.get_verbatim_store") as get_store:
        store = AsyncMock()
        store.delete_session = AsyncMock(return_value=2)
        get_store.return_value = store

        response = TestClient(app).delete("/verbatim-memory/session/s1")

    assert response.status_code == 200, response.text
    assert response.json() == {"session_id": "s1", "deleted_count": 2}
