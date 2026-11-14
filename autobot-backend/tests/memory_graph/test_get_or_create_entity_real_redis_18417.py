# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The claim-and-write Lua script against a real Redis with RedisJSON (#18417).

The fake-Redis tests mirror the script in Python, so they cannot prove the script
itself. This runs it on a throwaway server; skipped where no redis-stack binary exists.
"""

import asyncio
import shutil
import socket
import subprocess
import time

import pytest

from autobot_memory_graph import AutoBotMemoryGraph
from autobot_memory_graph.owner_scope import OwnerScope

BINARY = shutil.which("redis-stack-server")
pytestmark = pytest.mark.skipif(BINARY is None, reason="redis-stack-server not installed")


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture
def server(tmp_path):
    port = _free_port()
    proc = subprocess.Popen(  # noqa: S603 - fixed argv, throwaway local server
        [BINARY, "--port", str(port), "--save", "", "--dir", str(tmp_path), "--bind", "127.0.0.1"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(100):
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.1).close()
                break
            except OSError:
                time.sleep(0.1)
        else:
            pytest.skip("redis-stack-server did not start")
        yield port
    finally:
        proc.terminate()
        proc.wait(timeout=10)


@pytest.mark.asyncio
async def test_concurrent_upserts_against_real_redis_create_one_entity(server):
    import redis.asyncio as aioredis

    client = aioredis.Redis(host="127.0.0.1", port=server, decode_responses=True)
    graph = AutoBotMemoryGraph()
    graph._initialized = True
    graph.redis_client = client
    graph.knowledge_base = None

    results = await asyncio.gather(
        *[graph.get_or_create_entity("TASK", "Redis", ["a"], owner=OwnerScope.for_user("user-a")) for _ in range(8)]
    )

    keys = [k async for k in client.scan_iter(match="memory:entity:*")]
    assert len(keys) == 1
    assert sorted(created for _, created in results).count(True) == 1
    assert len({entity["id"] for entity, _ in results}) == 1
    await client.aclose()


@pytest.mark.asyncio
async def test_release_is_compare_and_delete_against_real_redis(server):
    import redis.asyncio as aioredis

    from autobot_memory_graph import entity_upsert

    client = aioredis.Redis(host="127.0.0.1", port=server, decode_responses=True)
    graph = AutoBotMemoryGraph()
    graph._initialized = True
    graph.redis_client = client
    key = entity_upsert.name_index_key("Redis")

    await client.set(key, "new")  # a re-claim after the releaser read "old"
    await entity_upsert.release_name(graph, "Redis", "old")
    assert await client.get(key) == "new"

    await entity_upsert.release_name(graph, "Redis", "new")
    assert await client.get(key) is None
    await client.aclose()
