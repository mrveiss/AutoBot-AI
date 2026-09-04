# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#15638: stop() must not leave behind a container a replenish was creating.

``acquire()`` fires ``_replenish()`` in the background. ``_replenish`` re-checks
``_running`` after the create, and ``stop()`` used to do nothing but clear that
flag and drain the queue. A replenish already inside ``_create_warm_container``
when ``stop()`` landed therefore started a Docker container, came back to a loop
that now saw ``_running`` false, and dropped it — running, never removed, with
nothing holding a reference to it. One leaked container per start/stop cycle.

Cancelling the replenish is not the fix: the create runs in a worker thread via
``asyncio.to_thread``, so cancelling the awaiting task does not stop the thread
from finishing ``containers.run`` — it only throws away the handle to what the
thread went on to create. ``stop()`` takes ``_replenish_lock`` instead, which
the in-flight replenish holds for the whole create.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any, List

from services.execution.container_pool import WarmContainerPool


class _FakeContainer:
    def __init__(self, short_id: str) -> None:
        self.short_id = short_id
        self.removed = False

    def remove(self, force: bool = False) -> None:
        self.removed = True


class _BlockingContainers:
    """``containers.run`` parks inside the worker thread until released.

    That park is the race: it is exactly the window in which ``stop()`` lands
    while a container is being created.
    """

    def __init__(self) -> None:
        self.created: List[_FakeContainer] = []
        self.calls = 0
        self.entered = threading.Event()
        self.release = threading.Event()

    def run(self, image: str, command: Any, **kwargs: Any) -> _FakeContainer:
        self.calls += 1
        self.entered.set()
        assert self.release.wait(timeout=10), "the test never released the blocked create"
        container = _FakeContainer(f"fake{self.calls}")
        self.created.append(container)
        return container


class _FakeDockerClient:
    def __init__(self) -> None:
        self.containers = _BlockingContainers()


async def _wait_for(predicate: Any, timeout: float = 5.0) -> bool:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        await asyncio.sleep(0.01)
        if predicate():
            return True
    return False


class TestStopRacesAMidFlightCreate:
    async def test_the_container_created_during_shutdown_is_removed(self) -> None:
        client = _FakeDockerClient()
        pool = WarmContainerPool(docker_client=client, image="probe:latest", pool_size=1)
        pool._running = True

        replenish = asyncio.create_task(pool._replenish())
        assert await _wait_for(client.containers.entered.is_set), "the create never started"

        stop = asyncio.create_task(pool.stop())
        await asyncio.sleep(0.05)
        assert not stop.done(), (
            "stop() returned while a create was still in flight — whatever that create produces "
            "has nowhere to be recorded and is leaked"
        )

        client.containers.release.set()
        await asyncio.wait_for(stop, timeout=10)
        await asyncio.wait_for(replenish, timeout=10)

        assert len(client.containers.created) == 1
        assert client.containers.created[0].removed, (
            "the container the replenish created during shutdown was dropped, not removed — it is "
            "still running with nothing referencing it"
        )
        assert pool.available == 0

    async def test_a_pooled_container_is_still_drained(self) -> None:
        """The drain moved under a lock; it still has to drain."""
        client = _FakeDockerClient()
        client.containers.release.set()
        pool = WarmContainerPool(docker_client=client, image="probe:latest", pool_size=1)
        pool._running = True

        await pool._replenish()
        assert pool.available == 1

        await pool.stop()
        assert client.containers.created[0].removed, "the pooled container survived stop()"
        assert pool.available == 0

    async def test_no_container_is_created_after_stop(self) -> None:
        client = _FakeDockerClient()
        client.containers.release.set()
        pool = WarmContainerPool(docker_client=client, image="probe:latest", pool_size=1)
        pool._running = True

        await pool._replenish()
        await pool.stop()

        await pool._replenish()
        assert client.containers.calls == 1, "a replenish scheduled before stop() created a container after it"
        assert pool.available == 0
