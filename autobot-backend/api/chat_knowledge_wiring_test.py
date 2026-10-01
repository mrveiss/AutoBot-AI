#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Route-level regression tests for the chat-knowledge manager wiring (#15160).

``api/chat_knowledge.py`` declared ``chat_knowledge_manager = None`` and never
assigned it. Six handlers dereferenced that module global, so every call raised
``AttributeError`` and returned HTTP 500 — while the health probe read the same
dead global and reported ``idle`` forever, hiding the outage from monitoring.

These tests exercise the **routes**, not the handler functions, and every one
asserts ``status != 404`` alongside its real assertion: a routing mistake must
fail the test rather than pass it for the wrong reason. Each success case also
asserts the stub manager's method was actually called with the request's own
arguments, so a "fix" that resolves the manager and then ignores it (inert
wiring) still fails.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.chat_knowledge as routes_module
import api.chat_knowledge_manager as manager_module
from api.chat_knowledge import router
from api.chat_knowledge_manager import (
    MANAGER_ERROR_STATE_KEY,
    MANAGER_STATE_KEY,
    ChatFileAssociation,
    ChatKnowledgeContext,
    probe_chat_knowledge,
)
from api.schemas_knowledge import FileAssociationType
from api.user_management.dependencies import get_current_user

API_PREFIX = "/api/chat-knowledge"
CHAT_ID = "chat-15160"


class StubChatKnowledgeManager:
    """Records every call so an inert (resolved-but-unused) fix cannot pass."""

    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        self.calls: list[tuple] = []
        self.chat_contexts = {
            CHAT_ID: ChatKnowledgeContext(
                chat_id=CHAT_ID,
                topic="wiring",
                keywords=["manager"],
                created_at=datetime.now(tz=timezone.utc),
                updated_at=datetime.now(tz=timezone.utc),
            )
        }
        self.file_associations = {
            CHAT_ID: [
                ChatFileAssociation(
                    file_id="file-from-manager",
                    chat_id=CHAT_ID,
                    file_path=f"{storage_dir}/notes.txt",
                    file_name="notes.txt",
                    association_type=FileAssociationType.UPLOAD,
                    size_bytes=11,
                )
            ]
        }

    async def associate_file(self, **kwargs):
        self.calls.append(("associate_file", kwargs))
        return ChatFileAssociation(
            file_id="assoc-from-manager",
            chat_id=kwargs["chat_id"],
            file_path=kwargs["file_path"],
            file_name="uploaded.txt",
            association_type=kwargs["association_type"],
        )

    async def add_temporary_knowledge(self, **kwargs):
        self.calls.append(("add_temporary_knowledge", kwargs))
        return "knowledge-from-manager"

    async def get_knowledge_for_decision(self, chat_id):
        self.calls.append(("get_knowledge_for_decision", {"chat_id": chat_id}))
        return [{"knowledge_id": "pending-from-manager", "content": "fact"}]

    async def apply_knowledge_decision(self, **kwargs):
        self.calls.append(("apply_knowledge_decision", kwargs))
        return True

    async def search_chat_knowledge(self, **kwargs):
        self.calls.append(("search_chat_knowledge", kwargs))
        return [{"content": "hit-from-manager", "score": 0.9}]


def _make_app(*, authenticated: bool = True) -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix=API_PREFIX)
    if authenticated:
        # #16375: the router is gated with `get_current_user`. These tests are
        # about manager WIRING, not about the gate, so the caller is stubbed in
        # rather than each test acquiring a credential. `authenticated=False`
        # exists for the one test that asserts the gate itself.
        app.dependency_overrides[get_current_user] = lambda: {
            "user_id": "wiring-test-user",
            "username": "wiring-test-user",
        }
    return app


@pytest.fixture
def stub_manager(tmp_path):
    return StubChatKnowledgeManager(str(tmp_path))


@pytest.fixture
def client(stub_manager):
    """Client with a warm manager already cached on app.state (the fixed path)."""
    app = _make_app()
    setattr(app.state, MANAGER_STATE_KEY, stub_manager)
    with TestClient(app) as test_client:
        yield test_client


