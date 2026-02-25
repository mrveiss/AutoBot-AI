# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Knowledge Base Factory - Async Factory Pattern Implementation

This module fixes the race condition issues in knowledge base initialization
by implementing a proper async factory pattern with initialization locks.

Key Features:
- Async factory pattern prevents race conditions
- Initialization locks ensure single initialization
- Proper error handling and fallbacks
- Thread-safe singleton pattern
- Configuration integration with unified config

Usage:
    from knowledge_base_factory import get_knowledge_base

    # Async context
    kb = await get_knowledge_base()

    # Sync context (uses thread pool)
    kb = await asyncio.to_thread(get_knowledge_base_sync)
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, Dict, Optional

from config import ConfigManager
from constants.threshold_constants import TimingConstants

if TYPE_CHECKING:
    from knowledge_base import KnowledgeBase

logger = logging.getLogger(__name__)

# Create singleton config instance
config = ConfigManager()


class KnowledgeBaseInitializer:
    """Thread-safe knowledge base initializer with async factory pattern"""

    _instance: Optional["KnowledgeBase"] = None
    _initialization_lock = asyncio.Lock()
    _initialization_complete = asyncio.Event()
    _initialization_failed = False
    _initialization_error: Optional[Exception] = None

    @classmethod
    async def get_instance(
        cls, force_reinit: bool = False
    ) -> Optional["KnowledgeBase"]:
        """Get or create knowledge base instance with proper async initialization"""

        # If we already have an instance and don't need to reinitialize
        if cls._instance is not None and not force_reinit:
            return cls._instance

        # If initialization failed before and we're not forcing reinit
        if cls._initialization_failed and not force_reinit:
            logger.warning(
                f"Knowledge base initialization previously failed: {cls._initialization_error}"
            )
            return None

        async with cls._initialization_lock:
            # Double-check after acquiring lock
            if cls._instance is not None and not force_reinit:
                return cls._instance

            # Reset initialization state if forcing reinit
            if force_reinit:
                cls._initialization_complete.clear()
                cls._initialization_failed = False
                cls._initialization_error = None
                cls._instance = None

            try:
                logger.info("Initializing knowledge base with async factory pattern...")

                # Import here to avoid circular dependencies
                from knowledge_base import KnowledgeBase

                # Create instance with async initialization
                cls._instance = KnowledgeBase()
                await cls._instance.initialize()

                cls._initialization_complete.set()
                cls._initialization_failed = False

                logger.info("Knowledge base initialized successfully")
                return cls._instance

            except Exception as e:
                logger.error("Knowledge base initialization failed: %s", e)
                cls._initialization_failed = True
                cls._initialization_error = e
                cls._instance = None
                cls._initialization_complete.set()  # Set event even on failure
                return None

    @classmethod
    async def wait_for_initialization(
        cls, timeout: float = TimingConstants.SHORT_TIMEOUT
    ) -> Optional["KnowledgeBase"]:
        """Wait for initialization to complete with timeout"""
        try:
            await asyncio.wait_for(cls._initialization_complete.wait(), timeout=timeout)
            return cls._instance
        except asyncio.TimeoutError:
            logger.warning("Knowledge base initialization timed out after %ss", timeout)
            return None

    @classmethod
    def is_initialized(cls) -> bool:
        """Check if knowledge base is initialized"""
        return cls._instance is not None and cls._initialization_complete.is_set()

    @classmethod
    def get_initialization_status(cls) -> Dict[str, Any]:
        """Get detailed initialization status"""
        return {
            "initialized": cls.is_initialized(),
            "failed": cls._initialization_failed,
            "error": (
                str(cls._initialization_error) if cls._initialization_error else None
            ),
            "instance_exists": cls._instance is not None,
        }


# Convenience functions for easy access
async def get_knowledge_base(
    force_reinit: bool = False, timeout: float = TimingConstants.SHORT_TIMEOUT
) -> Optional["KnowledgeBase"]:
    """Get knowledge base instance with async initialization"""
    try:
        # Try to get existing instance first
        instance = await KnowledgeBaseInitializer.get_instance(force_reinit)

        if instance is None and not force_reinit:
            # If no instance and not forcing reinit, wait for ongoing initialization
            instance = await KnowledgeBaseInitializer.wait_for_initialization(timeout)

        return instance

    except Exception as e:
        logger.error("Failed to get knowledge base: %s", e)
        return None


def get_knowledge_base_sync() -> Optional["KnowledgeBase"]:
    """Synchronous wrapper for getting knowledge base (uses existing instance only)"""
    if KnowledgeBaseInitializer.is_initialized():
        return KnowledgeBaseInitializer._instance
    else:
        logger.warning(
            "Knowledge base not initialized - use async get_knowledge_base() for initialization"
        )
        return None


@asynccontextmanager
async def knowledge_base_context(timeout: float = TimingConstants.SHORT_TIMEOUT):
    """Async context manager for knowledge base operations"""
    kb = None
    try:
        kb = await get_knowledge_base(timeout=timeout)
        if kb is None:
            raise RuntimeError("Failed to initialize knowledge base")
        yield kb
    except Exception as e:
        logger.error("Knowledge base context error: %s", e)
        raise
    finally:
        # Cleanup could be added here if needed
        pass


# Background initialization function
async def initialize_knowledge_base_background():
    """Initialize knowledge base in background without blocking"""
    try:
        logger.info("Starting background knowledge base initialization...")
        await get_knowledge_base()
        logger.info("Background knowledge base initialization completed")
    except Exception as e:
        logger.error("Background knowledge base initialization failed: %s", e)


def start_background_initialization():
    """Start background initialization (non-blocking)"""
    try:
        # Create task without awaiting it
        task = asyncio.create_task(initialize_knowledge_base_background())
        logger.info("Knowledge base background initialization task created")
        return task
    except Exception as e:
        logger.error("Failed to start background initialization: %s", e)
        return None


# Health check functions
async def health_check() -> Dict[str, Any]:
    """Comprehensive health check for knowledge base"""
    status = KnowledgeBaseInitializer.get_initialization_status()

    if status["initialized"]:
        try:
            kb = KnowledgeBaseInitializer._instance
            # Test basic operations
            redis_status = (
                await kb.ping_redis() if hasattr(kb, "ping_redis") else "unknown"
            )
            vector_store_status = "healthy" if kb.vector_store else "unavailable"

            status.update(
                {
                    "redis_connection": redis_status,
                    "vector_store": vector_store_status,
                    "health": "healthy",
                }
            )
        except Exception as e:
            status.update({"health": "unhealthy", "health_error": str(e)})
    else:
        status["health"] = "not_initialized"

    return status


# Export main functions
__all__ = [
    "get_knowledge_base",
    "get_knowledge_base_sync",
    "knowledge_base_context",
    "initialize_knowledge_base_background",
    "start_background_initialization",
    "health_check",
    "KnowledgeBaseInitializer",
]
