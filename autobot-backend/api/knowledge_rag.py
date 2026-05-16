#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Advanced RAG endpoints for knowledge base - Reranking and optimized search.

These endpoints provide enhanced search capabilities using the AdvancedRAGOptimizer
with cross-encoder reranking for improved relevance scoring.

Issue #4681: Added GET /entity/{id}/history for evolutionary lineage tracking.
"""

from fastapi import APIRouter, Depends, HTTPException, Request

from auth_middleware import check_admin_permission, get_current_user
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from knowledge.schemas.rag import (
    AdvancedSearchRequest,
    AdvancedSearchResponse,
    BenchmarkRunResponse,
    EntityHistoryResponse,
    LoopApproveResponse,
    LoopRejectResponse,
    LoopStatusResponse,
    RagConfigResponse,
    RAGConfigUpdate,
    RagStatsResponse,
    RerankRequest,
    RerankResultsResponse,
    RunBenchmarkRequest,
    UpdateRagConfigResponse,
)
from knowledge_factory import get_or_create_knowledge_base
from services.rag_config import get_rag_config, update_rag_config
from services.rag_service import RAGService

logger = get_logger(__name__)

router = APIRouter()


# ===== DEPENDENCY INJECTION =====


async def get_rag_service_dependency(request: Request) -> RAGService:
    """
    Dependency function to get RAGService instance.

    Args:
        request: FastAPI request object

    Returns:
        RAGService instance initialized with knowledge base
    """
    kb = await get_or_create_knowledge_base(request.app, force_refresh=False)

    if kb is None:
        raise HTTPException(status_code=503, detail="Knowledge base not available")

    # Create RAG service (it will initialize itself)
    rag_service = RAGService(kb)
    await rag_service.initialize()

    return rag_service


# ===== ENDPOINTS =====


def _convert_results_to_dicts(results: list) -> list:
    """
    Convert SearchResult objects to dictionaries.

    Issue #620: Extracted from advanced_search.

    Args:
        results: List of SearchResult objects

    Returns:
        List of result dictionaries
    """
    return [
        {
            "content": r.content,
            "metadata": r.metadata,
            "source_path": r.source_path,
            "semantic_score": r.semantic_score,
            "keyword_score": r.keyword_score,
            "hybrid_score": r.hybrid_score,
            "rerank_score": r.rerank_score,
            "relevance_rank": r.relevance_rank,
        }
        for r in results
    ]


def _build_search_metrics(metrics) -> dict:
    """
    Build metrics dictionary from search metrics object.

    Issue #620: Extracted from advanced_search.

    Args:
        metrics: Search metrics object

    Returns:
        Metrics dictionary
    """
    return {
        "query_processing_time": metrics.query_processing_time,
        "retrieval_time": metrics.retrieval_time,
        "reranking_time": metrics.reranking_time,
        "total_time": metrics.total_time,
        "documents_considered": metrics.documents_considered,
        "final_results_count": metrics.final_results_count,
        "hybrid_search_enabled": metrics.hybrid_search_enabled,
    }


@router.post("/advanced_search", response_model=AdvancedSearchResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="advanced_search",
    error_code_prefix="KNOWLEDGE_RAG",
)
async def advanced_search(
    request: AdvancedSearchRequest,
    rag_service: RAGService = Depends(get_rag_service_dependency),
    current_user: dict = Depends(get_current_user),
):
    """
    Perform advanced RAG search with cross-encoder reranking.

    Issue #620: Refactored to use extracted helper methods.
    Issue #744: Requires authenticated user.

    **Parameters:**
    - **query**: Search query string
    - **max_results**: Number of results to return (1-50)
    - **enable_reranking**: Whether to apply cross-encoder reranking
    - **return_context**: Return optimized context for RAG generation
    - **timeout**: Optional timeout in seconds

    **Returns:**
    - **results**: List of search results with rerank scores
    - **metrics**: Performance metrics (timing, result counts)
    - **context**: Optimized context (if return_context=true)
    """
    logger.info(
        "Advanced search: '%s' (max_results=%d, reranking=%s)",
        request.query,
        request.max_results,
        request.enable_reranking,
    )

    # Perform advanced search
    results, metrics = await rag_service.advanced_search(
        query=request.query,
        max_results=request.max_results,
        enable_reranking=request.enable_reranking,
        timeout=request.timeout,
    )

    # Build response (Issue #620: uses helpers)
    results_dicts = _convert_results_to_dicts(results)
    response = {
        "results": results_dicts,
        "total_results": len(results_dicts),
        "query": request.query,
        "metrics": _build_search_metrics(metrics),
        "reranking_enabled": request.enable_reranking,
    }

    # Optionally include optimized context
    if request.return_context:
        context, _ = await rag_service.get_optimized_context(query=request.query)
        response["context"] = context
        response["context_length"] = len(context)

    return response


@router.post("/rerank_results", response_model=RerankResultsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="rerank_results",
    error_code_prefix="KNOWLEDGE_RAG",
)
async def rerank_results(
    request: RerankRequest,
    rag_service: RAGService = Depends(get_rag_service_dependency),
    current_user: dict = Depends(get_current_user),
):
    """
    Rerank existing search results using cross-encoder model.

    This endpoint allows you to post-process results from basic searches
    with advanced cross-encoder reranking for improved relevance.

    Issue #744: Requires authenticated user.

    **Parameters:**
    - **query**: Original search query
    - **results**: List of search results to rerank

    **Returns:**
    - **reranked_results**: Results sorted by rerank score
    - **original_count**: Number of input results
    """
    logger.info(f"Reranking {len(request.results)} results for query: '{request.query}'")

    # Perform reranking
    reranked_results = await rag_service.rerank_results(
        query=request.query,
        results=request.results,
    )

    return {
        "reranked_results": reranked_results,
        "original_count": len(request.results),
        "query": request.query,
        "reranking_applied": True,
    }


@router.get("/config/rag", response_model=RagConfigResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_rag_configuration",
    error_code_prefix="KNOWLEDGE_RAG",
)
async def get_rag_configuration(
    current_user: dict = Depends(get_current_user),
):
    """
    Get current RAG configuration settings.

    Returns all configurable parameters for the advanced RAG system including:
    - Hybrid search weights
    - Reranking settings
    - Performance parameters

    Issue #744: Requires authenticated user.
    """
    config = get_rag_config()

    return {
        "config": config.to_dict(),
        "source": "config/complete.yaml",
    }


@router.put("/config/rag", response_model=UpdateRagConfigResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_rag_configuration",
    error_code_prefix="KNOWLEDGE_RAG",
)
async def update_rag_configuration(
    request: RAGConfigUpdate,
    current_user: dict = Depends(get_current_user),
):
    """
    Update RAG configuration at runtime.

    Allows dynamic adjustment of RAG parameters without restarting the service.
    Only provided parameters will be updated; others remain unchanged.

    Issue #744: Requires authenticated user.

    **Parameters:**
    - **hybrid_weight_semantic**: Weight for semantic search (0-1)
    - **hybrid_weight_keyword**: Weight for keyword search (0-1)
    - **enable_reranking**: Enable/disable cross-encoder reranking
    - **diversity_threshold**: Similarity threshold for diversification (0-1)
    - **max_results_per_stage**: Max results per retrieval stage
    """
    # Filter out None values
    updates = {k: v for k, v in request.dict().items() if v is not None}

    if not updates:
        return {
            "message": "No configuration changes provided",
            "config": get_rag_config().to_dict(),
        }

    logger.info("Updating RAG configuration: %s", list(updates.keys()))

    # Update configuration
    new_config = update_rag_config(updates)

    return {
        "message": "RAG configuration updated successfully",
        "updated_fields": list(updates.keys()),
        "config": new_config.to_dict(),
    }


@router.get("/loop/status", response_model=LoopStatusResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_loop_status",
    error_code_prefix="KNOWLEDGE_RAG",
)
async def get_loop_status(
    current_user: dict = Depends(get_current_user),
):
    """Get autonomous improvement loop status.

    Returns last run time, variants tested, winner, current baseline config,
    and any variant pending human approval.

    Issue #4680.
    """
    from services.rag_config import get_rag_config

    cfg = get_rag_config()

    # Import lazily to avoid hard startup dependency
    try:
        from services.knowledge.autonomous_loop import get_loop_runner as get_loop_orchestrator

        orchestrator = await get_loop_orchestrator(None, dry_run=cfg.autonomous_loop_dry_run)
        status = orchestrator.get_status()
    except Exception as exc:
        logger.warning("Loop status unavailable: %s", exc)
        from services.knowledge.autonomous_loop import LoopStatus

        status = LoopStatus(
            enabled=cfg.autonomous_loop_enabled,
            dry_run=cfg.autonomous_loop_dry_run,
            last_run=None,
        )

    return {
        "loop_status": status.to_dict(),
        "current_config": cfg.to_dict(),
    }


@router.post("/loop/approve", response_model=LoopApproveResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="approve_loop_variant",
    error_code_prefix="KNOWLEDGE_RAG",
)
async def approve_loop_variant(
    current_user: dict = Depends(get_current_user),
):
    """Promote the pending staging variant to production RAGConfig.

    The autonomous loop stores a "pending approval" variant when the improvement
    margin is below the auto-promotion threshold.  This endpoint applies it.

    Returns 409 if no variant is pending.

    Issue #4680.
    """
    from services.knowledge.autonomous_loop import get_loop_runner as get_loop_orchestrator
    from services.rag_config import get_rag_config

    cfg = get_rag_config()
    orchestrator = await get_loop_orchestrator(None, dry_run=cfg.autonomous_loop_dry_run)
    applied = await orchestrator.approve_pending()

    if not applied:
        raise HTTPException(status_code=409, detail="No variant pending approval")

    return {
        "message": "Pending variant promoted to production config",
        "config": get_rag_config().to_dict(),
    }


@router.post("/loop/reject", response_model=LoopRejectResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="reject_loop_variant",
    error_code_prefix="KNOWLEDGE_RAG",
)
async def reject_loop_variant(
    current_user: dict = Depends(get_current_user),
):
    """Discard the pending staging variant without applying it to production RAGConfig.

    The autonomous loop stores a "pending approval" variant when the improvement
    margin is below the auto-promotion threshold.  This endpoint clears it.

    Returns 409 if no variant is pending.

    Issue #4916.
    """
    from services.knowledge.autonomous_loop import get_loop_runner as get_loop_orchestrator
    from services.rag_config import get_rag_config

    cfg = get_rag_config()
    orchestrator = await get_loop_orchestrator(None, dry_run=cfg.autonomous_loop_dry_run)
    cleared = await orchestrator.reject_pending()

    if not cleared:
        raise HTTPException(status_code=409, detail="No variant pending approval")

    return {"message": "Pending variant rejected and cleared"}


@router.get("/stats/rag", response_model=RagStatsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_rag_stats",
    error_code_prefix="KNOWLEDGE_RAG",
)
async def get_rag_stats(
    rag_service: RAGService = Depends(get_rag_service_dependency),
    current_user: dict = Depends(get_current_user),
):
    """
    Get RAG service statistics and status.

    Returns information about:
    - Service initialization status
    - Knowledge base implementation
    - Cache statistics
    - Current configuration

    Issue #744: Requires authenticated user.
    """
    stats = rag_service.get_stats()

    return {
        "stats": stats,
        "service_available": True,
    }


@router.post("/benchmark/run", response_model=BenchmarkRunResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="run_rag_benchmark",
    error_code_prefix="KNOWLEDGE_RAG",
)
async def run_rag_benchmark(
    request: RunBenchmarkRequest,
    admin_check: bool = Depends(check_admin_permission),
):
    """Run the RAG precision@k benchmark suite and publish results to RetrievalLearner.

    Issue #4676: Executes ``run_benchmark_suite()`` against an ephemeral
    ChromaDB collection, then calls ``publish_feedback_events()`` to inject
    the results as synthetic ``rag:feedback:__global__:{date}`` stream entries.
    RetrievalLearner will pick up these events on its next scheduled consume
    run and update global retrieval patterns accordingly.

    Issue #5018: Admin-gated to prevent unauthenticated users from poisoning
    the ``__global__`` RetrievalLearner feedback stream.

    Issue #5074: Requires an explicit ``split`` body param (``dev`` | ``test``
    | ``all``).  Only ``split=test`` produces a ``held_out_score=true`` result.

    **Body:**
    - **split**: ``dev`` (tune) | ``test`` (held-out) | ``all`` (combined).
    - **k**: top-k retrieval size (default 5).

    **Returns:**
    - **published**: Number of feedback events written to Redis.
    - **total**: Total benchmark queries run.
    - **stream_key**: Redis stream key where events were written.
    - **split_used**: The split that was actually run.
    - **dev_size**: Total dev-set queries in the dataset.
    - **test_size**: Total test-set queries in the dataset.
    - **tuned_on_dev**: Whether the harness has ever run a tune() pass.
    - **held_out_score**: True iff split==test AND no dev leakage occurred.
    - **mean_precision_at_k**: Mean precision@k across the run.
    """
    import asyncio
    from datetime import datetime, timezone

    import chromadb

    from autobot_shared.redis_client import get_async_redis_client
    from knowledge.rag_benchmarks import (
        _BENCHMARK_USER,
        _TOPIC_DOCS,
        BenchmarkHarness,
        BenchmarkSplit,
        _deterministic_embed,
        get_default_dataset,
        publish_feedback_events,
        run_benchmark_suite,
    )

    # Build an ephemeral ChromaDB collection seeded with the domain corpus.
    _DIM = 128
    client = chromadb.EphemeralClient()
    collection = client.create_collection(
        name="benchmark_run",
        metadata={"hnsw:space": "cosine"},
    )
    collection.add(
        ids=[doc_id for doc_id, _, _ in _TOPIC_DOCS],
        embeddings=[_deterministic_embed(text, _DIM) for _, text, _ in _TOPIC_DOCS],
        documents=[text for _, text, _ in _TOPIC_DOCS],
        metadatas=[{"topic": topic} for _, _, topic in _TOPIC_DOCS],
    )

    split = BenchmarkSplit(request.split)
    dataset = get_default_dataset()
    harness = BenchmarkHarness(dataset=dataset)

    def _runner(ds):
        return run_benchmark_suite(collection, k=request.k, dataset=ds, split=split)

    loop = asyncio.get_running_loop()
    report = await loop.run_in_executor(None, harness.run, _runner, split)

    try:
        client.delete_collection("benchmark_run")
    except Exception as exc:
        logger.warning("benchmark cleanup failed: %s", exc)

    redis = await get_async_redis_client(database="analytics")
    if redis is None:
        logger.warning("run_rag_benchmark: Redis unavailable; benchmark events dropped")
        # Issue #5319 / #5407: emit ops-visible counter alongside the
        # warning.  reason="redis_down" - analytics Redis unreachable.
        from knowledge.metrics import autobot_kb_degradation_total

        autobot_kb_degradation_total.labels(endpoint="rag_benchmark", reason="redis_down").inc()
        return {
            "published": 0,
            "total": len(report.results),
            "stream_key": None,
            "reason": "redis_unavailable",
            "split_used": report.split_used,
            "dev_size": report.dev_size,
            "test_size": report.test_size,
            "tuned_on_dev": report.tuned_on_dev,
            "held_out_score": report.held_out_score,
            "mean_precision_at_k": report.mean_precision_at_k,
        }

    date_key = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    stream_key = f"rag:feedback:{_BENCHMARK_USER}:{date_key}"

    published = await publish_feedback_events(redis, report.results)
    logger.info(
        "run_rag_benchmark: split=%s published %d/%d feedback events " "(held_out_score=%s)",
        report.split_used,
        published,
        len(report.results),
        report.held_out_score,
    )
    return {
        "published": published,
        "total": len(report.results),
        "stream_key": stream_key,
        "split_used": report.split_used,
        "dev_size": report.dev_size,
        "test_size": report.test_size,
        "tuned_on_dev": report.tuned_on_dev,
        "held_out_score": report.held_out_score,
        "mean_precision_at_k": report.mean_precision_at_k,
    }


@router.get("/entity/{entity_id}/history", response_model=EntityHistoryResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_entity_history",
    error_code_prefix="KNOWLEDGE_RAG",
)
async def get_entity_history(
    entity_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Return the version list for a ChromaDB entity (evolutionary lineage).

    Each entry includes lineage_version, lineage_source_run_id, score, and
    timestamp so callers can trace every change back to its synthesis run.

    Issue #4681: Evolutionary lineage tracking.

    **Parameters:**
    - **entity_id**: ChromaDB document ID of the entity.

    **Returns:**
    - **entity_id**: The requested entity ID.
    - **versions**: List of version dicts sorted by lineage_version ascending.
    - **count**: Number of versions found.
    """
    from knowledge.backends import get_async_default_client
    from services.knowledge.lineage_service import LineageService
    from services.knowledge.synthesis_provenance import SynthesisProvenanceLog

    async def _collection_factory(name: str):
        client = await get_async_default_client()
        return await client.get_or_create_collection(name=name)

    svc = LineageService(
        provenance_log=SynthesisProvenanceLog(),
        chromadb_collection_factory=_collection_factory,
    )
    versions = await svc.get_entity_history(entity_id)
    return {
        "entity_id": entity_id,
        "versions": versions,
        "count": len(versions),
    }