def _call(client: TestClient, route: str):
    """Issue one request per broken route. Returns the response."""
    if route == "upload":
        return client.post(
            f"{API_PREFIX}/files/upload/{CHAT_ID}",
            files={"file": ("uploaded.txt", b"hello world", "text/plain")},
            data={"association_type": "upload"},
        )
    if route == "add_temporary":
        return client.post(
            f"{API_PREFIX}/knowledge/add_temporary",
            json={"chat_id": CHAT_ID, "content": "a temporary fact", "metadata": {"src": "test"}},
        )
    if route == "pending":
        return client.get(f"{API_PREFIX}/knowledge/pending/{CHAT_ID}")
    if route == "decide":
        return client.post(
            f"{API_PREFIX}/knowledge/decide",
            json={"chat_id": CHAT_ID, "knowledge_id": "k1", "decision": "keep_temporary"},
        )
    if route == "search":
        return client.post(
            f"{API_PREFIX}/search",
            json={"query": "redis", "chat_id": CHAT_ID, "include_temporary": True},
        )
    if route == "context":
        return client.get(f"{API_PREFIX}/context/{CHAT_ID}")
    raise AssertionError(f"unknown route {route!r}")


ALL_ROUTES = ["upload", "add_temporary", "pending", "decide", "search", "context"]


class TestSixRoutesNoLongerFiveHundred:
    """Every route that read the dead module global."""

    @pytest.mark.parametrize("route", ALL_ROUTES)
    def test_route_is_reached_and_does_not_500(self, client, route):
        response = _call(client, route)

        assert response.status_code != 404, f"{route} was not routed — test would pass for the wrong reason"
        assert response.status_code != 500, f"{route} returned 500: {response.text}"
        assert response.status_code == 200, response.text
        assert response.json()["success"] is True

    def test_upload_uses_the_manager_storage_dir_and_association(self, client, stub_manager):
        response = _call(client, "upload")

        assert response.status_code != 404
        assert response.status_code == 200, response.text
        body = response.json()["data"]
        assert body["file_id"] == "assoc-from-manager"
        assert body["file_path"].startswith(stub_manager.storage_dir)
        assert [name for name, _ in stub_manager.calls] == ["associate_file"]

    def test_add_temporary_passes_the_request_body_to_the_manager(self, client, stub_manager):
        response = _call(client, "add_temporary")

        assert response.status_code != 404
        assert response.json()["data"]["knowledge_id"] == "knowledge-from-manager"
        name, kwargs = stub_manager.calls[0]
        assert name == "add_temporary_knowledge"
        assert kwargs == {"chat_id": CHAT_ID, "content": "a temporary fact", "metadata": {"src": "test"}}

    def test_pending_returns_the_manager_items(self, client, stub_manager):
        response = _call(client, "pending")

        assert response.status_code != 404
        data = response.json()["data"]
        assert data["count"] == 1
        assert data["pending_items"][0]["knowledge_id"] == "pending-from-manager"
        assert stub_manager.calls == [("get_knowledge_for_decision", {"chat_id": CHAT_ID})]

    def test_decide_passes_the_decision_enum_to_the_manager(self, client, stub_manager):
        response = _call(client, "decide")

        assert response.status_code != 404
        assert response.json()["data"]["message"] == "Knowledge keep_temporary applied"
        name, kwargs = stub_manager.calls[0]
        assert name == "apply_knowledge_decision"
        assert kwargs["chat_id"] == CHAT_ID
        assert kwargs["knowledge_id"] == "k1"
        assert kwargs["decision"].value == "keep_temporary"

    def test_search_returns_the_manager_results(self, client, stub_manager):
        response = _call(client, "search")

        assert response.status_code != 404
        data = response.json()["data"]
        assert data["count"] == 1
        assert data["results"][0]["content"] == "hit-from-manager"
        name, kwargs = stub_manager.calls[0]
        assert name == "search_chat_knowledge"
        assert kwargs == {"query": "redis", "chat_id": CHAT_ID, "include_temporary": True}

    def test_context_reads_contexts_and_files_from_the_manager(self, client):
        response = _call(client, "context")

        assert response.status_code != 404
        data = response.json()["data"]
        assert data["chat_id"] == CHAT_ID
        assert data["topic"] == "wiring"
        assert data["file_count"] == 1
        assert data["files"][0]["file_id"] == "file-from-manager"


