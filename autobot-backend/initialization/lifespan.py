# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
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
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_constants import STARTUP_ERROR_FILE
from autobot_shared.tracing import (
    instrument_aiohttp,
    instrument_redis,
    shutdown_tracing,
)
from chat_history import ChatHistoryManager
from chat_workflow import ChatWorkflowManager
from config.manager import get_config_manager
from knowledge_factory import get_or_create_knowledge_base
from security_layer import SecurityLayer
from services.slm_client import init_slm_client, shutdown_slm_client
from type_defs.common import Metadata
from user_management.database import init_database
from utils.background_llm_sync import BackgroundLLMSync
from utils.io_executor import shutdown_executors as shutdown_io_executors

# Bounded thread pool to prevent unbounded thread creation
# Default asyncio executor creates min(32, cpu_count + 4) threads per invocation
# This shared executor limits total threads across all run_in_executor calls
MAX_WORKER_THREADS = 16
_executor: ThreadPoolExecutor | None = None

logger = get_logger(__name__)

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
    "startup_error": None,  # GH#8947: capture startup errors for health visibility
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
    from autobot_shared.ssot_config import config as _ssot_cfg

    LOG_LEVEL = _ssot_cfg.log_level.upper()
    LOG_LEVEL_VALUE = getattr(logging, LOG_LEVEL, logging.INFO)
    logging.root.setLevel(LOG_LEVEL_VALUE)

    # Set level for all backend loggers
    for logger_name in _BACKEND_LOGGER_NAMES:
        get_logger(logger_name).setLevel(LOG_LEVEL_VALUE)

    logger.info("📊 Logging level set to: %s (%s)", LOG_LEVEL, LOG_LEVEL_VALUE)


def warn_if_dev_auth_bypass_enabled() -> None:
    """Loud boot-time warning when AUTOBOT_DEV_AUTH_BYPASS=true (Issue #6838).

    The single_user synthetic-admin login shortcut is opt-in. When the flag is
    set, /api/auth/login mints an admin JWT for any credential pair — which is
    intended for local development only. Surfaced loudly so operators notice
    if it leaks into a production deployment.
    """
    from api.auth import _dev_auth_bypass_enabled

    if not _dev_auth_bypass_enabled():
        return
    banner = "=" * 72
    logger.warning(banner)
    logger.warning("⚠️  AUTOBOT_DEV_AUTH_BYPASS=true — /api/auth/login will mint an admin")
    logger.warning("    JWT for ANY credentials in single_user mode. DO NOT use in")
    logger.warning("    production. Unset the flag or switch AUTOBOT_USER_MODE away from")
    logger.warning("    single_user to disable. See issue #6838.")
    logger.warning(banner)


async def _init_cache_coordinator() -> None:
    """Register caches with CacheCoordinator for memory optimization.

    Helper for initialize_critical_services (Issue #743).
    """
    logger.info("✅ [ 55%] Cache: Registering caches with CacheCoordinator...")
    try:
        from cache import register_all_caches

        cache_count = await register_all_caches()
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
        await chat_history_manager.initialize()
        app.state.chat_history_manager = chat_history_manager
        await update_app_state("chat_history_manager", chat_history_manager)
        logger.info("✅ [ 30%] Chat History: Manager initialized successfully")
    except Exception as chat_history_error:
        logger.error(f"❌ CRITICAL: Chat history manager initialization failed: {chat_history_error}")
        raise RuntimeError(f"Chat history manager initialization failed: {chat_history_error}")


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
        logger.error(f"❌ CRITICAL: Conversation files database initialization failed: {conv_file_error}")
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
        logger.error(f"❌ CRITICAL: Chat workflow manager initialization failed: {chat_error}")
        raise RuntimeError(f"Chat workflow manager initialization failed: {chat_error}")


async def _check_env_drift() -> None:
    """Run .env drift check against SSOT config definitions (Issue #2650).

    Non-critical: a failed or drifted check is logged as a warning and never
    prevents startup.  This runs before other init steps so operators see drift
    warnings at the very top of the startup log.
    """
    try:
        from autobot_shared.env_drift_detector import check_env_drift

        report = check_env_drift()
        if report.error:
            logger.warning("env drift check skipped: %s", report.error)
        elif report.has_drift:
            logger.warning(
                "env drift detected — run 'python -m autobot_shared.env_drift_detector' " "for details (%s)",
                report.summary(),
            )
        else:
            logger.info(
                "env drift check passed: all %d SSOT keys present in .env",
                len(report.ssot_keys),
            )
    except Exception as exc:
        logger.warning("env drift check failed (non-critical): %s", exc)


async def _init_config(app: FastAPI) -> None:
    """Helper for initialize_critical_services. Ref: #1088, #3398."""
    logger.info("✅ [ 10%] Config: Loading unified configuration...")
    config = get_config_manager()
    app.state.config = config
    await update_app_state("config", config)
    logger.info("✅ [ 10%] Config: Configuration loaded successfully")

    # Issue #3398: Run startup validation — log override warnings, fail fast on
    # invalid values (e.g. negative ports, missing required keys).
    validation_result = config.validate_startup()
    if not validation_result.valid:
        error_summary = "; ".join(validation_result.errors)
        raise RuntimeError(f"Configuration validation failed at startup: {error_summary}")
    if validation_result.warnings:
        logger.warning(
            "Config: %d override warning(s) detected — review logged warnings above",
            len(validation_result.warnings),
        )


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
    logger.info("✅ [ 20%] Redis: Using centralized Redis client management (src.utils.redis_client)")


async def _init_skills(app: FastAPI) -> None:
    """Helper for initialize_critical_services. Ref: #1088.

    Initializes skills system tables and discovers builtin skills (non-critical).
    """
    try:
        await _init_skills_tables()
        await _init_skills_discovery()
    except Exception as skills_db_error:
        logger.warning("Skills initialization failed (non-critical): %s", skills_db_error)


async def _init_builtin_extensions(app: FastAPI) -> None:
    """Register built-in extensions (logging, secret masking, permission enforcement).

    Issue #658: Registers LoggingExtension and SecretMaskingExtension.
    Issue #3009: Wires PermissionEnforcementExtension into the extension
    manager so all tool executions are subject to role-based permission checks.
    Issue #4183: Registers SecretMaskingExtension as a builtin extension.
    Non-critical: a failure logs a warning but does not block startup.
    """
    try:
        from middleware.builtin import (
            LoggingExtension,
            PermissionEnforcementExtension,
            SecretMaskingExtension,
        )
        from middleware.manager import ExtensionManager

        manager = getattr(app.state, "extension_manager", None)
        if manager is None:
            manager = ExtensionManager()
            app.state.extension_manager = manager

        manager.register(LoggingExtension())
        manager.register(SecretMaskingExtension())
        manager.register(PermissionEnforcementExtension())
        logger.info("Built-in extensions registered (logging, secret_masking, permission_enforcement)")
    except Exception as ext_error:
        logger.warning("Built-in extension registration failed (non-critical): %s", ext_error)


