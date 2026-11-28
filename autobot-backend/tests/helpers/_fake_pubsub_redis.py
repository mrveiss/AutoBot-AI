# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""An in-memory Redis with just the pub/sub surface the turn-cancel bus uses (#18448).

``publish`` returns the number of subscribers it reached, exactly as Redis does:
the bus's "how many acks to wait for" depends on that number being real.
"""

import asyncio


class FakePubSub:
    def __init__(self, redis):
        self._redis = redis
        self._queue = asyncio.Queue()
        self._channels = []

    async def subscribe(self, channel):
        self._redis.subscribers.setdefault(channel, []).append(self._queue)
        self._channels.append(channel)

    async def unsubscribe(self, channel):
        queues = self._redis.subscribers.get(channel, [])
        if self._queue in queues:
            queues.remove(self._queue)

    async def listen(self):
        while True:
            yield await self._queue.get()

    async def aclose(self):
        for channel in list(self._channels):
            await self.unsubscribe(channel)


class FakeRedis:
    def __init__(self):
        self.subscribers = {}

    def pubsub(self):
        return FakePubSub(self)

    async def publish(self, channel, data):
        queues = self.subscribers.get(channel, [])
        for queue in queues:
            queue.put_nowait({"type": "message", "channel": channel, "data": data})
        return len(queues)

    def listeners(self, prefix):
        return sum(len(q) for ch, q in self.subscribers.items() if ch.startswith(prefix))
