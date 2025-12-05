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
from contextlib import asynccontextmanager

from backend.type_defs.common import Metadata

from fastapi import FastAPI

from backend.knowledge_factory import get_or_create_knowledge_base
from src.chat_history import ChatHistoryManager
from src.chat_workflow import ChatWorkflowManager
from src.security_layer import SecurityLayer
from src.unified_config_manager import UnifiedConfigManager
from src.utils.background_llm_sync import BackgroundLLMSync

logger = logging.getLogger(__name__)

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
    for logger_name in ["backend", "backend.api", "backend.api.codebase_analytics"]:
        logging.getLogger(logger_name).setLevel(LOG_LEVEL_VALUE)

    logger.info(f"📊 Logging level set to: {LOG_LEVEL} ({LOG_LEVEL_VALUE})")


async def initialize_critical_services(app: FastAPI):
    """
    Phase 1: Initialize critical services (BLOCKING)

    These services MUST be operational before serving requests.
    Failure in this phase will prevent app startup.

    Args:
        app: FastAPI application instance

    Raises:
        RuntimeError: If any critical service fails to initialize
    """
    await update_app_state_multi(
        initialization_status="phase1",
        initialization_message="Initializing critical services..."
    )
    logger.info("=== PHASE 1: Critical Services Initialization ===")

    try:
        # Initialize configuration - CRITICAL
        logger.info("✅ [ 10%] Config: Loading unified configuration...")
        config = UnifiedConfigManager()
        app.state.config = config
        await update_app_state("config", config)
        logger.info("✅ [ 10%] Config: Configuration loaded successfully")

        # Initialize Security Layer - CRITICAL
        logger.info("✅ [ 15%] Security: Initializing security layer...")
        security_layer = SecurityLayer()
        app.state.security_layer = security_layer
        await update_app_state("security_layer", security_layer)
        logger.info("✅ [ 15%] Security: Security layer initialized successfully")

        # Redis connections managed centrally via src.utils.redis_client
        logger.info(
            "✅ [ 20%] Redis: Using centralized Redis client management (src.utils.redis_client)"
        )

        # Initialize Chat History Manager - CRITICAL
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

        # Initialize Conversation File Manager Database - CRITICAL
        logger.info("✅ [ 40%] Conversation Files DB: Initializing database schema...")
        try:
            from src.conversation_file_manager import get_conversation_file_manager

            conversation_file_manager = await get_conversation_file_manager()
            await conversation_file_manager.initialize()
            app.state.conversation_file_manager = conversation_file_manager
            await update_app_state("conversation_file_manager", conversation_file_manager)
            logger.info(
                "✅ [ 40%] Conversation Files DB: Database initialized and verified"
            )
        except Exception as conv_file_error:
            logger.error(
                f"❌ CRITICAL: Conversation files database initialization failed: {conv_file_error}"
            )
            logger.error("Backend startup ABORTED - database must be operational")
            raise RuntimeError(f"Database initialization failed: {conv_file_error}")

        # Initialize Chat Workflow Manager - CRITICAL
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
            raise RuntimeError(
                f"Chat workflow manager initialization failed: {chat_error}"
            )

        logger.info("✅ [ 60%] PHASE 1 COMPLETE: All critical services operational")

    except Exception as critical_error:
        logger.error(f"❌ CRITICAL INITIALIZATION FAILED: {critical_error}")
        logger.error("Backend startup ABORTED - critical services must be operational")
        raise  # Re-raise to prevent app from starting


