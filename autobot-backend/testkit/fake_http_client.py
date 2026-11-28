# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One fake provider HTTP connection for chat tests (#19753, #20195).

``FakeHttpClient.post`` records every JSON body it is handed and returns ``reply`` or raises ``error``;
``FakeReply`` / ``FakeStreamBody`` are the streamed response. Patch ``autobot_shared.http_client.get_http_client``
to return it, or pass it where the code takes a client.
"""

from __future__ import annotations

import json


class FakeStreamBody:
    """The streamed response body: ``lines`` then, optionally, an exception mid-stream."""

    def __init__(self, lines, then_raise=None):
        self._lines, self._then_raise = list(lines), then_raise

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._lines:
            return self._lines.pop(0)
        if self._then_raise is not None:
            raise self._then_raise
        raise StopAsyncIteration


class FakeReply:
    def __init__(self, status=200, body=None):
        self.status = status
        self.content = body or FakeStreamBody([])

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeHttpClient:
    """``post`` returns ``reply`` or raises ``error``; counts calls and ``decrement_active``."""

    def __init__(self, reply=None, error=None):
        self.reply, self.error = reply, error
        self.posts: list[dict] = []
        self.decrements = 0

    async def post(self, url, json=None, **kwargs):  # noqa: A002
        self.posts.append(json)
        if self.error is not None:
            raise self.error
        return self.reply

    async def decrement_active(self):
        self.decrements += 1


def ollama_chunk(text, done=False):
    return json.dumps({"response": text, "done": done}).encode() + b"\n"
