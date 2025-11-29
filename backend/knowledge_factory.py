# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Knowledge Base Factory - Breaks circular import between api/knowledge.py and app_factory.py"""

import logging
from typing import Optional

from fastapi import FastAPI


logger = logging.getLogger(__name__)

# Module-level singleton for knowledge base instance (used when no app context available)
_knowledge_base_instance: Optional["KnowledgeBase"] = None  # noqa: F821


async def get_or_create_knowledge_base(app: FastAPI, force_refresh: bool = False):
    """
    Get or create a properly initialized knowledge base instance for the app.

    This is separated from app_factory to avoid circular imports with api/knowledge.py
    """
    try:
        # Check if we already have an initialized knowledge base
        if (
            hasattr(app.state, "knowledge_base")
            and app.state.knowledge_base is not None
            and not force_refresh
        ):
            # Verify it's actually initialized by checking if Redis connections exist
            kb = app.state.knowledge_base
            if hasattr(kb, "initialized") and kb.initialized:
                logger.info("Using existing initialized knowledge base from app state")
                return kb
            elif hasattr(kb, "_redis_initialized") and kb._redis_initialized:
                logger.info("Using existing initialized knowledge base from app state")
                return kb
            else:
                # Knowledge base exists but not initialized - initialize it instead of creating new
                # one
                logger.info(
                    "Knowledge base exists but not initialized, initializing existing instance..."
                )
                try:
                    await kb.initialize()
                    logger.info(
                        "✅ Successfully initialized existing knowledge base instance"
                    )
                    return kb
                except Exception as init_error:
                    logger.warning(
                        f"Failed to initialize existing instance: {init_error}, will create new instance"
                    )
                    # Fall through to create new instance

        # Use unified KnowledgeBase class (ChromaDB-based implementation)
        # This is the merged implementation combining V1 and V2 functionality
        try:
            from src.knowledge_base import KnowledgeBase

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
            else:
                logger.error("❌ KnowledgeBase initialization returned False")
                return None

        except ImportError as import_error:
            logger.error(f"❌ CRITICAL: KnowledgeBase not available: {import_error}")
            import traceback

            logger.error(f"Import traceback:\n{traceback.format_exc()}")
            return None
        except Exception as init_error:
            logger.error(
                f"❌ CRITICAL: KnowledgeBase initialization failed: {init_error}"
            )
            import traceback

            logger.error(f"Full traceback:\n{traceback.format_exc()}")
            return None

    except Exception as e:
        logger.error(f"❌ Failed to get or create knowledge base: {e}")
        return None


async def get_knowledge_base_async() -> Optional["KnowledgeBase"]:  # noqa: F821
    """
    Get or create a knowledge base instance without requiring FastAPI app context.

    Uses a module-level singleton for cases where we don't have app access
    (e.g., ChatWorkflowManager initialization).

    Returns:
        KnowledgeBase instance or None if initialization fails
    """
    global _knowledge_base_instance

    try:
        # Return existing instance if already initialized
        if _knowledge_base_instance is not None:
            if hasattr(_knowledge_base_instance, "initialized") and _knowledge_base_instance.initialized:
                logger.debug("Using existing knowledge base singleton")
                return _knowledge_base_instance

        # Create new instance
        from src.knowledge_base import KnowledgeBase

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
        logger.error(f"❌ KnowledgeBase not available: {import_error}")
        return None
    except Exception as e:
        logger.error(f"❌ Failed to create knowledge base singleton: {e}")
        return None
