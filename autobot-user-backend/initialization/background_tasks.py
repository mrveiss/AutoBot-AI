# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Background Tasks Initialization Module

This module handles all background initialization tasks for the AutoBot backend,
including Redis, knowledge base, chat workflow, LLM sync, AI Stack, and distributed tracing.
"""

import asyncio

from chat_workflow import ChatWorkflowManager
from fastapi import FastAPI

from autobot_shared.logging_manager import get_logger
from backend.initialization.ai_stack_init import initialize_ai_stack
from backend.utils.background_llm_sync import background_llm_sync

logger = get_logger(__name__, "backend")


def log_initialization_step(
    stage: str, message: str, percentage: int = 0, success: bool = True
):
    """Log initialization steps with consistent formatting."""
    icon = "✅" if success else "❌" if percentage == 100 else "🔄"
    logger.info(f"{icon} [{percentage:3d}%] {stage}: {message}")


async def get_or_create_knowledge_base(app: FastAPI, force_refresh: bool = False):
    """
    Get or create a properly initialized knowledge base instance for the app.
    Enhanced with AI Stack integration awareness.
    """
    from backend.knowledge_factory import get_or_create_knowledge_base as factory_kb

    # Import status functions from parent module (will be passed as parameters)
    try:
        kb = await factory_kb(app, force_refresh)
        return kb
    except Exception as e:
        logger.error("Knowledge base initialization error: %s", e)
        return None


async def _init_redis(update_status_fn, append_error_fn):
    """
    Initialize Redis status using centralized client management.

    Issue #281: Extracted helper for Redis initialization.

    Args:
        update_status_fn: Function to update initialization status
        append_error_fn: Function to append initialization errors
    """
    try:
        # Mark Redis as ready - no initialization needed with centralized client
        # Components will call get_redis_client() directly when they need Redis
        await update_status_fn("redis_pools", "ready")
        log_initialization_step(
            "Redis",
            "Using centralized Redis client management (src.utils.redis_client)",
            90,
            True,
        )
    except Exception as e:
        logger.error("Redis status check failed: %s", e)
        await update_status_fn("redis_pools", "failed")
        await append_error_fn(f"Redis: {str(e)}")


async def _init_knowledge_base(
    app: FastAPI, update_status_fn, append_error_fn, get_status_fn
):
    """
    Initialize knowledge base with optional AI Stack integration.

    Issue #281: Extracted helper for knowledge base initialization.

    Args:
        app: FastAPI application instance
        update_status_fn: Function to update initialization status
        append_error_fn: Function to append initialization errors
        get_status_fn: Function to get initialization status
    """
    kb = await get_or_create_knowledge_base(app, force_refresh=False)
    if kb:
        app.state.knowledge_base = kb
        await update_status_fn("knowledge_base", "ready")
        log_initialization_step("Knowledge Base", "Knowledge base ready", 90, True)

        # Enhanced: Check if AI Stack integration is available
        ai_stack_status = await get_status_fn("ai_stack")
        if hasattr(app.state, "ai_stack_client") and ai_stack_status == "ready":
            logger.info(
                "Knowledge Base initialized with AI Stack enhancement available"
            )
        else:
            logger.info("Knowledge Base initialized in standalone mode")
    else:
        await update_status_fn("knowledge_base", "failed")
        await append_error_fn("KB init: Failed to create knowledge base")
        logger.error("Knowledge base initialization failed")


async def _init_chat_workflow(app: FastAPI, update_status_fn, append_error_fn):
    """
    Initialize chat workflow manager for conversation handling.

    Issue #281: Extracted helper for chat workflow initialization.

    Args:
        app: FastAPI application instance
        update_status_fn: Function to update initialization status
        append_error_fn: Function to append initialization errors
    """
    try:
        workflow_manager = ChatWorkflowManager()
        app.state.chat_workflow_manager = workflow_manager
        await update_status_fn("chat_workflow", "ready")
        log_initialization_step(
            "Chat Workflow", "Chat workflow manager initialized", 90, True
        )
    except Exception as e:
        logger.error("Chat workflow initialization failed: %s", e)
        await update_status_fn("chat_workflow", "failed")
        await append_error_fn(f"Chat workflow: {str(e)}")


async def _init_llm_sync(update_status_fn, append_error_fn):
    """
    Initialize background LLM synchronization.

    Issue #281: Extracted helper for LLM sync initialization.

    Args:
        update_status_fn: Function to update initialization status
        append_error_fn: Function to append initialization errors
    """
    try:
        await background_llm_sync()
        await update_status_fn("llm_sync", "ready")
        log_initialization_step("LLM Sync", "LLM synchronization completed", 90, True)
    except Exception as e:
        logger.error("LLM sync failed: %s", e)
        await update_status_fn("llm_sync", "failed")
        await append_error_fn(f"LLM sync: {str(e)}")


async def _init_distributed_tracing(app: FastAPI, update_status_fn):
    """
    Initialize OpenTelemetry distributed tracing with Jaeger export.

    Issue #281: Extracted helper for distributed tracing initialization.
    Issue #697: Enhanced with Redis, aiohttp instrumentation and sampling.

    Args:
        app: FastAPI application instance
        update_status_fn: Function to update initialization status
    """
    try:
        # Lazy import to avoid circular dependency
        from backend.services.tracing_service import get_tracing_service

        tracing = get_tracing_service()
        success = tracing.initialize(
            service_name="autobot-backend",
            service_version="2.0.0",
            enable_console_export=False,  # Set True for debugging
        )
        if success:
            # Issue #697: Instrument all supported libraries (FastAPI, Redis, aiohttp)
            results = tracing.instrument_all(app)
            instrumented = [k for k, v in results.items() if v]
            await update_status_fn("distributed_tracing", "ready")
            log_initialization_step(
                "Distributed Tracing",
                f"OpenTelemetry initialized ({', '.join(instrumented)})",
                90,
                True,
            )
        else:
            await update_status_fn("distributed_tracing", "disabled")
            log_initialization_step(
                "Distributed Tracing",
                "Tracing disabled (Jaeger not available)",
                90,
                True,
            )
    except Exception as e:
        logger.warning("Distributed tracing initialization failed: %s", e)
        await update_status_fn("distributed_tracing", "failed")
        # Don't add to errors - tracing is optional
        log_initialization_step(
            "Distributed Tracing", f"Tracing unavailable: {e}", 90, False
        )


def _log_initialization_result(failed_services: list):
    """
    Log the final initialization result.

    Issue #281: Extracted helper for result logging.

    Args:
        failed_services: List of services that failed to initialize
    """
    if failed_services:
        log_initialization_step(
            "Background Init",
            f"Completed with {len(failed_services)} failed services: {', '.join(failed_services)}",
            100,
            False,
        )
    else:
        log_initialization_step(
            "Background Init", "All services initialized successfully", 100, True
        )


async def enhanced_background_init(
    app: FastAPI, update_status_fn, append_error_fn, get_status_fn
):
    """
    Enhanced background initialization with AI Stack integration.

    Issue #281: Refactored from 174 lines to use extracted helper methods.

    Args:
        app: FastAPI application instance
        update_status_fn: Function to update initialization status
        append_error_fn: Function to append initialization errors
        get_status_fn: Function to get initialization status
    """
    try:
        log_initialization_step(
            "Background Init", "Starting enhanced background initialization...", 0
        )

        # Run all initialization tasks concurrently (Issue #281: uses helpers)
        tasks = [
            _init_redis(update_status_fn, append_error_fn),
            _init_knowledge_base(app, update_status_fn, append_error_fn, get_status_fn),
            _init_chat_workflow(app, update_status_fn, append_error_fn),
            _init_llm_sync(update_status_fn, append_error_fn),
            initialize_ai_stack(app, update_status_fn, append_error_fn),
            _init_distributed_tracing(app, update_status_fn),
        ]

        await asyncio.gather(*tasks, return_exceptions=True)

        # Check overall initialization status (thread-safe)
        init_status_snapshot = await get_status_fn()
        failed_services = [
            service
            for service, status in init_status_snapshot.items()
            if status == "failed" and service != "errors"
        ]

        # Log result (Issue #281: uses helper)
        _log_initialization_result(failed_services)

    except Exception as e:
        logger.error("Background initialization failed: %s", e)
        await append_error_fn(f"Background init: {str(e)}")