class TestLazyResolutionWiring:
    """The manager must be created on demand and cached where the probe reads it."""

    def test_cold_app_state_resolves_and_caches_the_manager(self, monkeypatch, tmp_path):
        created: list[object] = []

        def _factory():
            manager = StubChatKnowledgeManager(str(tmp_path))
            created.append(manager)
            return manager

        monkeypatch.setattr(manager_module, "ChatKnowledgeManager", _factory)
        app = _make_app()
        with TestClient(app) as test_client:
            first = _call(test_client, "search")
            second = _call(test_client, "search")

            assert first.status_code != 404
            assert first.status_code == 200, first.text
            assert second.status_code == 200, second.text
            # Constructed once, then served from app.state — where the probe looks.
            assert len(created) == 1
            assert getattr(app.state, MANAGER_STATE_KEY) is created[0]
            assert len(created[0].calls) == 2

    @pytest.mark.parametrize("module", [manager_module, routes_module])
    def test_module_has_no_resurrected_dead_global(self, module):
        """Neither the manager module nor the HTTP surface may hold the decoy."""
        assert not hasattr(module, "chat_knowledge_manager"), (
            f"{module.__name__} has a module-level chat_knowledge_manager global again — "
            "it is a decoy nothing assigns, which is exactly defect #15160"
        )


class TestUnresolvableManagerIsHonest:
    """AC: a handler must surface the dependency failure, not an opaque 500."""

    @pytest.fixture
    def broken_client(self, monkeypatch):
        def _explode():
            raise RuntimeError("ChromaDB unreachable")

        monkeypatch.setattr(manager_module, "ChatKnowledgeManager", _explode)
        app = _make_app()
        with TestClient(app) as test_client:
            yield test_client

    @pytest.mark.parametrize("route", ALL_ROUTES)
    def test_route_returns_503_not_500(self, broken_client, route):
        response = _call(broken_client, route)

        assert response.status_code != 404, f"{route} was not routed"
        assert response.status_code != 500, f"{route} degraded into an opaque 500: {response.text}"
        assert response.status_code == 503, response.text
        assert "unavailable" in response.text.lower()

    def test_failure_is_recorded_on_app_state_for_the_probe(self, monkeypatch):
        def _explode():
            raise RuntimeError("ChromaDB unreachable")

        monkeypatch.setattr(manager_module, "ChatKnowledgeManager", _explode)
        app = _make_app()
        with TestClient(app) as test_client:
            response = _call(test_client, "search")

        assert response.status_code == 503
        recorded = getattr(app.state, MANAGER_ERROR_STATE_KEY, None)
        assert recorded is not None and "ChromaDB unreachable" in recorded


class TestHarnessCanProduceAFailure:
    """Control: prove "no 500 observed" is a real result, not a blind harness."""

    def test_a_raising_manager_still_produces_a_500(self, stub_manager):
        async def _boom(**_kwargs):
            raise RuntimeError("manager blew up mid-call")

        stub_manager.search_chat_knowledge = _boom
        app = _make_app()
        setattr(app.state, MANAGER_STATE_KEY, stub_manager)
        with TestClient(app, raise_server_exceptions=False) as test_client:
            response = _call(test_client, "search")

        assert response.status_code != 404
        assert response.status_code == 500, (
            "the harness never observed a 500 — every other assertion in this file that "
            "a route does NOT 500 would then be vacuous"
        )

    def test_an_unrouted_path_is_a_404(self, client):
        """Control: prove the != 404 assertions can actually fail."""
        response = client.post(f"{API_PREFIX}/search-typo", json={"query": "x"})

        assert response.status_code == 404