async def _init_transcriber_db(app: FastAPI) -> None:
    """Initialize the transcriber SQLite database (GH#9044).

    Non-critical: a failure logs a warning but does not block startup.
    Skipped entirely when TRANSCRIBER_ENABLED != true.
    Sets ``app.state.transcriber_db``, ``app.state.transcriber_upload_dir``,
    and ``app.state.transcriber_export_dir`` for use by the dependency
    injection layer (``transcriber.deps.get_db``).
    """
    import os
    from pathlib import Path as _Path

    enabled = os.getenv("TRANSCRIBER_ENABLED", "true").lower() == "true"
    if not enabled:
        logger.info("Transcriber DB init skipped (TRANSCRIBER_ENABLED != true)")
        return
    try:
        from transcriber.database import Database

        data_dir = _Path(os.getenv("TRANSCRIBER_DATA_DIR", "data/transcriber"))
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / "uploads").mkdir(exist_ok=True)
        (data_dir / "processed").mkdir(exist_ok=True)
        (data_dir / "exports").mkdir(exist_ok=True)
        db = Database(str(data_dir / "transcriber.db"))
        await db.connect()
        app.state.transcriber_db = db
        app.state.transcriber_upload_dir = str(data_dir / "uploads")
        app.state.transcriber_export_dir = str(data_dir / "exports")
        logger.info("Transcriber DB initialized")
    except Exception as _tc_err:
        logger.warning("Transcriber DB init failed (non-critical): %s", _tc_err)