async def initialize_background_services(app: FastAPI):
    """
    Phase 2: Initialize background services (NON-BLOCKING)

    These services can fail gracefully without preventing app startup.
    Initialization happens in background while app serves requests.

    Args:
        app: FastAPI application instance
    """
    try:
        await update_app_state_multi(
            initialization_status="phase2",
            initialization_message="Loading knowledge base and AI models..."
        )
        logger.info("=== PHASE 2: Background Services Initialization ===")

        # Initialize Knowledge Base - NON-CRITICAL (slow, can fail gracefully)
        logger.info("✅ [ 70%] Knowledge Base: Initializing knowledge base...")
        try:
            knowledge_base = await get_or_create_knowledge_base(app)
            app.state.knowledge_base = knowledge_base
            await update_app_state("knowledge_base", knowledge_base)
            logger.info("✅ [ 70%] Knowledge Base: Knowledge base ready")
        except Exception as kb_error:
            logger.warning(f"Knowledge base initialization failed: {kb_error}")
            app.state.knowledge_base = None

        # Initialize NPU Worker WebSocket subscriptions - NON-CRITICAL
        logger.info(
            "✅ [ 80%] NPU Workers: Initializing WebSocket event subscriptions..."
        )
        try:
            from backend.api.websockets import init_npu_worker_websocket

            init_npu_worker_websocket()
            logger.info("✅ [ 80%] NPU Workers: WebSocket subscriptions initialized")
        except Exception as npu_ws_error:
            logger.warning(
                f"NPU worker WebSocket initialization failed: {npu_ws_error}"
            )

        # Initialize Memory Graph - NON-CRITICAL
        logger.info("✅ [ 85%] Memory Graph: Initializing memory graph...")
        try:
            from src.autobot_memory_graph import AutoBotMemoryGraph

            memory_graph = AutoBotMemoryGraph(
                chat_history_manager=app.state.chat_history_manager
            )
            await memory_graph.initialize()
            app.state.memory_graph = memory_graph
            await update_app_state("memory_graph", memory_graph)
            logger.info("✅ [ 85%] Memory Graph: Memory graph initialized successfully")

            # Initialize Graph-RAG Service - depends on knowledge base and memory graph
            logger.info("✅ [ 87%] Graph-RAG: Initializing graph-aware RAG service...")
            try:
                from backend.services.rag_config import RAGConfig
                from backend.services.rag_service import RAGService
                from src.services.graph_rag_service import GraphRAGService

                if app.state.knowledge_base:
                    # Create RAGConfig with custom settings
                    rag_config = RAGConfig(
                        enable_advanced_rag=True,
                        timeout_seconds=10.0,
                    )
                    rag_service = RAGService(
                        knowledge_base=app.state.knowledge_base,
                        config=rag_config,
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
                    logger.info(
                        "🔄 [ 87%] Graph-RAG: Skipped (knowledge base not available)"
                    )
            except Exception as graph_rag_error:
                logger.warning(
                    f"Graph-RAG service initialization failed: {graph_rag_error}"
                )
                app.state.graph_rag_service = None

            # Initialize Entity Extractor - depends on memory graph
            logger.info("✅ [ 88%] Entity Extractor: Initializing entity extractor...")
            try:
                from src.agents.graph_entity_extractor import GraphEntityExtractor
                from src.agents.knowledge_extraction_agent import (
                    KnowledgeExtractionAgent,
                )

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
                logger.warning(f"Entity extractor initialization failed: {entity_error}")
                app.state.entity_extractor = None

        except Exception as memory_error:
            logger.warning(f"Memory graph initialization failed: {memory_error}")
            app.state.memory_graph = None
            app.state.graph_rag_service = None
            app.state.entity_extractor = None

        # Initialize Background LLM Sync - NON-CRITICAL
        logger.info(
            "✅ [ 90%] Background LLM Sync: Initializing AI Stack integration..."
        )
        try:
            from backend.services.ai_stack_client import AIStackClient

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
                    logger.info("🔄 [ 90%] AI Stack: AI Stack partially available")
            except Exception:
                logger.info("🔄 [ 90%] AI Stack: AI Stack partially available")

        except Exception as sync_error:
            logger.warning(f"Background LLM sync initialization failed: {sync_error}")

        await update_app_state_multi(
            initialization_status="ready",
            initialization_message="All services ready"
        )
        logger.info("✅ [100%] PHASE 2 COMPLETE: All background services initialized")

    except Exception as e:
        logger.error(f"Background initialization encountered errors: {e}")
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
        # Redis connections automatically managed by get_redis_client()
        logger.info("✅ Cleanup completed successfully")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")


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

        # Configure logging
        configure_logging()
        logger.info("🚀 AutoBot Backend starting up...")

        # Phase 1: Critical initialization (BLOCKING)
        await initialize_critical_services(app)

        # Phase 2: Background initialization (NON-BLOCKING)
        logger.info("🔄 Starting background services initialization...")
        asyncio.create_task(initialize_background_services(app))

        yield  # Application starts serving requests here

        # Cleanup on shutdown
        await cleanup_services(app)

    return lifespan


# Export app_state for external access
__all__ = ["create_lifespan_manager", "app_state"]
