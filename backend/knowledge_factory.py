"""Knowledge Base Factory - Breaks circular import between api/knowledge.py and app_factory.py"""

import logging
from typing import Optional

from fastapi import FastAPI

from src.constants.network_constants import NetworkConstants

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
                # Knowledge base exists but not initialized - initialize it instead of creating new one
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

        # MANDATORY: Use KnowledgeBaseV2 (ChromaDB-based implementation)
        # No fallback to old KnowledgeBase class - V2 is required for vector store migration
        try:
            from src.knowledge_base_v2 import KnowledgeBaseV2

            logger.info("Creating KnowledgeBaseV2 with ChromaDB vector store...")
            kb = KnowledgeBaseV2()

            logger.info("Initializing KnowledgeBaseV2...")
            result = await kb.initialize()

            if result:
                app.state.knowledge_base = kb
                logger.info("✅ Knowledge base created and initialized (KnowledgeBaseV2 with ChromaDB)")
                return kb
            else:
                logger.error("❌ KnowledgeBaseV2 initialization returned False")
                return None

        except ImportError as import_error:
            logger.error(f"❌ CRITICAL: KnowledgeBaseV2 not available: {import_error}")
            import traceback
            logger.error(f"Import traceback:\n{traceback.format_exc()}")
            return None
        except Exception as v2_error:
            logger.error(f"❌ CRITICAL: KnowledgeBaseV2 initialization failed: {v2_error}")
            import traceback
            logger.error(f"Full traceback:\n{traceback.format_exc()}")
            return None

    except Exception as e:
        logger.error(f"❌ Failed to get or create knowledge base: {e}")
        return None
