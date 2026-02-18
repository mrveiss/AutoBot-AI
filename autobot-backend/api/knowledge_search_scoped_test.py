#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for knowledge_search_scoped.py ChromaDB permission filter (Issue #934).

Tests:
- permission_where is computed and passed to kb.search() as filters=
- post-processing filter removes inaccessible results
- extract_user_context_from_request handles dict and ORM users
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_user_dict(user_id="u1", org_id="org1"):
    return {"user_id": user_id, "org_id": org_id, "role": "user"}


def _make_request():
    request = MagicMock()
    return request


def _make_kb(search_results=None):
    """Return a mock kb with search() returning search_results."""
    kb = MagicMock()
    kb.ownership_manager = AsyncMock()
    kb.search = AsyncMock(return_value=search_results or [])
    return kb


# ---------------------------------------------------------------------------
# extract_user_context_from_request — dict user
# ---------------------------------------------------------------------------


def test_extract_context_dict_with_ids():
    """Dict user with user_id and org_id extracts correctly."""
    from knowledge.search_filters import extract_user_context_from_request

    user = {"user_id": "abc123", "org_id": "org999", "role": "admin"}
    uid, org_id, groups = extract_user_context_from_request(user)

    assert uid == "abc123"
    assert org_id == "org999"
    assert groups == []  # no team info in dict-based auth


def test_extract_context_dict_no_org():
    """Dict user without org_id returns None org."""
    from knowledge.search_filters import extract_user_context_from_request

    user = {"user_id": "abc123"}
    uid, org_id, groups = extract_user_context_from_request(user)

    assert uid == "abc123"
    assert org_id is None
    assert groups == []


def test_extract_context_dict_fallback_username():
    """Dict user with only username falls back correctly."""
    from knowledge.search_filters import extract_user_context_from_request

    user = {"username": "admin", "role": "admin"}
    uid, org_id, groups = extract_user_context_from_request(user)

    assert uid == "admin"
    assert org_id is None


def test_extract_context_orm_user():
    """ORM User object extracts id, org_id, and team memberships."""
    from knowledge.search_filters import extract_user_context_from_request

    mock_user = MagicMock()
    mock_user.id = "user-uuid"
    mock_user.org_id = "org-uuid"

    team1 = MagicMock()
    team1.team_id = "team-1"
    team1.team = MagicMock(is_deleted=False)

    deleted_team = MagicMock()
    deleted_team.team_id = "team-deleted"
    deleted_team.team = MagicMock(is_deleted=True)

    mock_user.team_memberships = [team1, deleted_team]

    uid, org_id, groups = extract_user_context_from_request(mock_user)

    assert uid == "user-uuid"
    assert org_id == "org-uuid"
    assert groups == ["team-1"]  # deleted team excluded


# ---------------------------------------------------------------------------
# scoped_search: permission_where passed to kb.search
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scoped_search_passes_filters_to_kb():
    """permission_where is computed and passed as filters= to kb.search()."""
    from api.knowledge_search_scoped import ScopedSearchRequest, scoped_search

    user = _make_user_dict()
    result_doc = {
        "id": "fact1",
        "content": "hello",
        "metadata": {"owner_id": "u1", "visibility": "private"},
    }
    kb = _make_kb(search_results=[result_doc])

    fake_where = {"$or": [{"owner_id": "u1"}, {"visibility": "system"}]}

    with (
        patch(
            "api.knowledge_search_scoped.get_or_create_knowledge_base",
            new=AsyncMock(return_value=kb),
        ),
        patch(
            "api.knowledge_search_scoped.augment_search_request_with_permissions",
            new=AsyncMock(return_value=fake_where),
        ),
        patch(
            "api.knowledge_search_scoped.filter_search_results_by_permission",
            new=AsyncMock(return_value=[result_doc]),
        ),
    ):
        req = ScopedSearchRequest(query="hello")
        result = await scoped_search(
            search_request=req,
            request=_make_request(),
            current_user=user,
        )

    # kb.search must have been called with filters=fake_where
    kb.search.assert_called_once()
    call_kwargs = kb.search.call_args.kwargs
    assert call_kwargs.get("filters") == fake_where

    assert result["filtered_by_permissions"] is True
    assert result["total_results"] == 1


