# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Integration tests for POST /research (#12622).

Builds a standalone FastAPI app mounting only ``services.research.routes``,
overriding auth so these tests exercise the route wiring and error handling
without a live auth backend. This is the same "app.include_router" shape
production uses (see initialization/router_registry/feature_routers.py),
so a passing test here demonstrates the route is genuinely reachable.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from services.research.models import Citation, ResearchFactOut, ResearchResponse


def _build_app(orchestrator: AsyncMock) -> TestClient:
    """Build a FastAPI app with only the research router, auth overridden."""
    from auth_middleware import get_current_user
    from services.research.routes import router

    app = FastAPI()
    app.include_router(router, prefix="/research")
    app.dependency_overrides[get_current_user] = lambda: {"username": "test-user", "role": "user"}
    app.state.research_orchestrator = orchestrator
    return TestClient(app)


def _make_orchestrator(response: ResearchResponse) -> AsyncMock:
    orchestrator = AsyncMock()
    orchestrator.research = AsyncMock(return_value=response)
    return orchestrator


class TestPostResearch:
    """POST /research request/response contract."""

    def test_returns_full_contract_shape(self):
        """A successful run returns the full #12622 response contract."""
        response = ResearchResponse(
            answer="X is Y [F1].",
            citations=[Citation(fact_id="fact-1", source_url="https://a.example", source_doc_id="doc-1")],
            facts=[
                ResearchFactOut(fact_id="fact-1", content="X is Y.", source_url="https://a.example", confidence=0.8)
            ],
            contradictions=[],
            confidence=0.7,
            sources_fetched=1,
            facts_stored=1,
        )
        client = _build_app(_make_orchestrator(response))

        resp = client.post("/research", json={"question": "what is X?"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["answer"] == "X is Y [F1]."
        assert body["citations"][0]["fact_id"] == "fact-1"
        assert body["facts"][0]["fact_id"] == "fact-1"
        assert body["contradictions"] == []
        assert body["confidence"] == 0.7

    def test_question_too_short_is_rejected(self):
        """A sub-minimum-length question is rejected with 422 before the orchestrator runs."""
        orchestrator = _make_orchestrator(ResearchResponse(answer=""))
        client = _build_app(orchestrator)

        resp = client.post("/research", json={"question": "hi"})

        assert resp.status_code == 422
        orchestrator.research.assert_not_awaited()

    def test_missing_question_is_rejected(self):
        """A request with no 'question' field is rejected with 422."""
        client = _build_app(_make_orchestrator(ResearchResponse(answer="")))

        resp = client.post("/research", json={})

        assert resp.status_code == 422

    def test_orchestrator_exception_returns_500_not_stack_trace(self):
        """An unexpected orchestrator failure returns a clean 500, not a raw traceback."""
        orchestrator = AsyncMock()
        orchestrator.research = AsyncMock(side_effect=RuntimeError("boom"))
        client = _build_app(orchestrator)

        resp = client.post("/research", json={"question": "what is X?"})

        assert resp.status_code == 500
        assert "boom" not in resp.json()["detail"]

    def test_route_requires_auth_dependency(self):
        """The route is wired behind ``Depends(get_current_user)`` (not open).

        Asserts only that our route does not bypass the dependency: a rejected
        caller must not reach the orchestrator and must not succeed with 200.

        #13253: this installs an explicit denying override rather than relying
        on the conftest auth stub's behaviour. It previously passed because the
        stub was a bare ``MagicMock`` whose ``(*args, **kwargs)`` signature made
        FastAPI demand two required query params, so every call 422'd before
        reaching the handler — the assertion held for a reason that had nothing
        to do with authentication. With the stub corrected to a real callable
        the route authenticates and returns 200, so the guarantee has to be
        pinned to a real rejection instead.
        """
        from auth_middleware import get_current_user
        from services.research.routes import router

        def _deny() -> dict:
            raise HTTPException(status_code=401, detail="Authentication required")

        app = FastAPI()
        app.include_router(router, prefix="/research")
        orchestrator = _make_orchestrator(ResearchResponse(answer=""))
        app.state.research_orchestrator = orchestrator
        app.dependency_overrides[get_current_user] = _deny
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.post("/research", json={"question": "what is X?"})

        assert resp.status_code == 401
        orchestrator.research.assert_not_awaited()
