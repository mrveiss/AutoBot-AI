# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Rollout-statistics helpers for :class:`services.feature_flags.FeatureFlags`.

Split out of ``feature_flags.py`` (#18998) to keep that module under the file
size ceiling; behaviour is unchanged.
"""

import json

from autobot_shared.logging_manager import get_logger
from services.feature_flags_cache import ENDPOINT_KEY_PREFIX

logger = get_logger(__name__)


class FeatureFlagStatsMixin:
    """History parsing and per-endpoint override collection for rollout stats."""

    def _parse_history_entries(self, history_raw: list) -> list:
        """Parse raw history entries from Redis. (Issue #315 - extracted)"""
        history = []
        for entry in history_raw:
            if isinstance(entry, bytes):
                entry = entry.decode()
            try:
                history.append(json.loads(entry))
            except Exception as e:
                logger.debug("Skipping malformed history entry: %s", e)
        return history

    def _build_endpoint_overrides(self, endpoint_keys: list, mode_values: list) -> dict:
        """Build endpoint overrides dict from keys and values. (Issue #315 - extracted)"""
        endpoint_overrides = {}
        for key, mode_val in zip(endpoint_keys, mode_values):
            if not mode_val:
                continue
            if isinstance(key, bytes):
                key = key.decode()
            endpoint = key.replace(ENDPOINT_KEY_PREFIX, "")
            if isinstance(mode_val, bytes):
                mode_val = mode_val.decode()
            endpoint_overrides[endpoint] = mode_val
        return endpoint_overrides

    async def _collect_endpoint_overrides(self, redis) -> dict:
        """Scan every stored endpoint override and fetch them in one pipeline (no N+1)."""
        endpoint_keys = []
        cursor = 0
        while True:
            cursor, keys = await redis.scan(cursor, match=f"{ENDPOINT_KEY_PREFIX}*", count=100)
            endpoint_keys.extend(keys)
            if cursor == 0:
                break
        if not endpoint_keys:
            return {}
        pipe = redis.pipeline()
        for key in endpoint_keys:
            pipe.get(key)
        mode_values = await pipe.execute()
        return self._build_endpoint_overrides(endpoint_keys, mode_values)