class TestHealthProbeReportsTheRealState:
    """The probe must not be structurally incapable of leaving ``idle``."""

    class _FakeRequest:
        def __init__(self, app):
            self.app = app

    def test_warm_manager_is_ok(self, stub_manager):
        app = _make_app()
        setattr(app.state, MANAGER_STATE_KEY, stub_manager)

        result = asyncio.run(probe_chat_knowledge(self._FakeRequest(app)))

        assert result.status == "ok"
        assert result.data["storage_dir_configured"] is True

    def test_untouched_manager_is_idle(self):
        app = _make_app()

        result = asyncio.run(probe_chat_knowledge(self._FakeRequest(app)))

        assert result.status == "idle"

    def test_failed_resolution_is_down_not_idle(self):
        app = _make_app()
        setattr(app.state, MANAGER_ERROR_STATE_KEY, "RuntimeError: ChromaDB unreachable")

        result = asyncio.run(probe_chat_knowledge(self._FakeRequest(app)))

        assert result.status == "down", "an unavailable dependency must never read as idle"
        assert "ChromaDB unreachable" in result.detail

    def test_unobservable_state_is_degraded_not_idle(self):
        result = asyncio.run(probe_chat_knowledge(request=None))

        assert result.status == "degraded"
        assert "unobservable" in result.detail

    def test_route_traffic_flips_the_probe_off_idle(self, stub_manager, monkeypatch):
        """End to end: before the fix this transition was impossible."""
        monkeypatch.setattr(manager_module, "ChatKnowledgeManager", lambda: stub_manager)
        app = _make_app()

        assert asyncio.run(probe_chat_knowledge(self._FakeRequest(app))).status == "idle"

        with TestClient(app) as test_client:
            assert _call(test_client, "search").status_code == 200

        assert asyncio.run(probe_chat_knowledge(self._FakeRequest(app))).status == "ok"


class TestTheRouterIsGated:
    """#16375: every route requires an authenticated caller.

    `config_router_auth_coverage_test` already proves the gate is DECLARED --
    it reads the AST and checks `KNOWN_UNGATED`. This class proves the gate
    REFUSES, which is a different claim: a static scan sees a
    `dependencies=[Depends(...)]` and cannot see whether the dependency
    actually rejects anyone. Both matter, and a declared gate that admits
    everyone is the shape this repository keeps finding.
    """

    def test_a_request_whose_user_does_not_resolve_is_refused(self, stub_manager, monkeypatch):
        """No resolvable user -> the gated route refuses.

        The middleware is NOT left ambient. `get_auth_middleware` is a
        `lazy_singleton`, so it is process-global and other tests in this suite
        stub it (`chat_shared_links_tracking_16861_test.py:37` returns a
        canned user). Relying on whatever state the process happens to hold
        makes this order-dependent: the first version of this test read a
        real middleware whose dev-header and JWT paths were already primed by
        an earlier test, and got 200 from a correctly gated route.

        So the resolution is pinned to "nobody", which is the only input under
        which "the route refuses" is a claim about THIS router's wiring rather
        than about the middleware's own logic -- which has its own tests.
        """

        class _NoUser:
            def get_user_from_request(self, request):
                return None

        monkeypatch.setattr("api.user_management.dependencies.get_auth_middleware", lambda: _NoUser())
        app = _make_app(authenticated=False)
        setattr(app.state, MANAGER_STATE_KEY, stub_manager)
        with TestClient(app, raise_server_exceptions=False) as unauth:
            response = unauth.get(f"{API_PREFIX}/knowledge/pending/{CHAT_ID}")

        assert response.status_code in (401, 403), (
            f"a caller with no resolvable user got {response.status_code} from a "
            f"gated route -- before #16375 there was no gate at all and every "
            f"route here answered without a credential"
        )

    def test_an_authenticated_request_still_reaches_the_handler(self, client):
        """The contrast case. Without it, 'the gate refuses' is satisfied by a
        gate that refuses everyone, which would be a broken module rather than a
        secured one."""
        response = client.get(f"{API_PREFIX}/knowledge/pending/{CHAT_ID}")

        assert response.status_code == 200, (
            f"an authenticated caller got {response.status_code}; the gate is "
            f"rejecting the traffic it is meant to admit"
        )

    def test_the_gate_is_on_the_router_so_a_new_route_inherits_it(self):
        """Per-route gating is one forgotten decorator away from a hole. This
        pins the gate to the router object, which a route added later cannot
        opt out of by omission."""
        from api.chat_knowledge import router as chat_knowledge_router

        declared = [getattr(d, "dependency", None) for d in (chat_knowledge_router.dependencies or [])]
        assert get_current_user in declared, (
            "the router-level `get_current_user` dependency is gone; a route added " "later would be ungated by default"
        )
