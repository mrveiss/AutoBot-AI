# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Key counts come from the connection's own database, never an INFO keyspace ``db<N>`` (#19232).

``info.get("db8")`` / ``info.get("db1")`` named a number the one table owns: an
``AUTOBOT_REDIS_DB_*`` override moved the database and the count read zero (or another DB's).
Each fake answers INFO with a decoy count under the old literal, so a regression reads it.
"""

import asyncio
import types
from collections import defaultdict

from api import analytics_controller, knowledge_mcp

_DECOY = {"db1": {"keys": 999}, "db8": {"keys": 999}, "used_memory_human": "1M", "used_memory": 1024}


class _SyncDB:
    def info(self):
        return dict(_DECOY)

    def dbsize(self):
        return 3


class _AsyncDB:
    async def info(self):
        return dict(_DECOY)

    async def dbsize(self):
        return 3


def test_vector_info_counts_the_vectors_connections_keys():
    redis_mgr = types.SimpleNamespace(get_connection=lambda database: _SyncDB())
    result = asyncio.run(knowledge_mcp._vector_op_info(None, redis_mgr, {}))
    assert result["data"]["total_keys"] == 3


def test_usage_statistics_count_the_knowledge_connections_keys():
    controller = object.__new__(analytics_controller.AnalyticsController)
    controller.api_frequencies, controller.error_counts = defaultdict(int), defaultdict(int)
    controller.websocket_activity = defaultdict(int)

    async def get_redis_connection(database):
        return _AsyncDB()

    controller.get_redis_connection = get_redis_connection
    stats = asyncio.run(controller.get_usage_statistics())
    assert stats["knowledge_base_usage"]["keys_count"] == 3