async def initialize_critical_services(app: FastAPI):
    """
    Phase 1: Initialize critical services (BLOCKING).

    Issue #665: Refactored to use extracted helper methods for each service.
    Issue #1088: Further extracted inline blocks into private helpers.
    Issue #3015: Grouped independent steps into dependency tiers and run each
    tier concurrently with asyncio.gather() to reduce startup latency.

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
        # Issue #3015: Group init steps into dependency tiers and run each
        # tier concurrently with asyncio.gather() to reduce startup latency.
        #
        # Tier 0 (sequential): env drift check + config — must complete before
        #         anything else since all services may read global config.
        # Tier 1 (parallel): security, database, telemetry — independent of
        #         each other, only need the module-level global config manager.
        # Tier 2 (parallel): chat managers — independent of each other; benefit
        #         from telemetry instrumentation being in place for tracing.
        # Tier 3 (parallel): cache coordinator + skills — non-critical,
        #         independent of each other and of the chat managers.

        # --- Tier 0: config foundation (sequential) ---
        # Issue #2650: check .env drift before any service initialisation
        await _check_env_drift()
        await _init_config(app)

        # --- Tier 1: independent infrastructure (parallel) ---
        await asyncio.gather(
            _init_security_layer(app),
            _init_database(),
            _init_telemetry_and_redis(),
        )

        # --- Tier 2: chat service managers (parallel) ---
        # Issue #665: uses helpers
        await asyncio.gather(
            _init_chat_history_manager(app),
            _init_conversation_file_manager(app),
            _init_chat_workflow_manager(app),
        )

        # --- Tier 3: non-critical services (parallel) ---
        # Issue #743: Register caches with CacheCoordinator for memory optimization
        # Issue #3009: Register built-in extensions (permission enforcement)
        # GH#9044: Transcriber DB
        await asyncio.gather(
            _init_cache_coordinator(),
            _init_skills(app),
            _init_builtin_extensions(app),
            _init_transcriber_db(app),
        )

        logger.info("✅ [ 60%] PHASE 1 COMPLETE: All critical services operational")

    except Exception as critical_error:
        logger.error("❌ CRITICAL INITIALIZATION FAILED: %s", critical_error)
        logger.error("Backend startup ABORTED - critical services must be operational")
        error_type = type(critical_error).__name__
        logger.error("Startup error detail: %s: %s", error_type, str(critical_error))
        await update_app_state_multi(
            initialization_status="error",
            initialization_message="Startup failed — check server logs for details",
            startup_error=error_type,
        )
        # GH#8947: Persist error type to disk before re-raising — the process will
        # exit before binding to port, so the in-memory app_state update above is
        # unreachable. The file survives process exit and lets /api/health report
        # the failure when the next (probe) process reads it.
        try:
            STARTUP_ERROR_FILE.parent.mkdir(parents=True, exist_ok=True)
            STARTUP_ERROR_FILE.write_text(
                json.dumps(
                    {
                        "error_type": error_type,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                ),
                encoding="utf-8",
            )
        except Exception:
            pass  # File write failure must not mask the original startup error
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

        # Issue #2309: Wire KB into the already-initialized chat workflow manager.
        # Phase 1 initializes the manager before the KB is ready, leaving
        # knowledge_service=None. Re-wire here once the KB succeeds.
        mgr = getattr(app.state, "chat_workflow_manager", None)
        if mgr is not None and knowledge_base is not None and mgr.knowledge_service is None:
            await mgr.set_knowledge_base(knowledge_base)

        # Issue #8391: Start VectorWriteBuffer background flush task.
        write_buffer = getattr(knowledge_base, "_write_buffer", None)
        if write_buffer is not None:
            await write_buffer.start()

        # Issue #8392: Start CollectionTierManager background reaper.
        # Issue #8408: Pass the sync Redis client so all uvicorn workers share tier state.
        try:
            from autobot_shared.redis_client import get_redis_client as _get_sync_redis
            from knowledge.tiering import get_tier_manager

            _tier_redis = _get_sync_redis(database="knowledge")
            await get_tier_manager(redis_client=_tier_redis).start()
            app.state.tier_manager = get_tier_manager()
        except Exception as _tm_err:
            logger.warning("CollectionTierManager startup failed: %s", _tm_err)
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


async def _warmup_npu_connection(app: FastAPI) -> None:
    """
    Warm up NPU worker connection for fast first-request embedding (NON-CRITICAL).

    Issue #165: Pre-initializes the NPU connection pool and performs a test
    embedding to ensure the NPU worker's model is ready. This eliminates
    cold-start latency on the first real embedding request.

    Sets app.state.npu_worker_ready so /api/health can report accurate
    npu_acceleration capability status (#6768).
    """
    logger.info("✅ [ 82%] NPU Warmup: Warming up NPU connection...")
    npu_ready = False
    try:
        from knowledge.facts import warmup_npu_connection

        result = await warmup_npu_connection()

        if result["status"] == "success":
            npu_ready = True
            logger.info(
                "✅ [ 82%] NPU Warmup: Connection ready (%.1fms, %d dimensions)",
                result.get("warmup_time_ms", 0),
                result.get("embedding_dimensions", 0),
            )
        elif result["status"] == "npu_unavailable":
            logger.info("🔄 [ 82%] NPU Warmup: NPU unavailable, using fallback embeddings")
        else:
            logger.warning("⚠️ [ 82%] NPU Warmup: %s", result.get("message", "Unknown status"))

    except Exception as warmup_error:
        logger.warning("NPU warmup failed: %s", warmup_error)
    finally:
        app.state.npu_worker_ready = npu_ready


async def _start_doc_sync_queue_worker(app: FastAPI) -> None:
    """Start the persistent document sync queue worker (#4453).

    The worker drains :class:`DocumentSyncQueue` so re-indexing survives
    crashes, retries up to MAX_ATTEMPTS, and respects priority ordering.
    """
    try:
        from services.knowledge.sync_queue import SyncQueueWorker

        worker = SyncQueueWorker()
        task = asyncio.create_task(worker.run())
        app.state.doc_sync_queue_worker = worker
        app.state.doc_sync_queue_worker_task = task
        logger.info("✅ Doc Sync Queue: worker started")
    except Exception as e:  # noqa: BLE001
        logger.warning("Doc sync queue worker failed to start: %s", e)


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


async def _init_kb_folder_watcher():
    """
    Initialize KB folder watcher for automatic document ingestion (NON-CRITICAL).

    Issue #9000: Starts filesystem watcher for user-configured directories to enable
    automatic ingestion of new files into knowledge base collections.
    """
    logger.info("✅ [ 84%] KB Folder Watcher: Initializing KB folder watcher...")
    try:
        from services.kb_folder_watcher import start_kb_folder_watcher

        success = await start_kb_folder_watcher()

        if success:
            logger.info("✅ [ 84%] KB Folder Watcher: KB folder watcher started")
        else:
            logger.info("✅ [ 84%] KB Folder Watcher: No watch folders configured")

    except ImportError as import_error:
        logger.debug("KB folder watcher not available: %s", import_error)
    except Exception as watcher_error:
        logger.warning("KB folder watcher failed: %s", watcher_error)


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
        logger.info("✅ [ 85%] Doc Index: Collection empty, " "scheduling background indexing...")
        asyncio.create_task(_run_background_doc_indexing())

    except Exception as index_error:
        logger.warning("Documentation auto-index failed (non-critical): %s", index_error)


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
            logger.info("✅ [ 86%] Log Forwarding: Auto-start enabled, starting service...")
            success = forwarder.start()
            if success:
                logger.info(
                    "✅ [ 86%] Log Forwarding: Started with %d destination(s)",
                    len(forwarder.destinations),
                )
            else:
                logger.warning("⚠️ [ 86%] Log Forwarding: Failed to start (non-critical)")
        elif forwarder.auto_start:
            logger.info("✅ [ 86%] Log Forwarding: Auto-start enabled but no destinations configured")
        else:
            logger.info("✅ [ 86%] Log Forwarding: Auto-start disabled, skipping")

    except ImportError as import_error:
        logger.debug("Log forwarding not available: %s", import_error)
    except Exception as log_fwd_error:
        logger.warning("Log forwarding initialization failed: %s", log_fwd_error)


async def _init_llc_outbound_sync(app: FastAPI) -> None:
    """Start the LLC outbound PM sync subscriber (GH#8257)."""
    logger.info("LLC Outbound Sync: Starting...")
    try:
        from llc.sync.outbound_sync import get_outbound_sync_service

        svc = get_outbound_sync_service()
        await svc.start()
        app.state.llc_outbound_sync = svc
        logger.info("LLC Outbound Sync: Started")
    except Exception as exc:
        logger.warning("LLC outbound sync startup failed (non-fatal): %s", exc)
        app.state.llc_outbound_sync = None


async def _init_llc_routine_scheduler(app: FastAPI) -> None:
    """Start the LLC RoutineScheduler that fires cron-based routines (GH#8229)."""
    logger.info("LLC Routine Scheduler: Starting...")
    try:
        from llc.scheduler.routine_scheduler import RoutineScheduler

        scheduler = RoutineScheduler()
        await scheduler.startup()
        app.state.llc_routine_scheduler = scheduler
        logger.info("LLC Routine Scheduler: Started")
    except Exception as exc:
        logger.warning("LLC routine scheduler startup failed (non-fatal): %s", exc)
        app.state.llc_routine_scheduler = None


async def _init_heartbeat_scheduler(app: FastAPI) -> None:
    """
    Start heartbeat scheduler for scheduled agent wakeups (NON-CRITICAL).

    Issue #1407: Loads enabled agents from DB and spawns their asyncio loops.
    GH#8225: Prefers the LLC HeartbeatScheduler; falls back to legacy when
    the LLC package is unavailable, preventing duplicate sorted-set writes.
    """
    # GH#8225: Try LLC scheduler first; it owns llc:heartbeat:schedule.
    # Use get_heartbeat_scheduler() — same lazy_singleton instance used by API routes —
    # so cleanup_services.stop() drains tasks from both startup-fired and API-triggered runs.
    try:
        from llc.scheduler.heartbeat_scheduler import get_heartbeat_scheduler

        llc_scheduler = get_heartbeat_scheduler()
        await llc_scheduler.start()
        app.state.heartbeat_scheduler = llc_scheduler
        logger.info("Heartbeat: LLC HeartbeatScheduler started")
        return
    except Exception as llc_error:
        logger.warning("LLC heartbeat scheduler unavailable, falling back to legacy: %s", llc_error)

    logger.info("Heartbeat: Starting legacy heartbeat scheduler...")
    try:
        from api.heartbeat import configure_scheduler
        from services.heartbeat_scheduler import HeartbeatScheduler
        from user_management.database import get_async_session_factory

        session_factory = get_async_session_factory()
        scheduler = HeartbeatScheduler(session_factory)
        await scheduler.start()
        app.state.heartbeat_scheduler = scheduler
        configure_scheduler(scheduler)

        # Wire budget policy enforcement — must run after session factory is ready (GH#6470)
        from services.budget_policy import configure_session_factory as _cfg_bp
        from services.budget_policy import seed_default_policies

        _cfg_bp(session_factory)
        try:
            await seed_default_policies()
        except Exception as bp_seed_err:
            logger.warning("Budget policy seed failed (non-critical): %s", bp_seed_err)

        logger.info("Heartbeat: Legacy scheduler started")
    except Exception as hb_error:
        logger.warning("Heartbeat scheduler initialization failed: %s", hb_error)
        app.state.heartbeat_scheduler = None


async def _start_connector_scheduler() -> None:
    """Start the Redis-backed connector scheduler leader-election loop (NON-CRITICAL).

    Issue #6556: Kicks off the per-worker background task that competes for the
    connector-scheduler leader lock.  Whichever worker wins runs the asyncio sync
    tasks; all workers answer is_running() consistently via Redis.
    """
    logger.info("Connector scheduler: starting leader-election loop...")
    try:
        from knowledge.connectors.scheduler import get_connector_scheduler

        scheduler = get_connector_scheduler()
        await scheduler.begin_leader_election()
        logger.info("Connector scheduler: leader-election loop started")
    except Exception as cs_error:
        logger.warning("Connector scheduler initialization failed: %s", cs_error)


async def _init_trigger_service(app: FastAPI) -> None:
    """Start TriggerService background loops for event-driven triggers (#3100)."""
    logger.info("Triggers: Starting trigger service...")
    try:
        from api.triggers import get_trigger_service

        trigger_service = get_trigger_service()

        async def _launch_workflow(workflow_id: str, payload: dict) -> None:
            """Launcher callback invoked by TriggerService when a trigger fires."""
            from services.workflow_automation import get_workflow_manager

            logger.info(
                "Trigger fired for workflow %s with payload keys=%s",
                workflow_id,
                list(payload.keys()) if payload else [],
            )
            mgr = get_workflow_manager()
            if mgr:
                await mgr.start_workflow_execution(workflow_id, trigger_payload=payload)

        await trigger_service.start(launcher=_launch_workflow)
        app.state.trigger_service = trigger_service
        logger.info("Triggers: Service started")
    except Exception as trigger_error:
        logger.warning("Trigger service initialization failed: %s", trigger_error)
        app.state.trigger_service = None


async def _init_slm_reconciler(app: FastAPI):
    """
    Initialize SLM reconciliation loop with WebSocket broadcasting (NON-CRITICAL).

    DEPRECATED: Issue #729 - SLM services moved to SLM server.
    This function is disabled as backend/services/slm/ has been removed.
    SLM server runs its own reconciler independently.

    Issue #726: Starts the Service Lifecycle Manager reconciler that monitors
    node health and triggers remediation actions. Wires up WebSocket callbacks
    for real-time event broadcasting.
    """
    logger.info("✅ [ 92%] SLM Reconciler: Skipped (moved to SLM server)")
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
        from services.rag_service import RAGService, register_shared_mesh_components

        if app.state.knowledge_base:
            rag_config = RAGConfig(enable_advanced_rag=True, timeout_seconds=10.0)
            rag_service = RAGService(knowledge_base=app.state.knowledge_base, config=rag_config)
            await rag_service.initialize()

            # Build mesh brain components and register them so every RAGService.initialize()
            # can construct its OWN NeuralMeshRetriever with closures bound to its own
            # optimizer — eliminating the shared-singleton coupling (#4765).
            try:
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

                _mesh_components = {
                    "mesh_db": _mesh_db,
                    "ppr": _ppr,
                    "edge_learner": _edge_learner,
                    "reranker": ResultReranker(),
                    "classifier": QueryClassifier(),
                    "llm": None,
                }

                # Store on app.state for introspection / health checks.
                app.state.mesh_components = _mesh_components

                # Expose mesh_db on app.state so _start_community_clustering_loop can use it (#4834).
                app.state.mesh_db = _mesh_db

                # Register components; each future RAGService.initialize() builds its own
                # retriever from these, binding closures to its own optimizer (#4765).
                register_shared_mesh_components(_mesh_components)

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

                logger.info(
                    "✅ [ 87%] Neural Mesh RAG: mesh components registered; "
                    "per-instance NeuralMeshRetriever will build on next initialize() (#4765)"
                )
            except Exception as _mesh_wire_err:
                logger.warning("Neural Mesh RAG wiring skipped (non-fatal): %s", _mesh_wire_err)

            graph_rag_service = GraphRAGService(
                rag_service=rag_service,
                memory_graph=memory_graph,
                graph_weight=0.3,
                enable_entity_extraction=True,
            )
            app.state.graph_rag_service = graph_rag_service
            await update_app_state("graph_rag_service", graph_rag_service)
            logger.info("✅ [ 87%] Graph-RAG: Graph-aware RAG service initialized successfully")
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
        logger.info("✅ [ 88%] Entity Extractor: Entity extractor initialized successfully")
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

        slm_url = get_config().slm_url
        slm_token = get_config().slm_auth_token
        if not slm_token:
            logger.warning(
                "SLM_AUTH_TOKEN is unset — SLM WebSocket will connect without auth header. "
                "Set SERVICE_AUTH_ENFORCEMENT_MODE=false or configure the token to avoid 403 errors."
            )

        await init_slm_client(slm_url, slm_token)
        logger.info("✅ [ 89%] SLM Client: Connected to SLM server at %s", slm_url)
        from services.slm.deployment_bridge import init_orchestrator
        from services.slm_client import get_slm_client as _get_slm_client

        init_orchestrator(_get_slm_client())
        logger.info("✅ [ 89%] SLM Client: DeploymentCoordinator initialised")
    except Exception as slm_error:
        logger.warning("SLM client initialization failed (continuing without): %s", slm_error)


async def _init_metrics_collection():
    """
    Initialize system metrics collection (NON-CRITICAL).

    Issue #876: Start metrics collection AFTER backend initialization completes.
    Previously started at module load time causing self-health-check deadlock.
    """
    logger.info("✅ [ 91%] Metrics Collection: Starting system metrics collection...")
    try:
        # Import here to avoid circular dependency
        from datetime import datetime, timezone

        from api.analytics import analytics_controller

        # Initialize session tracking
        analytics_state = {}
        analytics_state["session_start"] = datetime.now(tz=timezone.utc).isoformat()

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
                try:
                    agents_info = await ai_stack_client.list_available_agents()
                    if agents_info.get("agents"):
                        app.state.ai_stack_agents = agents_info
                        logger.info(
                            "✅ [ 90%] AI Stack: %d agents registered from %s",
                            len(agents_info["agents"]),
                            agents_info.get("source", "ai_stack"),
                        )
                except Exception as agents_exc:
                    logger.warning("AI Stack agent listing failed: %s", agents_exc)
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


async def _seed_agent_registry() -> None:
    """Populate agents table from DEFAULT_AGENT_CONFIGS (#1754)."""
    logger.info("[ 97%%] Agent Registry: Seeding agents table...")
    try:
        from services.agent_registry_service import seed_agents_from_config
        from user_management.database import get_async_session_factory

        async with get_async_session_factory()() as session:
            count = await seed_agents_from_config(session)
        logger.info("[ 97%%] Agent Registry: %d agents seeded", count)
    except Exception as e:
        logger.warning("Agent registry seeding failed: %s", e)


async def _init_process_adapter(app: FastAPI) -> None:
    """Start ProcessAdapterService queue dispatcher (#1748).

    NON-CRITICAL: process management endpoints return 503 until this completes.
    """
    logger.info("[ 96%%] Process Adapter: Initializing...")
    try:
        from api.process_management import set_process_adapter_service
        from services.process_adapter_service import ProcessAdapterService
        from user_management.database import get_async_session_factory

        svc = ProcessAdapterService(session_factory=get_async_session_factory())
        await svc.start()
        app.state.process_adapter_service = svc
        set_process_adapter_service(svc)
        logger.info("[ 96%%] Process Adapter: Dispatcher started")
    except Exception as e:
        logger.warning("Process adapter initialization failed: %s", e)
        app.state.process_adapter_service = None


async def _recover_index_queue():
    """Restore queued indexing jobs from Redis after restart (#1717)."""
    try:
        from api.codebase_analytics.scanner import recover_index_queue

        count = await recover_index_queue()
        if count:
            logger.info(
                "[ 95%%] Index Queue: Recovered %d jobs from Redis",
                count,
            )
        else:
            logger.info("[ 95%%] Index Queue: No pending jobs to recover")
    except Exception as e:
        logger.warning("Index queue recovery failed (non-fatal): %s", e)


async def _ensure_agent_memory_index() -> None:
    """Auto-create the idx:agent_memory RediSearch vector index if it doesn't exist (#2645).

    Idempotent — safe to call on every startup. If the index already exists,
    handle_redis_vector_create_index returns immediately without error.
    Uses the vectors database (Redis DB 8) with default agent-memory schema:
    HNSW, FLOAT32, 1536 dimensions, COSINE distance.
    """
    logger.info("[ 93%%] Agent Memory Index: Ensuring idx:agent_memory exists...")
    try:
        from api.redis_mcp.vector_search import handle_redis_vector_create_index

        result = await handle_redis_vector_create_index(
            index_name="idx:agent_memory",
            prefix="autobot:agent:memory:",
            vector_field="embedding",
            dimensions=1536,
            distance_metric="COSINE",
            database="vectors",
        )
        if result.get("message") == "Index already exists":
            logger.info("[ 93%%] Agent Memory Index: idx:agent_memory already exists")
        else:
            logger.info(
                "[ 93%%] Agent Memory Index: idx:agent_memory created " "(prefix=%s, dims=%d, metric=%s)",
                result.get("prefix"),
                result.get("dimensions"),
                result.get("distance_metric"),
            )
    except Exception as e:
        logger.warning("Agent memory index creation failed (non-critical): %s", e)


async def _init_orchestrator(app: FastAPI) -> None:
    """Initialize and store the orchestrator on app.state (#2235).

    Uses the existing ``get_orchestrator()`` async singleton which calls
    ``await orchestrator.initialize()`` (LLM interface, memory manager, agent
    manager, Ollama validation).  NON-CRITICAL: endpoints that need it will
    return 422 if this fails rather than crashing the whole application.
    """
    logger.info("[ 97%%] Orchestrator: Initializing...")
    try:
        from orchestrator import get_orchestrator

        orchestrator = await get_orchestrator()
        app.state.orchestrator = orchestrator
        logger.info("[ 97%%] Orchestrator: Initialized and stored on app.state")
    except Exception as e:
        logger.warning("Orchestrator initialization failed (non-fatal): %s", e)
        app.state.orchestrator = None


async def _wire_npu_task_queue() -> None:
    """Wire NPUWorkerManager into the global TaskQueue for per-worker task tracking (#2985).

    TaskQueue._worker_loop already calls assign_task_to_worker / release_worker_task
    behind an ``if self.npu_worker_manager is not None:`` guard, but the attribute was
    never set to an actual instance — making all tracking code dead (#2944).  This helper
    runs during Phase 2 (non-critical) so that startup is never blocked by NPU issues.
    """
    logger.info("[ 98%%] NPU Task Queue: Wiring NPUWorkerManager into TaskQueue...")
    try:
        from autobot_shared.redis_client import get_async_redis_client
        from services.npu_worker_manager import get_worker_manager
        from utils.task_queue import get_task_queue

        redis_client = await get_async_redis_client(database="main")
        worker_manager = await get_worker_manager(redis_client=redis_client)
        task_queue = get_task_queue()
        task_queue.npu_worker_manager = worker_manager
        logger.info("[ 98%%] NPU Task Queue: NPUWorkerManager wired — per-worker task tracking active")
    except Exception as e:
        logger.warning("NPU task queue wiring failed (per-worker tracking disabled): %s", e)


async def _init_voice_interface(app: FastAPI) -> None:
    """Initialize VoiceInterface and attach it to app.state (#3848).

    NON-CRITICAL: voice endpoints return 503 when this is unavailable.
    Runs in Phase 2 because voice hardware is not required for core operation.
    """
    logger.info("[ 99%%] Voice Interface: Initializing...")
    try:
        from voice_interface import VoiceInterface

        voice_interface = VoiceInterface()
        app.state.voice_interface = voice_interface
        logger.info("[ 99%%] Voice Interface: Initialized and attached to app.state")
    except Exception as e:
        logger.warning(
            "Voice interface initialization failed (non-critical): %s — " "voice endpoints will return 503",
            e,
        )
        app.state.voice_interface = None


async def _init_llm_key_rotation_scheduler(app: FastAPI) -> None:
    """Start LLM API key expiry rotation scheduler (issue #6590).

    NON-CRITICAL: key expiry rotation not required for request handling.
    """
    logger.info("[100%%] LLM Key Rotation: Initializing...")
    try:
        from services.llm_key_rotation_scheduler import get_llm_key_rotation_scheduler

        scheduler = get_llm_key_rotation_scheduler()
        await scheduler.start()
        app.state.llm_key_rotation_scheduler = scheduler
        logger.info("[100%%] LLM Key Rotation: Scheduler started")
    except Exception as e:
        logger.warning("LLM key rotation scheduler initialization failed (non-critical): %s", e)
        app.state.llm_key_rotation_scheduler = None


async def _init_backup_scheduler(app: FastAPI) -> None:
    """Start the knowledge-base backup scheduler (issue #3294).

    NON-CRITICAL: backup failures do not affect request handling.
    Runs in Phase 2; scheduler wakes at AUTOBOT_BACKUP_SCHEDULE_HOUR (default 02:00 UTC).
    """
    logger.info("[100%%] Backup Scheduler: Initializing...")
    try:
        from backup.scheduler import BackupScheduler

        scheduler = BackupScheduler()
        await scheduler.start()
        app.state.backup_scheduler = scheduler
        logger.info(
            "[100%%] Backup Scheduler: Started (daily at %02d:00 UTC)",
            scheduler._schedule_hour,
        )
    except Exception as e:
        logger.warning("Backup scheduler initialization failed (non-critical): %s", e)
        app.state.backup_scheduler = None


async def _start_autonomous_loop(app: FastAPI) -> None:
    """Start the autonomous RAG/synthesis improvement loop background task (Issue #4680).

    NON-CRITICAL: loop failures do not affect request handling.
    Only fires a background task when ``autonomous_loop_enabled`` is True.
    """
    logger.info("[100%%] AutonomousLoop: Initializing...")
    try:
        from workflow_scheduler import start_autonomous_loop

        llm_service = getattr(app.state, "llm_service", None)
        start_autonomous_loop(llm_service)
        logger.info("[100%%] AutonomousLoop: background task started")
    except Exception as exc:
        logger.warning("AutonomousLoop initialization failed (non-critical): %s", exc)


async def _wire_scheduler_executor() -> None:
    """Wire the orchestration WorkflowExecutor into the global WorkflowScheduler (#2166).

    Replaces the scheduler's fallback _default_template_executor with an adapter
    that delegates non-template scheduled workflows to Orchestrator, enabling
    full agent coordination, step dependency management, and auto-documentation for
    all scheduled workflows — not just template-based ones.

    NON-CRITICAL: template-based workflows still work if this fails.
    """
    logger.info("[ 98%%] Scheduler: Wiring orchestration executor...")
    try:
        from orchestrator import get_orchestrator_sync
        from workflow_scheduler import ScheduledWorkflow, get_workflow_scheduler

        orchestrator = get_orchestrator_sync()

        async def _orchestration_executor(workflow: ScheduledWorkflow):
            """Adapter: ScheduledWorkflow → Orchestrator.execute_enhanced_workflow.

            Routes template-based workflows to the template executor and
            non-template workflows through the full orchestration pipeline.
            Ref: #2166.
            """
            if workflow.template_id:
                from workflow_scheduler import _default_template_executor

                return await _default_template_executor(workflow)

            context = {
                "workflow_id": workflow.id,
                "user_id": workflow.user_id,
                "variables": workflow.variables or {},
                "tags": workflow.tags or [],
                "auto_approve": workflow.auto_approve,
                "scheduled": True,
            }
            result = await orchestrator.execute_enhanced_workflow(
                user_request=workflow.user_message,
                context=context,
                auto_document=True,
            )
            succeeded = result.get("status") in ("completed", "partially_completed")
            return {"success": succeeded, **result}

        get_workflow_scheduler().set_workflow_executor(_orchestration_executor)
        logger.info("[ 98%%] Scheduler: Orchestration executor wired")
    except Exception as e:
        logger.warning("Scheduler executor wiring failed (template-only fallback active): %s", e)


async def _start_community_clustering_loop(app: FastAPI) -> None:
    """Start a periodic CommunityClusterer background loop every 6 hours (#4834).

    Uses the MeshDB adapter stored on app.state.mesh_db by _init_graph_rag_service.
    NON-CRITICAL: clustering failures do not affect request handling.
    """
    mesh_db = getattr(app.state, "mesh_db", None)
    if mesh_db is None:
        logger.info("CommunityClusterer: mesh_db not available, skipping periodic loop")
        return

    from services.mesh_brain.community_clusterer import CommunityClusterer

    _CLUSTER_INTERVAL_SECONDS = 6 * 3600  # 6 hours

    async def _loop() -> None:
        # Allow startup to complete before first expensive Leiden pass
        await asyncio.sleep(300)  # 5 minutes
        while True:
            try:
                promoted = await CommunityClusterer(mesh_db).run()
                logger.info(
                    "CommunityClusterer periodic run: %d anchors promoted",
                    len(promoted),
                )
            except ImportError as exc:
                logger.warning(
                    "graspologic not installed — community clustering paused. "
                    "Install with: pip install graspologic. Retrying in 24h. Error: %s",
                    exc,
                )
                await asyncio.sleep(86400)  # 24 hours — re-check after potential install
                continue
            except Exception as exc:
                logger.warning("CommunityClusterer periodic run failed (non-fatal): %s", exc)
            await asyncio.sleep(_CLUSTER_INTERVAL_SECONDS)

    app.state.community_cluster_task = asyncio.create_task(_loop())
    logger.info(
        "CommunityClusterer: periodic loop started (interval=%dh)",
        _CLUSTER_INTERVAL_SECONDS // 3600,
    )


async def _init_liveness_monitor(app: FastAPI) -> None:
    """Start LLC LivenessMonitor to recover stuck heartbeat runs (GH#9028)."""
    logger.info("LLC LivenessMonitor: Starting...")
    try:
        from llc.scheduler.liveness_monitor import LivenessMonitor

        monitor = LivenessMonitor()
        monitor.start()
        app.state.llc_liveness_monitor = monitor
        logger.info("LLC LivenessMonitor: Started")
    except Exception as exc:
        logger.warning("LLC liveness monitor startup failed (non-fatal): %s", exc)
        app.state.llc_liveness_monitor = None


async def _init_budget_watchdog(app: FastAPI) -> None:
    """Start LLC BudgetWatchdog for per-agent budget enforcement (GH#9029)."""
    logger.info("LLC BudgetWatchdog: Starting...")
    try:
        from llc.scheduler.budget_watchdog import BudgetWatchdog

        watchdog = BudgetWatchdog()
        watchdog.start()
        app.state.llc_budget_watchdog = watchdog
        logger.info("LLC BudgetWatchdog: Started")
    except Exception as exc:
        logger.warning("LLC budget watchdog startup failed (non-fatal): %s", exc)
        app.state.llc_budget_watchdog = None


async def _recover_agent_sessions(app: FastAPI) -> None:
    """Re-queue runs that were interrupted by a previous server crash (GH#9026)."""
    logger.info("LLC SessionCheckpointer: recovering incomplete runs...")
    try:
        from llc.scheduler.session_checkpointer import recover_incomplete_runs

        await recover_incomplete_runs()
        logger.info("LLC SessionCheckpointer: recovery complete")
    except Exception as exc:
        logger.warning("LLC session recovery failed (non-fatal): %s", exc)


async def _init_session_checkpointer(app: FastAPI) -> None:
    """Start LLC SessionCheckpointer for periodic session state persistence (GH#9026)."""
    logger.info("LLC SessionCheckpointer: Starting...")
    try:
        from llc.scheduler.session_checkpointer import SessionCheckpointer

        checkpointer = SessionCheckpointer()
        checkpointer.start()
        app.state.llc_session_checkpointer = checkpointer
        logger.info("LLC SessionCheckpointer: Started")
    except Exception as exc:
        logger.warning("LLC session checkpointer startup failed (non-fatal): %s", exc)
        app.state.llc_session_checkpointer = None


async def _start_llc_notification_router(app: FastAPI) -> None:
    """Start the LLC notification router background task (GH#8255).

    Subscribes to llc:* Redis pub/sub patterns and fans out events to WebSocket
    clients filtered by company_id. NON-CRITICAL: failure logs a warning but
    does not block startup.
    """
    try:
        from llc.notifications.router import get_llc_notification_router

        router = get_llc_notification_router()
        await router.start()
        app.state.llc_notification_router = router
        logger.info("✅ LLC notification router started")
    except Exception as exc:
        logger.warning("LLC notification router failed to start (non-critical): %s", exc)
        app.state.llc_notification_router = None


async def _init_web_researcher(app: FastAPI) -> None:
    """Initialize the WebResearcher singleton so web browsing is available in chat.

    WebResearcher.enabled defaults to False and initialize() is never called
    lazily — without this Phase 2 step, every web research request silently fails.
    NON-CRITICAL: browser unavailability does not block other features.
    """
    logger.info("[ 99%%] WebResearcher: Initializing browser automation...")
    try:
        from agents.web_researcher import _load_web_research_config, get_web_researcher

        # Load stored config then enable — passing only {"enabled": True} would
        # discard all other settings (rate limits, timeouts, circuit breaker).
        config = _load_web_research_config()
        config["enabled"] = True
        researcher = get_web_researcher(config=config)
        await researcher.initialize()
        app.state.web_researcher = researcher
        logger.info("[ 99%%] WebResearcher: Browser automation ready")
    except Exception as e:
        logger.warning(
            "WebResearcher initialization failed (non-critical): %s — "
            "web browsing will be unavailable until the next restart",
            e,
        )
        app.state.web_researcher = None


async def _init_plugin_manager(app: FastAPI) -> None:
    """Discover and load plugins from the configured plugins directory.

    Issue #3278 - Plugin and extension system for third-party integrations.
    Non-critical: failures are logged and do not block startup.
    """
    try:
        from pathlib import Path

        from autobot_shared.plugin_sdk import PluginManager
        from autobot_shared.ssot_config import config as ssot_config

        plugins_root = ssot_config.path.plugins_path
        plugin_dirs = [
            plugins_root / "core-plugins",
            plugins_root / "community-plugins",
            # Development fallback
            Path("plugins/core-plugins"),
            Path("plugins/community-plugins"),
        ]

        plugin_manager = PluginManager(plugin_dirs)
        await plugin_manager.startup()
        app.state.plugin_manager = plugin_manager
        logger.info("PluginManager started — %s", plugin_manager.get_plugin_status())
    except Exception as pm_err:
        logger.warning("Plugin manager startup failed (non-critical): %s", pm_err, exc_info=True)


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
        await _warmup_npu_connection(app)
        await _init_memory_graph(app)
        await _init_slm_client()
        await _init_background_llm_sync(app)
        await _init_documentation_watcher()
        await _init_kb_folder_watcher()
        await _start_doc_sync_queue_worker(app)
        await _auto_index_documentation()
        await _init_log_forwarding()
        await _recover_agent_sessions(app)
        await _init_heartbeat_scheduler(app)
        await _init_llc_routine_scheduler(app)
        await _init_liveness_monitor(app)
        await _init_budget_watchdog(app)
        await _init_session_checkpointer(app)
        await _init_llc_outbound_sync(app)
        await _start_connector_scheduler()
        await _init_trigger_service(app)
        await _init_slm_reconciler(app)
        await _init_metrics_collection()
        await _recover_index_queue()
        await _ensure_agent_memory_index()
        await _init_process_adapter(app)
        await _init_orchestrator(app)
        await _seed_agent_registry()
        await _wire_npu_task_queue()
        await _wire_scheduler_executor()
        await _init_voice_interface(app)
        await _init_web_researcher(app)
        await _init_plugin_manager(app)
        await _init_backup_scheduler(app)
        await _init_llm_key_rotation_scheduler(app)
        await _start_autonomous_loop(app)
        await _start_community_clustering_loop(app)
        await _start_llc_notification_router(app)

        await update_app_state_multi(
            initialization_status="ready",
            initialization_message="All services initialized",
        )
        # GH#8947: Successful startup — remove the Phase 1 error file if it exists
        # from a previous failed boot attempt.
        try:
            STARTUP_ERROR_FILE.unlink(missing_ok=True)
        except Exception:
            pass
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
        # GH#9044: Close transcriber DB connection
        transcriber_db = getattr(app.state, "transcriber_db", None)
        if transcriber_db is not None:
            await transcriber_db.close()
            logger.info("Transcriber DB closed")

        if hasattr(app.state, "background_llm_sync") and app.state.background_llm_sync:
            await app.state.background_llm_sync.stop()
        if hasattr(app.state, "memory_graph") and app.state.memory_graph:
            await app.state.memory_graph.close()

        # Issue #3100: Stop trigger service background loops
        if hasattr(app.state, "trigger_service") and app.state.trigger_service:
            await app.state.trigger_service.stop()
            logger.info("Trigger service stopped")

        # Issue #6556: Stop connector scheduler local tasks
        try:
            from knowledge.connectors.scheduler import get_connector_scheduler

            await get_connector_scheduler().stop_all()
            logger.info("Connector scheduler stopped")
        except Exception as _cs_err:
            logger.warning("Connector scheduler shutdown failed: %s", _cs_err)

        # Issue #8391: Stop VectorWriteBuffer (flushes pending writes).
        kb = getattr(app.state, "knowledge_base", None)
        if kb is not None:
            write_buffer = getattr(kb, "_write_buffer", None)
            if write_buffer is not None:
                await write_buffer.stop()

        # Issue #8392: Stop CollectionTierManager reaper.
        tier_manager = getattr(app.state, "tier_manager", None)
        if tier_manager is not None:
            await tier_manager.stop()

        # Issue #165: Stop documentation watcher
        try:
            from services.documentation_watcher import stop_documentation_watcher

            await stop_documentation_watcher()
        except ImportError:
            pass  # Watcher not available

        # Issue #9000: Stop KB folder watcher
        try:
            from services.kb_folder_watcher import stop_kb_folder_watcher

            await stop_kb_folder_watcher()
            logger.info("✅ KB folder watcher stopped")
        except ImportError:
            pass  # Watcher not available
        except Exception as kb_watcher_error:
            logger.warning("KB folder watcher shutdown failed: %s", kb_watcher_error)

        # Issue #4453: Stop doc sync queue worker
        worker = getattr(app.state, "doc_sync_queue_worker", None)
        task = getattr(app.state, "doc_sync_queue_worker_task", None)
        if worker is not None:
            worker.stop()
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

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

        # GH#9028: Stop LLC liveness monitor
        if hasattr(app.state, "llc_liveness_monitor") and app.state.llc_liveness_monitor:
            app.state.llc_liveness_monitor.stop()
            logger.info("✅ LLC liveness monitor stopped")
        # GH#9029: Stop LLC budget watchdog
        if hasattr(app.state, "llc_budget_watchdog") and app.state.llc_budget_watchdog:
            app.state.llc_budget_watchdog.stop()
            logger.info("✅ LLC budget watchdog stopped")
        # GH#9026: Stop LLC session checkpointer
        if hasattr(app.state, "llc_session_checkpointer") and app.state.llc_session_checkpointer:
            app.state.llc_session_checkpointer.stop()
            logger.info("✅ LLC session checkpointer stopped")

        # GH#8257: Stop LLC outbound sync service
        if hasattr(app.state, "llc_outbound_sync") and app.state.llc_outbound_sync:
            await app.state.llc_outbound_sync.stop()
            logger.info("✅ LLC outbound sync service stopped")
        # GH#8255: Stop LLC notification router
        if hasattr(app.state, "llc_notification_router") and app.state.llc_notification_router:
            await app.state.llc_notification_router.stop()
            logger.info("✅ LLC notification router stopped")

        # GH#8651: Drain HandoffService background brief-generation tasks
        try:
            from llc.api.work_items import _get_handoff_service

            handoff_svc = _get_handoff_service()
            await handoff_svc.shutdown()
            logger.info("✅ LLC HandoffService background tasks drained")
        except Exception as _hs_err:
            logger.warning("HandoffService drain failed: %s", _hs_err)

        # GH#8229: Stop LLC routine scheduler
        if hasattr(app.state, "llc_routine_scheduler") and app.state.llc_routine_scheduler:
            await app.state.llc_routine_scheduler.shutdown()
            logger.info("✅ LLC routine scheduler stopped")

        # GH#8225: Stop LLC heartbeat scheduler before other schedulers
        if hasattr(app.state, "heartbeat_scheduler") and app.state.heartbeat_scheduler:
            await app.state.heartbeat_scheduler.stop()
            logger.info("✅ LLC heartbeat scheduler stopped")

        # Issue #3294: Stop backup scheduler
        if hasattr(app.state, "backup_scheduler") and app.state.backup_scheduler:
            await app.state.backup_scheduler.stop()
            logger.info("✅ Backup scheduler stopped")

        # Issue #6590: Stop LLM key rotation scheduler
        if hasattr(app.state, "llm_key_rotation_scheduler") and app.state.llm_key_rotation_scheduler:
            await app.state.llm_key_rotation_scheduler.stop()
            logger.info("✅ LLM key rotation scheduler stopped")

        # Issue #4946: Cancel community clustering background task
        task = getattr(app.state, "community_cluster_task", None)
        if task and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            logger.info("✅ Community cluster task cancelled")

        # Issue #1748: Stop process adapter dispatcher
        if hasattr(app.state, "process_adapter_service") and app.state.process_adapter_service:
            await app.state.process_adapter_service.stop()
            logger.info("✅ Process adapter stopped")

        # Issue #1233: Shutdown dedicated I/O thread pools
        shutdown_io_executors()

        # Issue #697: Flush and shutdown OpenTelemetry tracing
        await shutdown_tracing()

        # Issue #3278: Shutdown plugin manager
        try:
            if hasattr(app.state, "plugin_manager") and app.state.plugin_manager:
                await app.state.plugin_manager.shutdown()
                logger.info("✅ Plugin manager shutdown")
        except Exception as pm_err:
            logger.warning("Plugin manager shutdown failed: %s", pm_err)

        # Issue #4107: Stop isolated MCP bridge worker processes
        try:
            from services.mcp_isolated_runtime import get_isolated_registry

            await get_isolated_registry().shutdown_all()
            logger.info("✅ Isolated MCP bridge workers shutdown")
        except Exception as mcp_err:
            logger.warning("Isolated MCP bridge shutdown failed: %s", mcp_err)

        # GH#9012: Flush LangFuse / LangSmith observer buffers before exit
        try:
            from llm_shared.observability.registry import _registry

            for _obs in _registry:
                if callable(getattr(_obs, "flush", None)):
                    _obs.flush()
            logger.info("✅ LLM observer buffers flushed")
        except Exception as obs_err:
            logger.warning("LLM observer flush failed: %s", obs_err)

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
        warn_if_dev_auth_bypass_enabled()

        # Create bounded thread pool executor to prevent thread explosion
        # This replaces the default unbounded asyncio executor
        _executor = ThreadPoolExecutor(max_workers=MAX_WORKER_THREADS, thread_name_prefix="autobot_worker")
        loop = asyncio.get_running_loop()
        loop.set_default_executor(_executor)
        logger.info("🧵 Bounded thread pool configured (max %d workers)", MAX_WORKER_THREADS)

        # Register the running event loop for sync-endpoint audit scheduling (#1568)
        from middleware.audit_middleware import set_main_event_loop

        set_main_event_loop(asyncio.get_running_loop())

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
