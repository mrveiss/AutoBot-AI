# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for WarmContainerPool and ContainerPoolRegistry (GH#4452)

Validates pool start/stop, acquire/release, cold-start fallback, replenishment,
and DockerBackend integration with pool enabled.
"""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from services.execution.container_pool import (
    ContainerPoolRegistry,
    WarmContainerPool,
)
from services.execution.base_backend import (
    ExecutionStatus,
    ExecutionTask,
)


def _make_container(short_id: str = "abc123") -> MagicMock:
    """Build a minimal mock Docker container."""
    c = MagicMock()
    c.short_id = short_id
    c.id = short_id * 2
    c.remove = MagicMock()
    return c


def _make_docker_client(*container_ids: str) -> MagicMock:
    """Build a mock Docker client that returns containers for run() calls."""
    client = MagicMock()
    containers = [_make_container(cid) for cid in container_ids] if container_ids else [_make_container()]
    client.containers.run.side_effect = list(containers)
    return client


@pytest.mark.asyncio
class TestWarmContainerPool:
    """Unit tests for WarmContainerPool."""

    async def test_start_fills_pool(self):
        """start() should place pool_size containers into the queue."""
        containers = [_make_container(f"c{i}") for i in range(2)]
        client = MagicMock()
        client.containers.run.side_effect = list(containers)

        pool = WarmContainerPool(docker_client=client, image="python:3.10-slim", pool_size=2)
        await pool.start()

        assert pool.available == 2
        assert client.containers.run.call_count == 2

    async def test_start_partial_failure(self):
        """start() tolerates individual container creation failures."""
        good = _make_container("good")
        client = MagicMock()
        client.containers.run.side_effect = [Exception("daemon error"), good]

        pool = WarmContainerPool(docker_client=client, image="python:3.10-slim", pool_size=2)
        await pool.start()

        # One succeeded despite one failure
        assert pool.available == 1

    async def test_acquire_returns_warm_container(self):
        """acquire() dequeues a warm container without calling containers.run again."""
        container = _make_container("warm1")
        client = MagicMock()
        client.containers.run.return_value = container

        pool = WarmContainerPool(docker_client=client, image="python:3.10-slim", pool_size=1)
        await pool.start()

        # Reset call count after start
        client.containers.run.reset_mock()

        acquired = await pool.acquire()
        assert acquired is container
        # Pool was pre-filled; acquire should not create a new one synchronously
        # (replenish runs as a background task)
        assert client.containers.run.call_count == 0

    async def test_acquire_cold_start_when_pool_empty(self):
        """acquire() falls back to a fresh container when the pool is empty."""
        fresh = _make_container("fresh")
        client = MagicMock()
        # start() gets nothing (size 0), then fallback creates one
        client.containers.run.side_effect = [fresh]

        pool = WarmContainerPool(docker_client=client, image="python:3.10-slim", pool_size=0)
        await pool.start()  # pool_size=0, nothing pre-created

        # Provide a container for the cold-start path
        client.containers.run.reset_mock()
        client.containers.run.return_value = fresh

        # Patch the timeout so the queue wait immediately times out
        with patch("services.execution.container_pool._ACQUIRE_TIMEOUT", 0.01):
            acquired = await pool.acquire()

        assert acquired is fresh

    async def test_release_removes_container(self):
        """release() calls remove(force=True) on the container."""
        container = _make_container("used")
        client = MagicMock()
        client.containers.run.return_value = container

        pool = WarmContainerPool(docker_client=client, image="python:3.10-slim", pool_size=1)
        await pool.start()
        acquired = await pool.acquire()
        await pool.release(acquired)

        container.remove.assert_called_once_with(force=True)

    async def test_release_tolerates_remove_error(self):
        """release() does not raise if remove() fails."""
        container = _make_container("bad")
        container.remove.side_effect = Exception("already gone")

        client = MagicMock()
        client.containers.run.return_value = container

        pool = WarmContainerPool(docker_client=client, image="python:3.10-slim", pool_size=1)
        await pool.start()
        acquired = await pool.acquire()

        # Should not raise
        await pool.release(acquired)

    async def test_stop_destroys_all_containers(self):
        """stop() removes every container remaining in the pool."""
        containers = [_make_container(f"s{i}") for i in range(3)]
        client = MagicMock()
        client.containers.run.side_effect = list(containers)

        pool = WarmContainerPool(docker_client=client, image="python:3.10-slim", pool_size=3)
        await pool.start()
        await pool.stop()

        for c in containers:
            c.remove.assert_called_with(force=True)
        assert pool.available == 0

    async def test_get_stats(self):
        """get_stats() returns expected keys."""
        client = MagicMock()
        client.containers.run.return_value = _make_container()

        pool = WarmContainerPool(docker_client=client, image="my-image", pool_size=1)
        await pool.start()

        stats = pool.get_stats()
        assert stats["image"] == "my-image"
        assert stats["pool_size"] == 1
        assert "available" in stats
        assert stats["running"] is True

    async def test_replenish_adds_container(self):
        """_replenish() adds a container to a depleted pool."""
        c1 = _make_container("c1")
        c2 = _make_container("c2")
        client = MagicMock()
        client.containers.run.side_effect = [c1, c2]

        pool = WarmContainerPool(docker_client=client, image="python:3.10-slim", pool_size=1)
        await pool.start()

        assert pool.available == 1
        await pool.acquire()  # drains pool, triggers background replenish
        # Give the background task a chance to run
        await asyncio.sleep(0.05)
        assert pool.available == 1  # replenished

    async def test_replenish_noop_when_pool_full(self):
        """_replenish() does not over-create when pool is already full."""
        c1 = _make_container("c1")
        client = MagicMock()
        client.containers.run.return_value = c1

        pool = WarmContainerPool(docker_client=client, image="python:3.10-slim", pool_size=1)
        await pool.start()

        pre = client.containers.run.call_count
        await pool._replenish()
        # Pool was already at capacity — no new container needed
        assert client.containers.run.call_count == pre


@pytest.mark.asyncio
class TestContainerPoolRegistry:
    """Unit tests for ContainerPoolRegistry."""

    async def test_start_creates_pools_for_each_image(self):
        """start() initialises one pool per image."""
        client = MagicMock()
        client.containers.run.return_value = _make_container()

        registry = ContainerPoolRegistry(docker_client=client, pool_size=1)
        await registry.start(["img-a", "img-b"])

        assert registry.get_pool("img-a") is not None
        assert registry.get_pool("img-b") is not None
        assert registry.get_pool("img-c") is None

    async def test_stop_clears_pools(self):
        """stop() calls stop() on every pool and removes them from the registry."""
        client = MagicMock()
        client.containers.run.return_value = _make_container()

        registry = ContainerPoolRegistry(docker_client=client, pool_size=1)
        await registry.start(["my-img"])
        await registry.stop()

        assert registry.get_pool("my-img") is None

    async def test_get_stats_returns_all_images(self):
        """get_stats() includes every registered image."""
        client = MagicMock()
        client.containers.run.return_value = _make_container()

        registry = ContainerPoolRegistry(docker_client=client, pool_size=1)
        await registry.start(["img-x", "img-y"])

        stats = registry.get_stats()
        assert "img-x" in stats
        assert "img-y" in stats


@pytest.mark.asyncio
class TestDockerBackendWithPool:
    """Integration tests for DockerBackend with use_pool=True (GH#4452)."""

    @pytest.fixture
    def mock_docker(self):
        with patch("services.execution.docker_backend.docker") as m:
            client = MagicMock()
            m.from_env.return_value = client
            client.ping.return_value = None
            yield client

    async def test_pooled_execute_calls_exec_run(self, mock_docker):
        """When pool is warmed, execute uses exec_run instead of containers.run."""
        from services.execution.docker_backend import DockerBackend

        warm_container = _make_container("warm")
        exec_result = MagicMock()
        exec_result.exit_code = 0
        exec_result.output = b"hello pooled"
        warm_container.exec_run.return_value = exec_result

        # containers.run only called for pool warm-up
        mock_docker.containers.run.return_value = warm_container

        backend = DockerBackend(use_pool=True, pool_size=1)
        await backend.warm_pool(["python:3.10-slim"])

        task = ExecutionTask(
            task_id="pool-1",
            code="print('hello pooled')",
            language="python",
            timeout_seconds=10,
        )

        result = await backend.execute(task)

        assert result.status == ExecutionStatus.SUCCESS
        assert "hello pooled" in result.stdout
        # exec_run was used, not a fresh containers.run for the task itself
        warm_container.exec_run.assert_called_once()

    async def test_pooled_execute_falls_back_when_pool_not_warmed(self, mock_docker):
        """When the pool has no containers for the image, cold-start runs."""
        from services.execution.docker_backend import DockerBackend

        cold_container = _make_container("cold")
        cold_container.wait.return_value = {"StatusCode": 0}
        cold_container.logs.return_value = b"cold output"
        mock_docker.containers.run.return_value = cold_container

        # Pool is enabled but we never call warm_pool — so no pool for "python:3.10-slim"
        backend = DockerBackend(use_pool=True, pool_size=1)
        # Do NOT call warm_pool → pool_registry has no pool for the image

        task = ExecutionTask(
            task_id="cold-1",
            code="print('cold')",
            language="python",
            timeout_seconds=10,
        )

        result = await backend.execute(task)

        # Should still succeed via cold-start path
        assert result.status == ExecutionStatus.SUCCESS

    async def test_cleanup_stops_pool(self, mock_docker):
        """cleanup() stops the pool registry."""
        from services.execution.docker_backend import DockerBackend

        mock_docker.containers.run.return_value = _make_container()

        backend = DockerBackend(use_pool=True, pool_size=1)
        await backend.warm_pool(["python:3.10-slim"])

        # Should not raise
        await backend.cleanup()

    async def test_get_pool_stats_empty_without_pool(self, mock_docker):
        """get_pool_stats() returns {} when use_pool=False."""
        from services.execution.docker_backend import DockerBackend

        backend = DockerBackend(use_pool=False)
        assert backend.get_pool_stats() == {}

    async def test_get_pool_stats_populated_with_pool(self, mock_docker):
        """get_pool_stats() returns image keys when pool is warmed."""
        from services.execution.docker_backend import DockerBackend

        mock_docker.containers.run.return_value = _make_container()

        backend = DockerBackend(use_pool=True, pool_size=1)
        await backend.warm_pool(["python:3.10-slim"])

        stats = backend.get_pool_stats()
        assert "python:3.10-slim" in stats
