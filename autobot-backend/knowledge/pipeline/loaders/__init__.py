# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Loaders Package - Import all loaders to trigger registration.

Issue #759: Knowledge Pipeline Foundation - Extract, Cognify, Load (ECL).
"""

from knowledge.pipeline.loaders.chromadb_loader import ChromaDBLoader
from knowledge.pipeline.loaders.redis_graph_loader import RedisGraphLoader
from knowledge.pipeline.loaders.sqlite_loader import SQLiteLoader

__all__ = [
    "ChromaDBLoader",
    "RedisGraphLoader",
    "SQLiteLoader",
]
