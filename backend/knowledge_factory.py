# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Knowledge Base Factory - Breaks circular import between api/knowledge.py and app_factory.py"""

import logging

from fastapi import FastAPI


logger = logging.getLogger(__name__)


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
