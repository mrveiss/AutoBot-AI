# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Pre-warmed Docker Container Pool (GH#4452)

Reduces sandbox cold-start latency by maintaining a pool of already-running
containers. Callers acquire a warm container, execute via docker exec, then
release it. Released containers are destroyed and replaced asynchronously so
the pool stays at the target size.
"""

import asyncio
from typing import Any, Dict

from autobot_shared.async_compat import fire_and_forget
from autobot_shared.logging_manager import get_logger

try:
    import docker
    from docker.errors import DockerException
except ImportError:
    docker = None
    DockerException = Exception

logger = get_logger(__name__)

_DEFAULT_POOL_SIZE = 2
_ACQUIRE_TIMEOUT = 5.0  # seconds before falling back to cold start


class WarmContainerPool:
    """Pool of pre-started Docker containers for near-zero cold-start execution.

    Each container runs ``sleep infinity`` until a caller acquires it and
    uses ``container.exec_run()`` to execute code. After use the container is
    destroyed and a replacement is created asynchronously, keeping the pool at
    *pool_size* ready containers.
    """

    def __init__(
        self,
        docker_client: "docker.DockerClient",
        image: str,
        pool_size: int = _DEFAULT_POOL_SIZE,
        container_kwargs: Dict[str, Any] | None = None,
    ) -> None:
        """
        Args:
            docker_client: Connected Docker client.
            image: Image to pre-start (e.g. ``"python:3.10-slim"``).
            pool_size: Number of warm containers to maintain.
            container_kwargs: Extra kwargs forwarded to ``containers.run()``.
        """
        self._client = docker_client
        self._image = image
        self._pool_size = pool_size
        self._container_kwargs: Dict[str, Any] = container_kwargs or {}
        self._pool: asyncio.Queue = asyncio.Queue()
        self._running = False
        self._replenish_lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Warm the pool by pre-creating *pool_size* containers.

        Failures are logged but do not prevent partial warm-up; any remaining
        slots will be filled on demand.
        """
        self._running = True
        results = await asyncio.gather(
            *[self._create_warm_container() for _ in range(self._pool_size)],
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, Exception):
                logger.warning("Failed to pre-warm container for %s: %s", self._image, result)
            elif result is not None:
                await self._pool.put(result)

        logger.info(
            "Container pool started for %s: %d/%d warm",
            self._image,
            self._pool.qsize(),
            self._pool_size,
        )

    async def stop(self) -> None:
        """Drain and destroy all containers in the pool.

        #15638: clearing ``_running`` is not enough on its own. A replenish that
        is already inside ``_create_warm_container()`` when ``stop()`` lands
        returns to a loop that now sees ``_running`` false, and used to drop the
        container it had just started -- running, unremoved, with nothing left
        holding a reference to it. One leaked container per start/stop cycle.

        The drain therefore runs under ``_replenish_lock``, which the in-flight
        replenish holds for the whole create. ``stop()`` cannot return while a
        create is in progress, and the replenish that owns that create removes
        what it made rather than dropping it. Cancelling the replenish instead
        would not do: the create runs in a worker thread via
        ``asyncio.to_thread``, and cancelling the awaiting task does not stop
        that thread from finishing the ``containers.run`` call -- it only throws
        away the handle to the container the thread went on to create.
        """
        self._running = False
        async with self._replenish_lock:
            while not self._pool.empty():
                try:
                    container = self._pool.get_nowait()
                    await asyncio.to_thread(container.remove, force=True)
                except Exception as exc:
                    logger.warning("Error destroying pool container: %s", exc)
        logger.info("Container pool stopped for %s", self._image)

    # ------------------------------------------------------------------
    # Acquire / release
    # ------------------------------------------------------------------

    async def acquire(self) -> "docker.models.containers.Container":
        """Return a warm container from the pool.

        If the pool is empty (all containers acquired concurrently), falls
        back to an on-demand cold start. In either case the pool is
        replenished in the background.

        Returns:
            A running Docker container ready for ``exec_run()``.
        """
        try:
            container = await asyncio.wait_for(
                self._try_get_from_pool(),
                timeout=_ACQUIRE_TIMEOUT,
            )
            logger.debug("Acquired warm container %s from pool", container.short_id)
        except asyncio.TimeoutError:
            logger.warning(
                "Container pool empty for %s — falling back to cold start",
                self._image,
            )
            container = await self._create_warm_container()
            if container is None:
                raise RuntimeError(f"Failed to create container for image {self._image}")

        # Refill in the background without blocking the caller. Retained by
        # ``fire_and_forget`` so it cannot be collected before it runs (#15619).
        fire_and_forget(self._replenish(), name="container-pool-replenish")
        return container

    async def release(self, container: "docker.models.containers.Container") -> None:
        """Destroy a used container.

        Containers are not reused between executions — each request gets a
        fresh environment. The pool is replenished by ``_replenish()``,
        which ``acquire()`` schedules automatically.

        Args:
            container: Container returned by :meth:`acquire`.
        """
        try:
            await asyncio.to_thread(container.remove, force=True)
            logger.debug("Released and removed container %s", container.short_id)
        except Exception as exc:
            logger.warning("Failed to remove used container: %s", exc)

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    @property
    def available(self) -> int:
        """Number of warm containers currently in the pool."""
        return self._pool.qsize()

    def get_stats(self) -> Dict[str, Any]:
        """Return pool statistics for monitoring."""
        return {
            "image": self._image,
            "pool_size": self._pool_size,
            "available": self.available,
            "running": self._running,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _try_get_from_pool(self) -> "docker.models.containers.Container":
        """Blocking coroutine that waits for a container from the queue."""
        return await self._pool.get()

    async def _create_warm_container(self) -> "docker.models.containers.Container | None":
        """Start a new idle container and return it.

        The container runs ``sleep infinity`` so it stays alive until
        explicitly removed.

        Returns:
            Running container, or ``None`` on failure.
        """
        try:
            container = await asyncio.to_thread(
                self._client.containers.run,
                self._image,
                ["sleep", "infinity"],
                detach=True,
                remove=False,
                **self._container_kwargs,
            )
            logger.debug("Created warm container %s for %s", container.short_id, self._image)
            return container
        except Exception as exc:
            logger.error("Failed to create warm container for %s: %s", self._image, exc)
            return None

    async def _replenish(self) -> None:
        """Add one container to the pool if it is below target size.

        Protected by a lock to prevent concurrent over-creation.
        """
        if not self._running:
            return

        async with self._replenish_lock:
            if self._pool.qsize() >= self._pool_size:
                return
            container = await self._create_warm_container()
            if container is None:
                return
            if not self._running:
                # ``stop()`` landed while the create was in flight. The
                # container exists and only this frame knows about it, so this
                # frame has to remove it -- dropping it here is the #15638 leak.
                await self._discard_container(container)
                return
            await self._pool.put(container)
            logger.debug(
                "Replenished pool for %s: %d/%d",
                self._image,
                self._pool.qsize(),
                self._pool_size,
            )

    async def _discard_container(self, container: "docker.models.containers.Container") -> None:
        """Remove a container the pool created but is not going to hand out."""
        try:
            await asyncio.to_thread(container.remove, force=True)
            logger.debug("Removed container %s created after shutdown", container.short_id)
        except Exception as exc:
            logger.warning("Failed to remove container created after shutdown: %s", exc)


class ContainerPoolRegistry:
    """Manages one WarmContainerPool per Docker image.

    A single registry can serve multiple images (e.g. python, node, bash)
    without callers needing to know which pool to use.
    """

    def __init__(
        self,
        docker_client: "docker.DockerClient",
        pool_size: int = _DEFAULT_POOL_SIZE,
        default_container_kwargs: Dict[str, Any] | None = None,
    ) -> None:
        self._client = docker_client
        self._pool_size = pool_size
        self._default_kwargs = default_container_kwargs or {}
        self._pools: Dict[str, WarmContainerPool] = {}
        self._started = False

    async def start(self, images: list[str]) -> None:
        """Start pools for all given images concurrently.

        Args:
            images: Docker image names to pre-warm.
        """
        for image in images:
            pool = WarmContainerPool(
                docker_client=self._client,
                image=image,
                pool_size=self._pool_size,
                container_kwargs=self._default_kwargs.copy(),
            )
            self._pools[image] = pool

        await asyncio.gather(*[p.start() for p in self._pools.values()])
        self._started = True
        logger.info("ContainerPoolRegistry started for images: %s", images)

    async def stop(self) -> None:
        """Stop all pools and destroy their containers."""
        await asyncio.gather(*[p.stop() for p in self._pools.values()])
        self._pools.clear()
        self._started = False

    def get_pool(self, image: str) -> WarmContainerPool | None:
        """Return the pool for *image*, or ``None`` if not registered."""
        return self._pools.get(image)

    def get_stats(self) -> Dict[str, Any]:
        """Return stats for all pools."""
        return {image: pool.get_stats() for image, pool in self._pools.items()}
