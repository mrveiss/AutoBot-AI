#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""End-to-end tests for the Chat Knowledge Management System.

Covers chat-context creation, file association, temporary-knowledge capture and
decisions, in-chat search, compilation and context retrieval against a running
backend (``/api/chat-knowledge/*``).

#14979: this module used to be an operational driver script wearing test names —
a class with ``__init__``, a ``run_all_tests`` loop and a ``main()`` that logged
a summary. pytest never collects a class that defines ``__init__``, so all seven
``test_*`` methods below collected **zero** items and had never run once. The
driver is gone (pytest is the driver now) and every method asserts instead of
returning ``True``/``False``, which the old loop only logged.
"""

import uuid
from typing import Any, Dict, Iterator, List

import pytest
import requests

from autobot_shared.live_service_probe import require_live_endpoint
from autobot_shared.ssot_config import config

# #12510: every test here issues real HTTP against a running backend, so the
# module must stay out of the unit gate (pytest -m "not integration ...").
pytestmark = pytest.mark.integration

# SSOT only — no hardcoded host, port or URL (#1618).
BACKEND_URL = config.backend_url
CHAT_KNOWLEDGE_API = "/api/chat-knowledge"

# One module constant rather than a literal at each call site, so the whole
# suite shares a single HTTP budget.
HTTP_TIMEOUT_SECONDS = 30.0

CHAT_TOPIC = "Python Development Best Practices"
CHAT_KEYWORDS = ["python", "fastapi", "async", "testing"]

KNOWLEDGE_ITEMS: List[Dict[str, Any]] = [
    {
        "content": (
            "FastAPI is a modern web framework for Python that provides automatic "
            "API documentation and high performance."
        ),
        "metadata": {"category": "framework", "importance": "high"},
    },
    {
        "content": "Use async/await for I/O operations to improve performance in FastAPI applications.",
        "metadata": {"category": "performance", "importance": "medium"},
    },
    {
        "content": "Pydantic models in FastAPI provide automatic request validation and serialization.",
        "metadata": {"category": "validation", "importance": "high"},
    },
]

# api/schemas_knowledge.py KnowledgeDecision members, one per KNOWLEDGE_ITEMS entry.
KNOWLEDGE_DECISIONS = ["add_to_kb", "keep_temporary", "add_to_kb"]

SEARCH_QUERIES = ["FastAPI framework", "async performance", "Pydantic validation"]

UPLOAD_FILE_NAME = "test_code.py"
UPLOAD_FILE_BODY = '''# Sample Python file associated with a chat by the upload test.


def sample_function() -> str:
    """Example function used as upload content."""
    return "Hello from test file"
'''


@pytest.fixture(autouse=True)
def _require_live_stack() -> None:
    """Skip when the AutoBot backend is absent (#14930).

    All seven tests drive ``/api/chat-knowledge/*`` over real HTTP. On a
    GitHub-hosted runner no backend exists, so an unguarded run would report a
    refused connection as a product failure rather than as "not exercised here".
    """
    require_live_endpoint(BACKEND_URL, what="the AutoBot backend API")


@pytest.fixture
def session(_require_live_stack: None) -> Iterator[requests.Session]:
    """One pooled HTTP session per test, closed on teardown.

    Replaces the deleted ``__init__``/``setup``/``cleanup`` trio: the session
    was instance state built in ``__init__``, which is exactly what stopped
    pytest collecting this class.
    """
    with requests.Session() as http:
        yield http


@pytest.fixture
def chat_context(session: requests.Session) -> str:
    """Create a knowledge context for a fresh chat id and return that id.

    The id is generated locally because no chat-creation route exists — the old
    ``setup()`` posted to ``/api/chats/new``, which the backend never served.
    ``/context/create`` is also what builds the lazily-constructed
    chat-knowledge manager that ``add_temporary``, ``pending``, ``decide`` and
    ``search`` read, so every test needs it before touching those routes.
    """
    chat_id = f"e2e-chat-{uuid.uuid4().hex[:12]}"
    payload = {"chat_id": chat_id, "topic": CHAT_TOPIC, "keywords": CHAT_KEYWORDS}
    data = _envelope(
        _post(session, f"{CHAT_KNOWLEDGE_API}/context/create", json=payload),
        f"POST {CHAT_KNOWLEDGE_API}/context/create",
    )
    assert (
        data.get("chat_id") == chat_id
    ), f"context/create echoed chat_id {data.get('chat_id')!r}, expected {chat_id!r}"
    return chat_id


def _post(session: requests.Session, path: str, **kwargs: Any) -> requests.Response:
    """POST to *path* on the backend with the shared timeout budget."""
    return session.post(f"{BACKEND_URL}{path}", timeout=HTTP_TIMEOUT_SECONDS, **kwargs)


def _get(session: requests.Session, path: str) -> requests.Response:
    """GET *path* from the backend with the shared timeout budget."""
    return session.get(f"{BACKEND_URL}{path}", timeout=HTTP_TIMEOUT_SECONDS)


def _envelope(response: requests.Response, description: str) -> Dict[str, Any]:
    """Assert *response* is a successful ``DataResponse`` envelope; return its ``data``."""
    assert response.status_code == 200, f"{description} returned HTTP {response.status_code}: {response.text[:200]}"
    body = response.json()
    assert body.get("success") is True, f"{description} returned a non-success envelope: {body}"
    data = body.get("data")
    assert isinstance(data, dict), f"{description} returned no data object: {body}"
    return data


def _add_temporary_knowledge(session: requests.Session, chat_id: str) -> List[str]:
    """Add every KNOWLEDGE_ITEMS entry to *chat_id* and return their knowledge ids."""
    knowledge_ids: List[str] = []
    path = f"{CHAT_KNOWLEDGE_API}/knowledge/add_temporary"

    for item in KNOWLEDGE_ITEMS:
        payload = {"chat_id": chat_id, "content": item["content"], "metadata": item["metadata"]}
        data = _envelope(_post(session, path, json=payload), f"POST {path}")
        knowledge_id = data.get("knowledge_id")
        assert knowledge_id, f"POST {path} returned no knowledge_id for {item['content'][:48]!r}: {data}"
        knowledge_ids.append(knowledge_id)

    return knowledge_ids


def _read_context(session: requests.Session, chat_id: str) -> Dict[str, Any]:
    """Return the stored knowledge context for *chat_id*."""
    path = f"{CHAT_KNOWLEDGE_API}/context/{chat_id}"
    return _envelope(_get(session, path), f"GET {path}")


def _read_pending(session: requests.Session, chat_id: str) -> List[Dict[str, Any]]:
    """Return the knowledge items awaiting a decision for *chat_id*."""
    path = f"{CHAT_KNOWLEDGE_API}/knowledge/pending/{chat_id}"
    data = _envelope(_get(session, path), f"GET {path}")
    items = data.get("pending_items")
    assert isinstance(items, list), f"GET {path} returned a non-list pending_items: {data}"
    return items


class TestChatKnowledgeSystem:
    """Chat context, file association, knowledge decisions and search over live HTTP."""

    def test_chat_context_creation(self, session: requests.Session, chat_context: str) -> None:
        """A created context is readable back with the topic and keywords it was given."""
        context = _read_context(session, chat_context)

        assert context.get("chat_id") == chat_context, f"context is for chat {context.get('chat_id')!r}"
        assert context.get("topic") == CHAT_TOPIC, f"context topic is {context.get('topic')!r}, expected {CHAT_TOPIC!r}"
        assert (
            context.get("keywords") == CHAT_KEYWORDS
        ), f"context keywords are {context.get('keywords')!r}, expected {CHAT_KEYWORDS!r}"

    def test_file_association(self, session: requests.Session, chat_context: str, tmp_path) -> None:
        """An uploaded file is stored and counted against the chat's context."""
        upload = tmp_path / UPLOAD_FILE_NAME
        upload.write_text(UPLOAD_FILE_BODY, encoding="utf-8")
        path = f"{CHAT_KNOWLEDGE_API}/files/upload/{chat_context}"

        with upload.open("rb") as handle:
            response = _post(
                session,
                path,
                files={"file": (UPLOAD_FILE_NAME, handle, "text/plain")},
                data={"association_type": "upload"},
            )
        data = _envelope(response, f"POST {path}")

        assert data.get("file_id"), f"POST {path} returned no file_id: {data}"
        file_count = _read_context(session, chat_context).get("file_count")
        assert file_count == 1, f"context reports {file_count} associated files after one upload, expected 1"

    def test_temporary_knowledge_addition(self, session: requests.Session, chat_context: str) -> None:
        """Every temporary knowledge item is stored under a distinct id and counted."""
        knowledge_ids = _add_temporary_knowledge(session, chat_context)

        assert len(set(knowledge_ids)) == len(KNOWLEDGE_ITEMS), (
            f"{len(KNOWLEDGE_ITEMS)} knowledge items produced {len(set(knowledge_ids))} distinct "
            f"ids: {knowledge_ids}"
        )
        count = _read_context(session, chat_context).get("temporary_knowledge_count")
        assert count == len(
            KNOWLEDGE_ITEMS
        ), f"context reports {count} temporary knowledge items, expected {len(KNOWLEDGE_ITEMS)}"

    def test_knowledge_retrieval_and_decisions(self, session: requests.Session, chat_context: str) -> None:
        """Pending items are returned for decision, and each applied decision retires one."""
        knowledge_ids = _add_temporary_knowledge(session, chat_context)
        pending = _read_pending(session, chat_context)

        assert {item.get("id") for item in pending} == set(
            knowledge_ids
        ), f"pending ids {[item.get('id') for item in pending]} do not match the added ids {knowledge_ids}"

        for item, decision in zip(pending, KNOWLEDGE_DECISIONS):
            payload = {"chat_id": chat_context, "knowledge_id": item["id"], "decision": decision}
            path = f"{CHAT_KNOWLEDGE_API}/knowledge/decide"
            data = _envelope(_post(session, path, json=payload), f"POST {path}")
            assert data.get("success") is True, f"decision {decision!r} on {item['id']} was not applied: {data}"

        remaining = _read_pending(session, chat_context)
        assert not remaining, f"{len(remaining)} items still pending after deciding all {len(pending)}"

    def test_chat_search(self, session: requests.Session, chat_context: str) -> None:
        """Every search query returns a well-formed, self-consistent result set."""
        _add_temporary_knowledge(session, chat_context)
        path = f"{CHAT_KNOWLEDGE_API}/search"

        for query in SEARCH_QUERIES:
            payload = {"query": query, "chat_id": chat_context, "include_temporary": True}
            data = _envelope(_post(session, path, json=payload), f"POST {path} ({query!r})")
            results = data.get("results")
            assert isinstance(results, list), f"search {query!r} returned a non-list results field: {data}"
            assert data.get("count") == len(
                results
            ), f"search {query!r} reported count {data.get('count')} for {len(results)} results"

    def test_chat_compilation(self, session: requests.Session, chat_context: str) -> None:
        """Compiling a chat that has no message history is refused, not fabricated."""
        payload = {
            "chat_id": chat_context,
            "title": "FastAPI Development Best Practices - Compiled Knowledge",
            "include_system_messages": False,
        }
        path = f"{CHAT_KNOWLEDGE_API}/compile"

        response = _post(session, path, json=payload)

        assert response.status_code != 200, (
            f"POST {path} returned HTTP 200 for chat {chat_context}, which has no message history — "
            f"compilation must not invent a knowledge-base entry: {response.text[:200]}"
        )

    def test_context_retrieval(self, session: requests.Session, chat_context: str) -> None:
        """A retrieved context carries the full counted summary the UI renders."""
        _add_temporary_knowledge(session, chat_context)
        context = _read_context(session, chat_context)

        for key in ("topic", "keywords", "created_at", "updated_at", "file_count", "persistent_knowledge_count"):
            assert key in context, f"context for {chat_context} is missing {key!r}: {sorted(context)}"

        assert context["temporary_knowledge_count"] == len(
            KNOWLEDGE_ITEMS
        ), f"context reports {context['temporary_knowledge_count']} temporary items, expected {len(KNOWLEDGE_ITEMS)}"
