# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Knowledge Base - Backward Compatibility Wrapper

This module provides backward compatibility for code importing from knowledge_base.
The actual implementation has been refactored into src/knowledge/ for better maintainability.

All imports from this module are re-exported from the modular implementation.

For new code, prefer importing directly from knowledge:
    from knowledge import KnowledgeBase, get_knowledge_base
"""

# Re-export everything from the modular implementation
from knowledge import (
    KnowledgeBase,
    get_knowledge_base,
)
from knowledge.embedding_cache import (
    EmbeddingCache,
    get_embedding_cache,
)
from knowledge.utils import (
    sanitize_metadata_for_chromadb as _sanitize_metadata_for_chromadb,
)

# Public exports
__all__ = [
    "KnowledgeBase",
    "get_knowledge_base",
    "EmbeddingCache",
    "get_embedding_cache",
    "_sanitize_metadata_for_chromadb",
]


def __getattr__(name: str):
    """Provide helpful deprecation warnings for direct attribute access."""
    if name in __all__:
        return globals()[name]
    raise AttributeError(f"module 'src.knowledge_base' has no attribute '{name}'")
