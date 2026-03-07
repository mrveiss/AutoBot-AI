# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
FastAPI Lifespan Manager

Handles application startup and shutdown with 2-phase initialization:
- Phase 1: Critical services (blocking) - must complete before serving requests
- Phase 2: Background services (non-blocking) - can complete while serving
"""

import asyncio
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

from chat_history import ChatHistoryManager
from chat_workflow import ChatWorkflowManager
from config import ConfigManager
from fastapi import FastAPI
from knowledge_factory import get_or_create_knowledge_base
from security_layer import SecurityLayer
from services.slm_client import init_slm_client, shutdown_slm_client
from type_defs.common import Metadata
from user_management.database import init_database
from utils.background_llm_sync import BackgroundLLMSync
from utils.io_executor import shutdown_executors as shutdown_io_executors

from autobot_shared.tracing import (
    instrument_aiohttp,
    instrument_redis,
    shutdown_tracing,
)

# Bounded thread pool to prevent unbounded thread creation
# Default asyncio executor creates min(32, cpu_count + 4) threads per invocation
# This shared executor limits total threads across all run_in_executor calls
MAX_WORKER_THREADS = 16
_executor: ThreadPoolExecutor | None = None

logger = logging.getLogger(__name__)

# Issue #380: Module-level tuple for backend logger names
_BACKEND_LOGGER_NAMES = ("api", "api.codebase_analytics")

# Lock for thread-safe access to app_state
_app_state_lock = asyncio.Lock()

# Global state shared across app
app_state: Metadata = {
    "knowledge_base": None,
    "chat_workflow_manager": None,
    "chat_history_manager": None,
    "background_llm_sync": None,
    "config": None,
    "initialization_status": "starting",  # starting, phase1, phase2, ready, error
    "initialization_message": "Backend starting...",
}


async def update_app_state(key: str, value) -> None:
    """Thread-safe update of app_state."""
    async with _app_state_lock:
        app_state[key] = value


async def update_app_state_multi(**kwargs) -> None:
    """Thread-safe update of multiple app_state keys."""
    async with _app_state_lock:
        app_state.update(kwargs)


def configure_logging():
    """Configure logging level from environment variable"""
    LOG_LEVEL = os.getenv("AUTOBOT_LOG_LEVEL", "INFO").upper()
    LOG_LEVEL_VALUE = getattr(logging, LOG_LEVEL, logging.INFO)
    logging.root.setLevel(LOG_LEVEL_VALUE)

    # Set level for all backend loggers
    for logger_name in _BACKEND_LOGGER_NAMES:
        logging.getLogger(logger_name).setLevel(LOG_LEVEL_VALUE)

    logger.info("📊 Logging level set to: %s (%s)", LOG_LEVEL, LOG_LEVEL_VALUE)


async def _init_cache_coordinator() -> None:
    """Register caches with CacheCoordinator for memory optimization.

    Helper for initialize_critical_services (Issue #743).
    """
    logger.info("✅ [ 55%] Cache: Registering caches with CacheCoordinator...")
    try:
        from cache import register_all_caches

        cache_count = register_all_caches()
        logger.info(
            "✅ [ 55%] Cache: %d caches registered for coordinated management",
            cache_count,
        )
    except Exception as cache_error:
        logger.warning("Cache registration failed (non-critical): %s", cache_error)


async def _init_skills_tables() -> None:
    """Create skills system tables if they don't exist."""
    from skills.db import get_skills_engine
    from skills.models import SkillsBase

    engine = get_skills_engine()
    async with engine.begin() as conn:
        await conn.run_sync(SkillsBase.metadata.create_all)
    logger.info("Skills tables initialized")


async def _init_skills_discovery() -> None:
    """Discover and register builtin skills at startup."""
    from api.skills import _get_manager

    manager = _get_manager()
    result = await manager.initialize()
    logger.info(
        "Skills discovered: %d registered, categories: %s",
        result.get("total_registered", 0),
        result.get("categories", []),
    )


async def _init_chat_history_manager(app: FastAPI) -> None:
    """Initialize chat history manager (Issue #665: extracted helper).

    Args:
        app: FastAPI application instance

    Raises:
        RuntimeError: If initialization fails
    """
    logger.info("✅ [ 30%] Chat History: Initializing chat history manager...")
    try:
        chat_history_manager = ChatHistoryManager()
        app.state.chat_history_manager = chat_history_manager
        await update_app_state("chat_history_manager", chat_history_manager)
        logger.info("✅ [ 30%] Chat History: Manager initialized successfully")
    except Exception as chat_history_error:
        logger.error(
            f"❌ CRITICAL: Chat history manager initialization failed: {chat_history_error}"
        )
        raise RuntimeError(
            f"Chat history manager initialization failed: {chat_history_error}"
        )


async def _init_conversation_file_manager(app: FastAPI) -> None:
    """Initialize conversation file manager database (Issue #665: extracted helper).

    Args:
        app: FastAPI application instance

    Raises:
        RuntimeError: If initialization fails
    """
    logger.info("✅ [ 40%] Conversation Files DB: Initializing database schema...")
    try:
        from conversation_file_manager import get_conversation_file_manager

        conversation_file_manager = await get_conversation_file_manager()
        await conversation_file_manager.initialize()
        app.state.conversation_file_manager = conversation_file_manager
        await update_app_state("conversation_file_manager", conversation_file_manager)
        logger.info("✅ [ 40%] Conversation Files DB: Database initialized and verified")
    except Exception as conv_file_error:
        logger.error(
            f"❌ CRITICAL: Conversation files database initialization failed: {conv_file_error}"
        )
        logger.error("Backend startup ABORTED - database must be operational")
        raise RuntimeError(f"Database initialization failed: {conv_file_error}")


async def _init_chat_workflow_manager(app: FastAPI) -> None:
    """Initialize chat workflow manager (Issue #665: extracted helper).

    Args:
        app: FastAPI application instance

    Raises:
        RuntimeError: If initialization fails
    """
    logger.info("✅ [ 50%] Chat Workflow: Initializing workflow manager...")
    try:
        chat_workflow_manager = ChatWorkflowManager()
        await chat_workflow_manager.initialize()
        app.state.chat_workflow_manager = chat_workflow_manager
        await update_app_state("chat_workflow_manager", chat_workflow_manager)
        logger.info("✅ [ 50%] Chat Workflow: Manager initialized with async Redis")
    except Exception as chat_error:
        logger.error(
            f"❌ CRITICAL: Chat workflow manager initialization failed: {chat_error}"
        )
        raise RuntimeError(f"Chat workflow manager initialization failed: {chat_error}")


async def _init_config(app: FastAPI) -> None:
    """Helper for initialize_critical_services. Ref: #1088."""
    logger.info("✅ [ 10%] Config: Loading unified configuration...")
    config = ConfigManager()
    app.state.config = config
    await update_app_state("config", config)
    logger.info("✅ [ 10%] Config: Configuration loaded successfully")


async def _init_security_layer(app: FastAPI) -> None:
    """Helper for initialize_critical_services. Ref: #1088."""
    logger.info("✅ [ 15%] Security: Initializing security layer...")
    security_layer = SecurityLayer()
    app.state.security_layer = security_layer
    await update_app_state("security_layer", security_layer)
    logger.info("✅ [ 15%] Security: Security layer initialized successfully")


async def _init_database() -> None:
    """Helper for initialize_critical_services. Ref: #1088.

    Issue #898: Initialize PostgreSQL async engine. Raises RuntimeError on failure.
    """
    logger.info("✅ [ 16%] Database: Initializing PostgreSQL async engine...")
    logger.info("🔍 DEBUG: About to call get_deployment_config()")
    try:
        from user_management.config import get_deployment_config

        config = get_deployment_config()
        logger.info(
            "🔍 DEBUG: Deployment config loaded - mode=%s, postgres_enabled=%s",
            config.mode.value,
            config.postgres_enabled,
        )
        logger.info(
            "🔍 DEBUG: PostgreSQL - host=%s, port=%s, db=%s",
            config.postgres_host,
            config.postgres_port,
            config.postgres_db,
        )
        logger.info("🔍 DEBUG: About to call init_database()")
        await init_database()
        logger.info("✅ [ 16%] Database: PostgreSQL async engine initialized")
    except Exception as db_error:
        logger.error("❌ CRITICAL: Database initialization failed: %s", db_error)
        import traceback

        logger.error("❌ TRACEBACK: %s", traceback.format_exc())
        raise RuntimeError(f"Database initialization failed: {db_error}")


async def _init_telemetry_and_redis() -> None:
    """Helper for initialize_critical_services. Ref: #1088.

    Issue #881: Gateway skipped (testing event loop deadlock).
    Issue #697: Instruments Redis and aiohttp with OpenTelemetry.
    """
    # Issue #732: Initialize Gateway - CRITICAL
    # Issue #881: TEMP DISABLED - testing if Gateway blocks event loop
    logger.info("✅ [ 17%] Gateway: SKIPPED (testing event loop deadlock)")
    # try:
    #     from backend.services.gateway import ChannelType, Gateway, WebSocketAdapter
    #
    #     gateway = Gateway()
    #     await gateway.start()
    #
    #     # Register WebSocket adapter
    #     ws_adapter = WebSocketAdapter()
    #     gateway.register_channel_adapter(ChannelType.WEBSOCKET, ws_adapter)
    #
    #     app.state.gateway = gateway
    #     await update_app_state("gateway", gateway)
    #     logger.info("✅ [ 17%] Gateway: Gateway initialized with WebSocket adapter")
    # except Exception as gateway_error:
    #     logger.error(f"❌ CRITICAL: Gateway initialization failed: {gateway_error}")
    #     raise RuntimeError(f"Gateway initialization failed: {gateway_error}")

    instrument_redis()
    instrument_aiohttp()
    logger.info(
        "✅ [ 20%] Redis: Using centralized Redis client management (src.utils.redis_client)"
    )


async def _init_skills(app: FastAPI) -> None:
    """Helper for initialize_critical_services. Ref: #1088.

    Initializes skills system tables and discovers builtin skills (non-critical).
    """
    try:
        await _init_skills_tables()
        await _init_skills_discovery()
    except Exception as skills_db_error:
        logger.warning(
            "Skills initialization failed (non-critical): %s", skills_db_error
        )


async def initialize_critical_services(app: FastAPI):
    """
    Phase 1: Initialize critical services (BLOCKING).

    Issue #665: Refactored to use extracted helper methods for each service.
    Issue #1088: Further extracted inline blocks into private helpers.

    These services MUST be operational before serving requests.
    Failure in this phase will prevent app startup.

    Args:
        app: FastAPI application instance

    Raises:
        RuntimeError: If any critical service fails to initialize
    """
    await update_app_state_multi(
        initialization_status="phase1",
        initialization_message="Initializing critical services...",
    )
    logger.info("=== PHASE 1: Critical Services Initialization ===")

    try:
        await _init_config(app)
        await _init_security_layer(app)
        await _init_database()
        await _init_telemetry_and_redis()

        # Issue #665: uses helpers
        await _init_chat_history_manager(app)
        await _init_conversation_file_manager(app)
        await _init_chat_workflow_manager(app)

        # Issue #743: Register caches with CacheCoordinator for memory optimization
        await _init_cache_coordinator()

        await _init_skills(app)

        logger.info("✅ [ 60%] PHASE 1 COMPLETE: All critical services operational")

    except Exception as critical_error:
        logger.error("❌ CRITICAL INITIALIZATION FAILED: %s", critical_error)
        logger.error("Backend startup ABORTED - critical services must be operational")
        raise  # Re-raise to prevent app from starting


async def _init_knowledge_base(app: FastAPI):
    """
    Initialize knowledge base (NON-CRITICAL).

    Issue #281: Extracted helper for knowledge base initialization.

    Args:
        app: FastAPI application instance
    """
    logger.info("✅ [ 70%] Knowledge Base: Initializing knowledge base...")
    try:
        knowledge_base = await get_or_create_knowledge_base(app)
        app.state.knowledge_base = knowledge_base
        await update_app_state("knowledge_base", knowledge_base)
        logger.info("✅ [ 70%] Knowledge Base: Knowledge base ready")
    except Exception as kb_error:
        logger.warning("Knowledge base initialization failed: %s", kb_error)
        app.state.knowledge_base = None


async def _init_npu_worker_websocket():
    """
    Initialize NPU Worker WebSocket subscriptions (NON-CRITICAL).

    Issue #281: Extracted helper for NPU WebSocket initialization.
    """
    logger.info("✅ [ 80%] NPU Workers: Initializing WebSocket event subscriptions...")
    try:
        from api.websockets import init_npu_worker_websocket

        init_npu_worker_websocket()
        logger.info("✅ [ 80%] NPU Workers: WebSocket subscriptions initialized")
    except Exception as npu_ws_error:
        logger.warning("NPU worker WebSocket initialization failed: %s", npu_ws_error)


async def _warmup_npu_connection():
    """
    Warm up NPU worker connection for fast first-request embedding (NON-CRITICAL).

    Issue #165: Pre-initializes the NPU connection pool and performs a test
    embedding to ensure the NPU worker's model is ready. This eliminates
    cold-start latency on the first real embedding request.
    """
    logger.info("✅ [ 82%] NPU Warmup: Warming up NPU connection...")
    try:
        from knowledge.facts import warmup_npu_connection

        result = await warmup_npu_connection()

        if result["status"] == "success":
            logger.info(
                "✅ [ 82%] NPU Warmup: Connection ready (%.1fms, %d dimensions)",
                result.get("warmup_time_ms", 0),
                result.get("embedding_dimensions", 0),
            )
        elif result["status"] == "npu_unavailable":
            logger.info(
                "🔄 [ 82%] NPU Warmup: NPU unavailable, using fallback embeddings"
            )
        else:
            logger.warning(
                "⚠️ [ 82%] NPU Warmup: %s", result.get("message", "Unknown status")
            )

    except Exception as warmup_error:
        logger.warning("NPU warmup failed: %s", warmup_error)


async def _init_documentation_watcher():
    """
    Initialize documentation watcher for real-time sync (NON-CRITICAL).

    Issue #165: Starts file system watcher for docs/ directory to enable
    automatic reindexing when documentation files change.
    """
    logger.info("✅ [ 84%] Doc Watcher: Initializing documentation watcher...")
    try:
        from services.documentation_watcher import start_documentation_watcher

        success = await start_documentation_watcher()

        if success:
            logger.info("✅ [ 84%] Doc Watcher: Documentation watcher started")
        else:
            logger.warning("⚠️ [ 84%] Doc Watcher: Failed to start (non-critical)")

    except ImportError as import_error:
        logger.debug("Documentation watcher not available: %s", import_error)
    except Exception as watcher_error:
        logger.warning("Documentation watcher failed: %s", watcher_error)


async def _run_background_doc_indexing():
    """Background task for documentation indexing (#1385, #1390).

    Runs as a fire-and-forget task so it doesn't block startup.
    After indexing, patches HNSW pickle metadata so subsequent
    PersistentClient instances can load the index correctly.
    """
    try:
        from services.knowledge.doc_indexer import get_doc_indexer_service

        indexer = get_doc_indexer_service()
        result = await indexer.index_all(force=False)
        logger.info(
            "Doc Index: done — %d indexed, %d skipped in %.1fs",
            result.success,
            result.skipped,
            result.elapsed_seconds,
        )

        # Fix HNSW pickle format after indexing (#1390)
        from constants.path_constants import PATH
        from utils.chromadb_client import _fix_hnsw_pickle_format

        chroma_path = PATH.PROJECT_ROOT / "data" / "chromadb"
        _fix_hnsw_pickle_format(chroma_path)
    except Exception as e:
        logger.warning("Background doc indexing failed (non-critical): %s", e)


async def _auto_index_documentation():
    """
    Auto-index documentation into ChromaDB if collection is empty (NON-CRITICAL).

    Issue #1385: Ensures autobot_docs ChromaDB collection is populated on startup
    so the chat RAG pipeline can answer documentation queries without hallucinating.
    Initialization is synchronous (fast), but actual indexing runs in background
    to avoid blocking startup.
    """
    logger.info("✅ [ 85%] Doc Index: Checking documentation index...")
    try:
        from services.knowledge.doc_indexer import get_doc_indexer_service

        indexer = get_doc_indexer_service()
        if not await indexer.initialize():
            logger.warning("⚠️ [ 85%] Doc Index: Failed to initialize (non-critical)")
            return

        if not indexer.needs_indexing():
            stats = await indexer.get_stats()
            logger.info(
                "✅ [ 85%] Doc Index: Collection has %d vectors, skipping",
                stats.get("count", 0),
            )
            return

        # Fire-and-forget: run indexing in background so startup continues
        logger.info(
            "✅ [ 85%] Doc Index: Collection empty, " "scheduling background indexing..."
        )
        asyncio.create_task(_run_background_doc_indexing())

    except Exception as index_error:
        logger.warning(
            "Documentation auto-index failed (non-critical): %s", index_error
        )


async def _init_log_forwarding():
    """
    Initialize log forwarding service if auto-start is enabled (NON-CRITICAL).

    Issue #553: Auto-starts log forwarding on backend startup if configured
    via the GUI settings.
    """
    logger.info("✅ [ 86%] Log Forwarding: Checking auto-start configuration...")
    try:
        from api.log_forwarding import get_forwarder

        forwarder = await get_forwarder()

        if forwarder.auto_start and forwarder.destinations:
            logger.info(
                "✅ [ 86%] Log Forwarding: Auto-start enabled, starting service..."
            )
            success = forwarder.start()
            if success:
                logger.info(
                    "✅ [ 86%] Log Forwarding: Started with %d destination(s)",
                    len(forwarder.destinations),
                )
            else:
                logger.warning(
                    "⚠️ [ 86%] Log Forwarding: Failed to start (non-critical)"
                )
        elif forwarder.auto_start:
            logger.info(
                "✅ [ 86%] Log Forwarding: Auto-start enabled but no destinations configured"
            )
        else:
            logger.info("✅ [ 86%] Log Forwarding: Auto-start disabled, skipping")

    except ImportError as import_error:
        logger.debug("Log forwarding not available: %s", import_error)
    except Exception as log_fwd_error:
        logger.warning("Log forwarding initialization failed: %s", log_fwd_error)


async def _init_slm_reconciler(app: FastAPI):
    """
    Initialize SLM reconciliation loop with WebSocket broadcasting (NON-CRITICAL).

    DEPRECATED: Issue #729 - SLM services moved to slm-server at 172.16.168.19.
    This function is disabled as backend/services/slm/ has been removed.
    SLM server runs its own reconciler independently.

    Issue #726: Starts the Service Lifecycle Manager reconciler that monitors
    node health and triggers remediation actions. Wires up WebSocket callbacks
    for real-time event broadcasting.
    """
    logger.info(
        "✅ [ 92%] SLM Reconciler: Skipped (moved to SLM server at 172.16.168.19)"
    )
    # REMOVED as part of Issue #729 layer separation
    # SLM server now runs its own reconciler - no longer initialized from backend
    return


async def _init_graph_rag_service(app: FastAPI, memory_graph):
    """
    Initialize Graph-RAG service (depends on knowledge base and memory graph).

    Issue #281: Extracted helper for Graph-RAG initialization.

    Args:
        app: FastAPI application instance
        memory_graph: Initialized memory graph instance
    """
    logger.info("✅ [ 87%] Graph-RAG: Initializing graph-aware RAG service...")
    try:
        from services.graph_rag_service import GraphRAGService
        from services.rag_config import RAGConfig
        from services.rag_service import RAGService

        if app.state.knowledge_base:
            rag_config = RAGConfig(enable_advanced_rag=True, timeout_seconds=10.0)
            rag_service = RAGService(
                knowledge_base=app.state.knowledge_base, config=rag_config
            )
            await rag_service.initialize()

            graph_rag_service = GraphRAGService(
                rag_service=rag_service,
                memory_graph=memory_graph,
                graph_weight=0.3,
                enable_entity_extraction=True,
            )
            app.state.graph_rag_service = graph_rag_service
            await update_app_state("graph_rag_service", graph_rag_service)
            logger.info(
                "✅ [ 87%] Graph-RAG: Graph-aware RAG service initialized successfully"
            )
        else:
            logger.info("🔄 [ 87%] Graph-RAG: Skipped (knowledge base not available)")
    except Exception as graph_rag_error:
        logger.warning("Graph-RAG service initialization failed: %s", graph_rag_error)
        app.state.graph_rag_service = None


async def _init_entity_extractor(app: FastAPI, memory_graph):
    """
    Initialize entity extractor (depends on memory graph).

    Issue #281: Extracted helper for entity extractor initialization.

    Args:
        app: FastAPI application instance
        memory_graph: Initialized memory graph instance
    """
    logger.info("✅ [ 88%] Entity Extractor: Initializing entity extractor...")
    try:
        from agents.graph_entity_extractor import GraphEntityExtractor
        from agents.knowledge_extraction_agent import KnowledgeExtractionAgent

        knowledge_extraction_agent = KnowledgeExtractionAgent()
        entity_extractor = GraphEntityExtractor(
            extraction_agent=knowledge_extraction_agent,
            memory_graph=memory_graph,
            confidence_threshold=0.6,
            enable_relationship_inference=True,
        )
        app.state.entity_extractor = entity_extractor
        await update_app_state("entity_extractor", entity_extractor)
        logger.info(
            "✅ [ 88%] Entity Extractor: Entity extractor initialized successfully"
        )
    except Exception as entity_error:
        logger.warning("Entity extractor initialization failed: %s", entity_error)
        app.state.entity_extractor = None


async def _init_memory_graph(app: FastAPI):
    """
    Initialize memory graph with dependent services (NON-CRITICAL).

    Issue #281: Extracted helper for memory graph initialization.

    Args:
        app: FastAPI application instance
    """
    logger.info("✅ [ 85%] Memory Graph: Initializing memory graph...")
    try:
        from autobot_memory_graph import AutoBotMemoryGraph

        memory_graph = AutoBotMemoryGraph()
        memory_graph.chat_history_manager = app.state.chat_history_manager
        await memory_graph.initialize()
        app.state.memory_graph = memory_graph
        await update_app_state("memory_graph", memory_graph)
        logger.info("✅ [ 85%] Memory Graph: Memory graph initialized successfully")

        # Initialize dependent services (Issue #281: uses helpers)
        await _init_graph_rag_service(app, memory_graph)
        await _init_entity_extractor(app, memory_graph)

    except Exception as memory_error:
        logger.warning("Memory graph initialization failed: %s", memory_error)
        app.state.memory_graph = None
        app.state.graph_rag_service = None
        app.state.entity_extractor = None


async def _init_slm_client():
    """
    Initialize SLM client for agent configuration (NON-CRITICAL).

    Issue #760: Connects to SLM server for agent LLM config caching.
    Issue #768: Use SSOT config instead of hardcoded URL.
    Falls back gracefully if SLM is unavailable.
    """
    logger.info("✅ [ 89%] SLM Client: Initializing SLM client for agent configs...")
    try:
        # Issue #768: Get SLM URL from SSOT config, fallback to env var
        from autobot_shared.ssot_config import get_config

        slm_url = os.getenv("SLM_URL") or get_config().slm_url
        slm_token = os.getenv("SLM_AUTH_TOKEN")

        await init_slm_client(slm_url, slm_token)
        logger.info("✅ [ 89%] SLM Client: Connected to SLM server at %s", slm_url)
    except Exception as slm_error:
        logger.warning(
            "SLM client initialization failed (continuing without): %s", slm_error
        )


async def _init_metrics_collection():
    """
    Initialize system metrics collection (NON-CRITICAL).

    Issue #876: Start metrics collection AFTER backend initialization completes.
    Previously started at module load time causing self-health-check deadlock.
    """
    logger.info("✅ [ 91%] Metrics Collection: Starting system metrics collection...")
    try:
        # Import here to avoid circular dependency
        from datetime import datetime

        from api.analytics import analytics_controller

        # Initialize session tracking
        analytics_state = {}
        analytics_state["session_start"] = datetime.now().isoformat()

        # Start metrics collection safely (backend is now ready to serve requests)
        collector = analytics_controller.metrics_collector
        if hasattr(collector, "_is_collecting") and not collector._is_collecting:
            import asyncio

            asyncio.create_task(collector.start_collection())
            logger.info("✅ [ 91%] Metrics Collection: Started successfully")
        else:
            logger.info("✅ [ 91%] Metrics Collection: Already running")

    except Exception as metrics_error:
        logger.warning("Metrics collection initialization failed: %s", metrics_error)


async def _init_background_llm_sync(app: FastAPI):
    """
    Initialize background LLM sync and AI Stack client (NON-CRITICAL).

    Issue #281: Extracted helper for LLM sync initialization.

    Args:
        app: FastAPI application instance
    """
    logger.info("✅ [ 90%] Background LLM Sync: Initializing AI Stack integration...")
    try:
        from services.ai_stack_client import AIStackClient

        ai_stack_client = AIStackClient()
        app.state.ai_stack_client = ai_stack_client

        background_llm_sync = BackgroundLLMSync()
        await background_llm_sync.start()
        app.state.background_llm_sync = background_llm_sync
        await update_app_state("background_llm_sync", background_llm_sync)

        # Test AI Stack availability
        try:
            ai_stack_health = await ai_stack_client.health_check()
            if ai_stack_health.get("status") == "healthy":
                logger.info("✅ [ 90%] AI Stack: AI Stack fully available")
            else:
                logger.warning(
                    "AI Stack API unreachable at %s — agent routing disabled",
                    ai_stack_client.base_url,
                )
                ai_stack_client.start_retry_loop()
        except Exception:
            logger.warning(
                "AI Stack API unreachable at %s — agent routing disabled",
                ai_stack_client.base_url,
            )
            ai_stack_client.start_retry_loop()

    except Exception as sync_error:
        logger.warning("Background LLM sync initialization failed: %s", sync_error)


async def initialize_background_services(app: FastAPI):
    """
    Phase 2: Initialize background services (NON-BLOCKING).

    Issue #281: Refactored from 162 lines to use extracted helper methods.

    These services can fail gracefully without preventing app startup.
    Initialization happens in background while app serves requests.

    Args:
        app: FastAPI application instance
    """
    try:
        await update_app_state_multi(
            initialization_status="phase2",
            initialization_message="Loading knowledge base and AI models...",
        )
        logger.info("=== PHASE 2: Background Services Initialization ===")

        # Issue #876: Root cause fixed — metrics collector no longer calls backend
        # self-health endpoint (circular deadlock). Phase 2 re-enabled (#970).
        await _init_knowledge_base(app)
        await _init_npu_worker_websocket()
        await _warmup_npu_connection()
        await _init_memory_graph(app)
        await _init_slm_client()
        await _init_background_llm_sync(app)
        await _init_documentation_watcher()
        await _auto_index_documentation()
        await _init_log_forwarding()
        await _init_slm_reconciler(app)
        await _init_metrics_collection()

        await update_app_state_multi(
            initialization_status="ready",
            initialization_message="All services initialized",
        )
        logger.info("✅ [100%] PHASE 2 COMPLETE: All background services initialized")

    except Exception as e:
        logger.error("Background initialization encountered errors: %s", e)
        logger.info("App remains operational with degraded background services")


async def cleanup_services(app: FastAPI):
    """
    Cleanup services on shutdown

    Args:
        app: FastAPI application instance
    """
    logger.info("🛑 AutoBot Backend shutting down...")
    try:
        if hasattr(app.state, "background_llm_sync") and app.state.background_llm_sync:
            await app.state.background_llm_sync.stop()
        if hasattr(app.state, "memory_graph") and app.state.memory_graph:
            await app.state.memory_graph.close()

        # Issue #165: Stop documentation watcher
        try:
            from services.documentation_watcher import stop_documentation_watcher

            await stop_documentation_watcher()
        except ImportError:
            pass  # Watcher not available

        # Issue #760: Shutdown SLM client
        try:
            await shutdown_slm_client()
            logger.info("✅ SLM client shutdown")
        except Exception as slm_error:
            logger.warning("SLM client shutdown failed: %s", slm_error)

        # Issue #732: Shutdown Gateway
        try:
            if hasattr(app.state, "gateway") and app.state.gateway:
                await app.state.gateway.stop()
                logger.info("✅ Gateway shutdown")
        except Exception as gateway_error:
            logger.warning("Gateway shutdown failed: %s", gateway_error)

        # Issue #726: Stop SLM reconciler
        # REMOVED as part of Issue #729 - SLM moved to slm-server
        # SLM server manages its own reconciler lifecycle
        pass  # SLM reconciler now in slm-server

        # Issue #1233: Shutdown dedicated I/O thread pools
        shutdown_io_executors()

        # Issue #697: Flush and shutdown OpenTelemetry tracing
        await shutdown_tracing()

        # Redis connections automatically managed by get_redis_client()
        logger.info("✅ Cleanup completed successfully")
    except Exception as e:
        logger.error("Error during shutdown: %s", e)


def create_lifespan_manager():
    """
    Create FastAPI lifespan context manager

    Returns:
        Async context manager for application lifespan

    Example:
        ```python
        app = FastAPI(lifespan=create_lifespan_manager())
        ```
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Application lifespan manager with critical and background initialization"""
        global _executor

        # Configure logging
        configure_logging()
        logger.info("🚀 AutoBot Backend starting up...")

        # Create bounded thread pool executor to prevent thread explosion
        # This replaces the default unbounded asyncio executor
        _executor = ThreadPoolExecutor(
            max_workers=MAX_WORKER_THREADS, thread_name_prefix="autobot_worker"
        )
        loop = asyncio.get_event_loop()
        loop.set_default_executor(_executor)
        logger.info(
            "🧵 Bounded thread pool configured (max %d workers)", MAX_WORKER_THREADS
        )

        # Phase 1: Critical initialization (BLOCKING)
        await initialize_critical_services(app)

        # Phase 2: Background initialization (NON-BLOCKING)
        logger.info("🔄 Starting background services initialization...")
        asyncio.create_task(initialize_background_services(app))

        yield  # Application starts serving requests here

        # Cleanup on shutdown
        await cleanup_services(app)

        # Shutdown thread pool
        if _executor:
            _executor.shutdown(wait=True, cancel_futures=False)
            logger.info("🧵 Thread pool shutdown complete")

    return lifespan


# Export app_state for external access
__all__ = ["create_lifespan_manager", "app_state"]