@pytest.mark.asyncio
async def test_scoped_search_no_kb_raises_503():
    """Missing knowledge base returns 503."""
    from api.knowledge_search_scoped import ScopedSearchRequest, scoped_search
    from fastapi import HTTPException

    with patch(
        "api.knowledge_search_scoped.get_or_create_knowledge_base",
        new=AsyncMock(return_value=None),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await scoped_search(
                search_request=ScopedSearchRequest(query="test"),
                request=_make_request(),
                current_user=_make_user_dict(),
            )

    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_scoped_search_post_filter_removes_inaccessible():
    """filter_search_results_by_permission strips facts user cannot access."""
    from api.knowledge_search_scoped import ScopedSearchRequest, scoped_search

    user = _make_user_dict(user_id="u1")
    accessible = {"id": "f1", "content": "mine", "metadata": {"owner_id": "u1"}}
    private_other = {
        "id": "f2",
        "content": "not mine",
        "metadata": {"owner_id": "u99", "visibility": "private"},
    }
    kb = _make_kb(search_results=[accessible, private_other])

    with (
        patch(
            "api.knowledge_search_scoped.get_or_create_knowledge_base",
            new=AsyncMock(return_value=kb),
        ),
        patch(
            "api.knowledge_search_scoped.augment_search_request_with_permissions",
            new=AsyncMock(return_value={"owner_id": "u1"}),
        ),
        patch(
            "api.knowledge_search_scoped.filter_search_results_by_permission",
            new=AsyncMock(return_value=[accessible]),  # strips private_other
        ),
    ):
        result = await scoped_search(
            search_request=ScopedSearchRequest(query="test"),
            request=_make_request(),
            current_user=user,
        )

    assert result["total_results"] == 1
    assert result["results"][0]["id"] == "f1"


# ---------------------------------------------------------------------------
# knowledge/search.py — ChromaDB where filter threading
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_passes_filters_to_query_chromadb():
    """KnowledgeSearcher.search() threads filters= to _query_chromadb via where=."""
    from knowledge.search import KnowledgeSearcher

    searcher = KnowledgeSearcher.__new__(KnowledgeSearcher)
    searcher._tag_filter = None
    searcher._keyword_searcher = None
    searcher._hybrid_searcher = None

    # Mock vector_store so ensure_initialized and _validate pass
    searcher.vector_store = MagicMock()

    where_filter = {"owner_id": "u1"}
    query_embedding = [0.1] * 768
    chromadb_result = {"documents": [[]], "metadatas": [[]], "distances": [[]]}

    with (
        patch.object(
            searcher,
            "ensure_initialized",
        ),
        patch.object(
            searcher,
            "_get_query_embedding",
            new=AsyncMock(return_value=query_embedding),
        ),
        patch.object(
            searcher,
            "_query_chromadb",
            new=AsyncMock(return_value=chromadb_result),
        ) as mock_query,
    ):
        await searcher.search(query="test", top_k=5, filters=where_filter)

    mock_query.assert_called_once_with(query_embedding, 5, where=where_filter)


@pytest.mark.asyncio
async def test_search_no_filters_omits_where():
    """When filters=None, _query_chromadb is called without where."""
    from knowledge.search import KnowledgeSearcher

    searcher = KnowledgeSearcher.__new__(KnowledgeSearcher)
    searcher._tag_filter = None
    searcher._keyword_searcher = None
    searcher._hybrid_searcher = None
    searcher.vector_store = MagicMock()

    query_embedding = [0.1] * 768
    chromadb_result = {"documents": [[]], "metadatas": [[]], "distances": [[]]}

    with (
        patch.object(searcher, "ensure_initialized"),
        patch.object(
            searcher,
            "_get_query_embedding",
            new=AsyncMock(return_value=query_embedding),
        ),
        patch.object(
            searcher,
            "_query_chromadb",
            new=AsyncMock(return_value=chromadb_result),
        ) as mock_query,
    ):
        await searcher.search(query="test", top_k=5)

    mock_query.assert_called_once_with(query_embedding, 5, where=None)
