# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
DEPRECATED: This module redirects to advanced_cache_manager.py

All functionality has been consolidated into src.utils.advanced_cache_manager.
This file exists only for backward compatibility.

Migration Status: Phase 4 Cache Consolidation (2025-11-11)
Expected Removal: After verification period (2025-12-01)
Archived: archives/2025-11-11_cache_consolidation/knowledge_cache.py

Usage:
    # Old import (deprecated but still works):
    from utils.knowledge_cache import get_knowledge_cache

    # New recommended import:
    from utils.advanced_cache_manager import get_knowledge_cache

All methods are preserved with identical signatures.
"""

import warnings

# Emit deprecation warning
warnings.warn(
    "src.utils.knowledge_cache is deprecated. "
    "Use src.utils.advanced_cache_manager instead. "
    "This compatibility shim will be removed in future version.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export everything from advanced_cache_manager for backward compatibility
from utils.advanced_cache_manager import (
    cache_knowledge_results,
    clear_knowledge_cache,
    get_cached_knowledge_results,
    get_knowledge_cache,
    get_knowledge_cache_stats,
)

# Legacy class wrapper (for direct instantiation compatibility)


def KnowledgeCache():
    """Legacy wrapper for backward compatibility."""
    return get_knowledge_cache()


__all__ = [
    "get_knowledge_cache",
    "get_cached_knowledge_results",
    "cache_knowledge_results",
    "clear_knowledge_cache",
    "get_knowledge_cache_stats",
    "KnowledgeCache",
]
