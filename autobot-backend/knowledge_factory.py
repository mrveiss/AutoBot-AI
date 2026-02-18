# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Knowledge Base Factory - Breaks circular import between api/knowledge.py and app_factory.py"""

import asyncio
import logging
from typing import Optional

from fastapi import FastAPI

logger = logging.getLogger(__name__)

# Module-level singleton for knowledge base instance (used when no app context available)
_knowledge_base_instance: Optional["KnowledgeBase"] = None  # noqa: F821
_knowledge_base_lock = asyncio.Lock()


def _is_kb_initialized(kb) -> bool:
    """Check if knowledge base instance is properly initialized (Issue #315: extracted)."""
    if hasattr(kb, "initialized") and kb.initialized:
        return True
    if hasattr(kb, "_redis_initialized") and kb._redis_initialized:
        return True
    return False


def _log_kb_state(kb) -> None:
    """Log knowledge base state for debugging (Issue #315: extracted)."""
    logger.debug(
        f"Checking app.state.knowledge_base: initialized={getattr(kb, 'initialized', 'N/A')}, "
        f"_redis_initialized={getattr(kb, '_redis_initialized', 'N/A')}, "
        f"vector_store={kb.vector_store is not None if hasattr(kb, 'vector_store') else 'N/A'}, "
        f"llama_index_configured={getattr(kb, 'llama_index_configured', 'N/A')}"
    )


async def _try_initialize_existing_kb(kb):
    """Try to initialize an existing but uninitialized knowledge base (Issue #315: extracted).

    Returns:
        Initialized kb on success, None on failure
    """
    logger.info(
        "Knowledge base exists but not initialized, initializing existing instance..."
    )
    try:
        await kb.initialize()
        logger.info("✅ Successfully initialized existing knowledge base instance")
        return kb
    except Exception as init_error:
        logger.warning(
            f"Failed to initialize existing instance: {init_error}, will create new instance"
        )
        return None


async def _create_new_knowledge_base(app: FastAPI):
    """Create and initialize a new knowledge base (Issue #315: extracted).

    Returns:
        Initialized kb on success, None on failure
    """
    import traceback

    try:
        from knowledge_base import KnowledgeBase

        logger.info("Creating KnowledgeBase with ChromaDB vector store...")
        kb = KnowledgeBase()

        logger.info("Initializing KnowledgeBase...")
        result = await kb.initialize()

        if result:
            app.state.knowledge_base = kb
            logger.info(
                "✅ Knowledge base created and initialized (unified KnowledgeBase with ChromaDB)"
            )
            return kb

        logger.error("❌ KnowledgeBase initialization returned False")
        return None

    except ImportError as import_error:
        logger.error("❌ CRITICAL: KnowledgeBase not available: %s", import_error)
        logger.error("Import traceback:\n%s", traceback.format_exc())
        return None
    except Exception as init_error:
        logger.error(f"❌ CRITICAL: KnowledgeBase initialization failed: {init_error}")
        logger.error("Full traceback:\n%s", traceback.format_exc())
        return None


async def get_or_create_knowledge_base(app: FastAPI, force_refresh: bool = False):
    """Get or create a properly initialized knowledge base instance for the app.

    This is separated from app_factory to avoid circular imports with api/knowledge.py

    Issue #315: Refactored to use helper functions for reduced nesting depth.
    """
    try:
        # Check for existing initialized knowledge base
        has_existing = (
            hasattr(app.state, "knowledge_base")
            and app.state.knowledge_base is not None
            and not force_refresh
        )

        if has_existing:
            kb = app.state.knowledge_base
            _log_kb_state(kb)

            if _is_kb_initialized(kb):
                logger.info("Using existing initialized knowledge base from app state")
                return kb

            # Try to initialize existing uninitialized instance
            result = await _try_initialize_existing_kb(kb)
            if result is not None:
                return result
            # Fall through to create new instance

        # Create new knowledge base
        return await _create_new_knowledge_base(app)

    except Exception as e:
        logger.error("❌ Failed to get or create knowledge base: %s", e)
        return None


async def get_knowledge_base_async() -> Optional["KnowledgeBase"]:  # noqa: F821
    """
    Get or create a knowledge base instance without requiring FastAPI app context (thread-safe).

    Uses a module-level singleton for cases where we don't have app access
    (e.g., ChatWorkflowManager initialization).

    Returns:
        KnowledgeBase instance or None if initialization fails
    """
    global _knowledge_base_instance

    try:
        # Return existing instance if already initialized
        if _knowledge_base_instance is not None:
            if (
                hasattr(_knowledge_base_instance, "initialized")
                and _knowledge_base_instance.initialized
            ):
                logger.debug("Using existing knowledge base singleton")
                return _knowledge_base_instance

        # Use lock for thread-safe initialization
        async with _knowledge_base_lock:
            # Double-check after acquiring lock
            if _knowledge_base_instance is not None:
                if (
                    hasattr(_knowledge_base_instance, "initialized")
                    and _knowledge_base_instance.initialized
                ):
                    logger.debug("Using existing knowledge base singleton (after lock)")
                    return _knowledge_base_instance

            # Create new instance
            from knowledge_base import KnowledgeBase

            logger.info("Creating KnowledgeBase singleton (no app context)...")
            kb = KnowledgeBase()

            logger.info("Initializing KnowledgeBase singleton...")
            result = await kb.initialize()

            if result:
                _knowledge_base_instance = kb
                logger.info("✅ Knowledge base singleton created and initialized")
                return kb
            else:
                logger.error("❌ KnowledgeBase singleton initialization returned False")
                return None

    except ImportError as import_error:
        logger.error("❌ KnowledgeBase not available: %s", import_error)
        return None
    except Exception as e:
        logger.error("❌ Failed to create knowledge base singleton: %s", e)
        return None
