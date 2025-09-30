"""Knowledge Base Factory - Breaks circular import between api/knowledge.py and app_factory.py"""

import logging
from typing import Optional
from fastapi import FastAPI

logger = logging.getLogger(__name__)

async def get_or_create_knowledge_base(app: FastAPI, force_refresh: bool = False):
    """
    Get or create a properly initialized knowledge base instance for the app.

    This is separated from app_factory to avoid circular imports with api/knowledge.py
    """
    try:
        # Check if we already have an initialized knowledge base
        if hasattr(app.state, 'knowledge_base') and app.state.knowledge_base is not None and not force_refresh:
            # Verify it's actually initialized by checking if Redis connections exist
            kb = app.state.knowledge_base
            if hasattr(kb, 'initialized') and kb.initialized:
                logger.info("Using existing initialized knowledge base from app state")
                return kb
            elif hasattr(kb, '_redis_initialized') and kb._redis_initialized:
                logger.info("Using existing initialized knowledge base from app state")
                return kb
            else:
                logger.warning("Knowledge base exists but not initialized, will initialize now")

        # Try using KnowledgeBaseV2 first (preferred async implementation)
        try:
            from src.knowledge_base_v2 import KnowledgeBaseV2
            kb = KnowledgeBaseV2()
            await kb.initialize()
            app.state.knowledge_base = kb
            logger.info("✅ Knowledge base created and initialized (KnowledgeBaseV2)")
            return kb
        except ImportError:
            logger.info("KnowledgeBaseV2 not available, using standard KnowledgeBase")
        except Exception as v2_error:
            logger.warning(f"KnowledgeBaseV2 initialization failed: {v2_error}, trying standard KnowledgeBase")

        # Final fallback: Use standard KnowledgeBase with manual async initialization
        from src.knowledge_base import KnowledgeBase
        logger.info("Creating standard KnowledgeBase with async initialization...")
        kb = KnowledgeBase()

        # CRITICAL: Manually call the async initialization that the constructor skips
        await kb._ensure_redis_initialized()

        # Verify initialization worked
        if hasattr(kb, 'redis_client') and kb.redis_client is not None:
            app.state.knowledge_base = kb
            logger.info("✅ Knowledge base created and initialized (standard KnowledgeBase)")
            return kb
        else:
            logger.error("❌ Knowledge base initialization failed - Redis client is None")
            return None

    except Exception as e:
        logger.error(f"❌ Failed to get or create knowledge base: {e}")
        return None