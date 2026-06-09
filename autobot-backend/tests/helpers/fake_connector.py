# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shared fake AbstractConnector implementation for unit tests.

Extracted from scattered _FakeConnector definitions per #5443/#5558.
"""

import asyncio

from knowledge.connectors.base import ConnectorConfig


class FakeConnector:
    """Minimal stand-in for an AbstractConnector instance.

    Supports optional delay for simulating slow connections and
    Exception result for simulating failures.
    """

    def __init__(self, config: ConnectorConfig, result=True, delay: float = 0.0):
        self.config = config
        self._result = result
        self._delay = delay

    async def test_connection(self):
        if self._delay:
            await asyncio.sleep(self._delay)
        if isinstance(self._result, Exception):
            raise self._result
        return self._result
