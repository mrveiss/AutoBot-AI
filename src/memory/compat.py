# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Backward Compatibility Wrappers - Drop-in replacements for legacy APIs
"""

import logging
import threading
from typing import Dict, List, Optional

from .enums import MemoryCategory
from .manager import UnifiedMemoryManager
from .models import MemoryEntry, TaskExecutionRecord

logger = logging.getLogger(__name__)


class EnhancedMemoryManager(UnifiedMemoryManager):
    """
    Backward compatibility wrapper for enhanced_memory_manager.py

    All existing code using EnhancedMemoryManager continues to work
    without any changes. This is a drop-in replacement.

    Used by 7 files:
    - src/voice_processing_system.py
    - src/context_aware_decision_system.py
    - src/markdown_reference_system.py
    - src/computer_vision_system.py
    - src/takeover_manager.py
    - src/modern_ai_integration.py
    - backend/api/enhanced_memory.py
    """

    def __init__(self, db_path: str = "data/enhanced_memory.db"):
        """Initialize with enhanced_memory_manager.py defaults"""
        super().__init__(db_path=db_path, enable_cache=True, enable_monitoring=False)
        logger.info("EnhancedMemoryManager compatibility wrapper initialized")

    def log_task_execution(self, record: TaskExecutionRecord) -> str:
        """
        Alias for log_task (backward compatibility)

        ⚠️ WARNING: This is a synchronous method. DO NOT call from async code.
        For async code, create UnifiedMemoryManager directly and use:
            await manager.log_task(record)
        """
        return self.log_task_sync(record)


class LongTermMemoryManager:
    """
    Backward compatibility wrapper for memory_manager.py

    Used by 2 files:
    - src/orchestrator.py
    - analysis/refactoring/test_memory_path_utils.py
    """

    def __init__(
        self, config_path: Optional[str] = None, db_path: str = "data/agent_memory.db"
    ):
        """
        Initialize with memory_manager.py defaults

        Args:
            config_path: Legacy parameter (ignored, kept for backward compatibility)
            db_path: Path to SQLite database (default: "data/agent_memory.db")
        """
        self._unified = UnifiedMemoryManager(
            db_path=db_path,
            enable_cache=True,
            enable_monitoring=False,
            retention_days=90,
        )
        logger.info(
            f"LongTermMemoryManager compatibility wrapper initialized at {db_path}"
        )

    async def store_memory(
        self,
        category: str,
        content: str,
        metadata: Optional[Dict] = None,
        embedding: Optional[bytes] = None,
    ) -> int:
        """Map old API to new unified API"""
        # Convert string category to enum if possible
        try:
            cat = MemoryCategory[category.upper()]
        except (KeyError, AttributeError):
            cat = category  # Use as-is if not in enum

        return await self._unified.store_memory(
            cat, content, metadata, embedding=embedding
        )

    async def retrieve_memories(
        self, category: str, filters: Optional[Dict] = None, limit: int = 100
    ) -> List[MemoryEntry]:
        """Map old API to new unified API"""
        filters = filters or {}

        try:
            cat = MemoryCategory[category.upper()]
        except (KeyError, AttributeError):
            cat = category

        return await self._unified.retrieve_memories(
            cat,
            limit=limit,
            start_date=filters.get("start_date"),
            end_date=filters.get("end_date"),
            reference_path=filters.get("reference_path"),
        )

    async def search_by_metadata(self, metadata_query: Dict) -> List[MemoryEntry]:
        """Search by metadata (limited implementation)"""
        # Convert to content search
        query = " ".join(str(v) for v in metadata_query.values())
        return await self._unified.search_memories(query)

    async def cleanup_old_memories(self, retention_days: Optional[int] = None) -> int:
        """Cleanup old memories"""
        return await self._unified.cleanup_old_memories(retention_days)


# ============================================================================
# GLOBAL INSTANCES (for drop-in replacement)
# ============================================================================

# Lazy initialization - only create when first accessed
_enhanced_memory_instance = None
_long_term_memory_instance = None
_enhanced_memory_lock = threading.Lock()
_long_term_memory_lock = threading.Lock()


def get_enhanced_memory_manager() -> EnhancedMemoryManager:
    """Get global EnhancedMemoryManager instance (singleton, thread-safe)"""
    global _enhanced_memory_instance
    if _enhanced_memory_instance is None:
        with _enhanced_memory_lock:
            # Double-check after acquiring lock
            if _enhanced_memory_instance is None:
                _enhanced_memory_instance = EnhancedMemoryManager()
    return _enhanced_memory_instance


def get_long_term_memory_manager() -> LongTermMemoryManager:
    """Get global LongTermMemoryManager instance (singleton, thread-safe)"""
    global _long_term_memory_instance
    if _long_term_memory_instance is None:
        with _long_term_memory_lock:
            # Double-check after acquiring lock
            if _long_term_memory_instance is None:
                _long_term_memory_instance = LongTermMemoryManager()
    return _long_term_memory_instance


__all__ = [
    "EnhancedMemoryManager",
    "LongTermMemoryManager",
    "get_enhanced_memory_manager",
    "get_long_term_memory_manager",
]
