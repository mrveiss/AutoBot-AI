# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Shared fake KnowledgeBase implementations for unit tests.

Extracted from scattered _FakeKB definitions per #5443/#5557.
"""

from unittest.mock import AsyncMock, MagicMock

from knowledge.facts import FactsMixin


class MinimalFakeKB:
    """Minimal KB stub exposing only the redis() accessor."""

    def __init__(self, fake_redis=None):
        self._aioredis_client = fake_redis if fake_redis is not None else AsyncMock()

    def redis(self):
        return self._aioredis_client


class FactsFakeKB(MinimalFakeKB, FactsMixin):
    """KB stub exposing FactsMixin interface for facts-layer unit tests."""

    initialized = True
    embedding_model_name = "test-embed"

    def __init__(self, vector_store=None, fake_redis=None):
        self.vector_store = vector_store
        self.redis_client = MagicMock()
        self._aioredis_client = fake_redis if fake_redis is not None else AsyncMock()

    def ensure_initialized(self):
        pass

    async def _increment_stat(self, *_):
        pass

    def _schedule_bm25_refresh(self):
        pass

    async def _track_session_fact_relationship(self, *_):
        pass
