# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Memory Provider System - Pluggable Backend Architecture

This package provides a provider-based memory system supporting multiple backends:
- PostgreSQL GraphDB (built-in)
- Redis (external, optional)
- Milvus (external, optional)

The provider pattern allows flexible backend selection while maintaining
a unified interface for memory operations across the application.

Issue #4344: Provider-based memory architecture with external provider support
"""

from .external_provider_factory import ExternalProviderFactory, ProviderType
from .memory_provider_interface import MemoryProvider
from .postgres_provider import PostgresMemoryProvider
from .redis_provider import RedisMemoryProvider

__all__ = [
    "MemoryProvider",
    "PostgresMemoryProvider",
    "RedisMemoryProvider",
    "ExternalProviderFactory",
    "ProviderType",
]
