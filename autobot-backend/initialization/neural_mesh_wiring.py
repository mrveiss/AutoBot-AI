# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Neural Mesh RAG wiring for the Graph-RAG startup step (#4765, #16250).

Moved out of ``initialization/lifespan.py``'s ``_init_graph_rag_service`` so no
function is over the length limit. Every mesh dependency is still imported
inside the function that uses it, so a missing one only skips the wiring, as
before.
"""

from collections.abc import Callable
from typing import Any

from fastapi import FastAPI

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


def build_mesh_components() -> dict[str, Any]:
    """Construct the shared mesh components each RAGService builds its retriever from."""
    from autobot_shared.redis_client import get_async_redis_client
    from knowledge.search_components.query_classifier import QueryClassifier
    from knowledge.search_components.reranking import ResultReranker
    from services.mesh_brain.edge_learner import EdgeLearner
    from services.mesh_brain.mesh_db_adapter import create_mesh_db_adapter
    from services.mesh_brain.ppr import PersonalizedPageRank
    from user_management.database import get_async_engine

    _mesh_db = create_mesh_db_adapter(get_async_engine())
    _redis = get_async_redis_client()
    _ppr = PersonalizedPageRank(db=_mesh_db)
    _edge_learner = EdgeLearner(db=_mesh_db, redis=_redis)

    return {
        "mesh_db": _mesh_db,
        "ppr": _ppr,
        "edge_learner": _edge_learner,
        "reranker": ResultReranker(),
        "classifier": QueryClassifier(),
        "llm": None,
    }


def requeue_existing_rag_services(app: FastAPI) -> None:
    """Make already-created RAGService instances build per-instance retrievers (#4765)."""
    # Trigger re-initialization for already-created RAGService instances so they
    # also build per-instance retrievers (covers chat_workflow_manager and the
    # get_rag_service() singleton that were created before this point).
    import services.rag_service as _rag_mod

    for _existing in [
        _rag_mod._rag_service_instance,
        getattr(
            getattr(
                getattr(app.state, "chat_workflow_manager", None),
                "knowledge_service",
                None,
            ),
            "rag_service",
            None,
        ),
    ]:
        if _existing is not None and _existing._mesh_retriever is None:
            _existing._initialized = False  # force re-init on next call
            logger.info("Queued per-instance NeuralMeshRetriever build for existing RAGService (#4765)")


def wire_neural_mesh_components(
    app: FastAPI, register_shared_mesh_components: Callable[[dict[str, Any]], None]
) -> None:
    """Register the mesh components on app.state and requeue existing RAG services; never raises."""
    try:
        _mesh_components = build_mesh_components()

        # Store on app.state for introspection / health checks.
        app.state.mesh_components = _mesh_components

        # Expose mesh_db on app.state so _start_community_clustering_loop can use it (#4834).
        app.state.mesh_db = _mesh_components["mesh_db"]

        # Register components; each future RAGService.initialize() builds its own
        # retriever from these, binding closures to its own optimizer (#4765).
        register_shared_mesh_components(_mesh_components)

        requeue_existing_rag_services(app)

        logger.info(
            "✅ [ 87%] Neural Mesh RAG: mesh components registered; "
            "per-instance NeuralMeshRetriever will build on next initialize() (#4765)"
        )
    except Exception as _mesh_wire_err:
        logger.warning("Neural Mesh RAG wiring skipped (non-fatal): %s", _mesh_wire_err)
