# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Cache management package.

Provides unified cache coordination with memory-pressure-aware eviction.
"""

from .coordinator import CacheCoordinator, get_cache_coordinator
from .protocols import CacheProtocol

__all__ = ["CacheProtocol", "CacheCoordinator", "get_cache_coordinator"]
