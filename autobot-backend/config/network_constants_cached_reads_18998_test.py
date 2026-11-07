# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Repeated NetworkConstants attribute reads cost at most one Redis call (#18998).

``_LazyConfigMeta.__getattr__`` -> ``_get_config_value`` -> ``ConfigRegistry.get``;
the negative cache in the registry is what makes the repeats free.
"""

import os
from unittest.mock import patch

from autobot_shared.network_constants import NetworkConstants
from config.registry import ConfigRegistry


class _CountingRedis:
    def __init__(self):
        self.gets = 0

    def get(self, key):
        self.gets += 1
        return None


def test_one_hundred_reads_of_one_constant_make_at_most_one_redis_call():
    """Reverting the ``_remember_miss`` call in ``ConfigRegistry.get`` makes this 100."""
    ConfigRegistry.clear_cache()
    fake = _CountingRedis()
    ConfigRegistry._redis_client = fake
    try:
        with patch.dict(os.environ, {}, clear=True):
            values = {NetworkConstants.REDIS_PORT for _ in range(100)}
        assert len(values) == 1
        assert fake.gets <= 1
    finally:
        ConfigRegistry.clear_cache()
