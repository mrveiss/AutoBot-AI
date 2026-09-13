# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
Advanced RAG API endpoint tests, split out of rag_integration_test.py (#15256).

The five ``TestAPIEndpoints`` methods there previously had bodies of nothing but
a comment and, in one case, ``assert client is not None`` -- every statement
executed nothing while the function name asserted a behaviour (#15256). These
replacements hit the real ``api.knowledge_rag`` router, mounted at its
production prefix, through ``fastapi.testclient.TestClient`` with
``dependency_overrides`` standing in for auth and the heavy
KnowledgeBase/RAGService construction -- the same pattern
``tests/api/test_onboarding_auth_regression.py`` uses.
"""

from unittest.mock import AsyncMock, Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from advanced_rag_optimizer import RAGMetrics, SearchResult
from api.knowledge_rag import get_rag_service_dependency
from api.knowledge_rag import router as rag_router
from auth_middleware import get_current_user
from services.rag_config import get_rag_config, reset_rag_config


def _build_rag_test_app(rag_service) -> FastAPI:
    """Minimal FastAPI app wrapping the real knowledge_rag router.

    Mounted at ``/knowledge_base/rag``, its production prefix (see
    ``initialization/router_registry/feature_routers.py``), so these tests
    exercise the actual route table rather than a re-implementation of it.
    Auth is overridden to a stub authenticated user; ``get_rag_service_dependency``
    is overridden to the caller's mock so building a real KnowledgeBase/RAGService
    (Chroma, embeddings, LLM) never runs.
    """
    app = FastAPI()
    app.include_router(rag_router, prefix="/knowledge_base/rag")
    app.dependency_overrides[get_current_user] = lambda: {"username": "test-user"}
    app.dependency_overrides[get_rag_service_dependency] = lambda: rag_service
    return app


def _sample_result(content: str) -> SearchResult:
    return SearchResult(
        content=content,
        metadata={"source": "kb"},
        semantic_score=0.9,
        keyword_score=0.6,
        hybrid_score=0.85,
        relevance_rank=1,
        source_path="facts.md",
    )


class TestAPIEndpoints:
    """Tests for advanced RAG API endpoints, exercised through TestClient (#15256)."""

    def setup_method(self):
        """Isolate the module-level RAG config singleton, mirroring rag_integration_test.py."""
        reset_rag_config()

    def teardown_method(self):
        reset_rag_config()

    def test_search_with_reranking_parameter(self) -> None:
        """POST /advanced_search must thread enable_reranking through to RAGService."""
        rag_service = Mock()
        rag_service.advanced_search = AsyncMock(return_value=([_sample_result("doc")], RAGMetrics()))
        app = _build_rag_test_app(rag_service)

        response = TestClient(app).post(
            "/knowledge_base/rag/advanced_search",
            json={"query": "latency", "enable_reranking": False},
        )

        assert response.status_code == 200
        assert response.json()["reranking_enabled"] is False
        rag_service.advanced_search.assert_awaited_once()
        assert rag_service.advanced_search.await_args.kwargs["enable_reranking"] is False

    def test_advanced_search_endpoint(self) -> None:
        """POST /knowledge_base/rag/advanced_search returns real search results (#4070)."""
        rag_service = Mock()
        result = _sample_result("Latency increased by 15%")
        rag_service.advanced_search = AsyncMock(return_value=([result], RAGMetrics(total_time=0.02)))
        app = _build_rag_test_app(rag_service)

        response = TestClient(app).post("/knowledge_base/rag/advanced_search", json={"query": "latency"})

        assert response.status_code == 200
        body = response.json()
        assert body["total_results"] == 1
        assert body["results"][0]["content"] == "Latency increased by 15%"
        assert body["metrics"]["total_time"] == 0.02

    def test_rerank_results_endpoint(self) -> None:
        """POST /knowledge_base/rag/rerank_results reranks the supplied results via RAGService."""
        rag_service = Mock()
        rag_service.rerank_results = AsyncMock(return_value=[{"content": "b"}, {"content": "a"}])
        app = _build_rag_test_app(rag_service)

        response = TestClient(app).post(
            "/knowledge_base/rag/rerank_results",
            json={"query": "q", "results": [{"content": "a"}, {"content": "b"}]},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["original_count"] == 2
        assert body["reranking_applied"] is True
        assert body["reranked_results"] == [{"content": "b"}, {"content": "a"}]
        rag_service.rerank_results.assert_awaited_once()

    def test_config_get_endpoint(self) -> None:
        """GET /knowledge_base/rag/config/rag returns the real RAGConfig defaults."""
        app = _build_rag_test_app(Mock())
        response = TestClient(app).get("/knowledge_base/rag/config/rag")

        assert response.status_code == 200
        body = response.json()
        assert body["config"]["enable_reranking"] is True
        assert body["source"] == "config/complete.yaml"

    def test_config_update_endpoint(self) -> None:
        """PUT /knowledge_base/rag/config/rag persists a change through update_rag_config()."""
        app = _build_rag_test_app(Mock())
        response = TestClient(app).put(
            "/knowledge_base/rag/config/rag",
            json={"enable_reranking": False},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["config"]["enable_reranking"] is False
        assert "enable_reranking" in body["updated_fields"]
        assert get_rag_config().enable_reranking is False


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
