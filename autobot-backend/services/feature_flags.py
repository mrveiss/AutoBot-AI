# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Feature Flags Service for AutoBot Access Control Rollout

Provides Redis-backed feature flag management for gradual enforcement rollout
across distributed 6-VM infrastructure.

Features:
- DISABLED, LOG_ONLY, ENFORCED enforcement modes
- Real-time flag updates across all VMs
- Per-feature granular control
- Audit logging integration
- Performance monitoring

Usage:
    flags = await get_feature_flags()
    mode = await flags.get_enforcement_mode()

    if mode == EnforcementMode.ENFORCED:
        # Block unauthorized access
        raise HTTPException(403)
    elif mode == EnforcementMode.LOG_ONLY:
        # Log but don't block
        await audit_log("unauthorized_access", result="would_deny")
"""

import asyncio
import json
import logging
from datetime import datetime
from enum import Enum
from typing import Optional

from constants.threshold_constants import StringParsingConstants
from type_defs.common import Metadata

from autobot_shared.redis_client import get_redis_client

logger = logging.getLogger(__name__)


class EnforcementMode(str, Enum):
    """Access control enforcement modes for gradual rollout"""

    DISABLED = "disabled"  # No enforcement, no logging
    LOG_ONLY = "log_only"  # Log violations but don't block
    ENFORCED = "enforced"  # Full enforcement, block violations


class FeatureFlags:
    """
    Redis-backed feature flags for access control rollout

    Uses Redis DB 5 (cache) for feature flag storage
    Supports real-time updates across distributed VMs
    """

    def __init__(self):
        """Initialize feature flags service"""
        self.redis = None
        self._cache = {}
        self._cache_ttl = 5  # seconds
        self._last_refresh = {}
        self._enforcement_default_logged = False

    async def _get_redis(self):
        """Get Redis connection for feature flags (uses cache DB)"""
        if not self.redis:
            # Get async Redis client for cache database (returns coroutine, must await)
            self.redis = await get_redis_client(async_client=True, database="cache")
        return self.redis

    async def get_enforcement_mode(self) -> EnforcementMode:
        """
        Get current access control enforcement mode

        Returns:
            EnforcementMode enum value
        """
        try:
            redis = await self._get_redis()
            mode_str = await redis.get("feature_flag:access_control:enforcement_mode")

            if mode_str:
                # Handle bytes response
                if isinstance(mode_str, bytes):
                    mode_str = mode_str.decode()
                return EnforcementMode(mode_str)

            # Default to DISABLED if not set (log once at INFO, then DEBUG)
            if not self._enforcement_default_logged:
                logger.info("Enforcement mode not set, defaulting to DISABLED")
                self._enforcement_default_logged = True
            else:
                logger.debug("Enforcement mode not set, using default DISABLED")
            return EnforcementMode.DISABLED

        except Exception as e:
            logger.error("Failed to get enforcement mode: %s", e)
            # Fail-safe: default to DISABLED on error
            return EnforcementMode.DISABLED

    async def set_enforcement_mode(self, mode: EnforcementMode) -> bool:
        """
        Set access control enforcement mode

        Args:
            mode: Enforcement mode to set

        Returns:
            True if successful
        """
        try:
            redis = await self._get_redis()

            # Set the mode
            await redis.set("feature_flag:access_control:enforcement_mode", mode.value)

            # Record change in history
            history_key = "feature_flag:access_control:history"
            history_entry = json.dumps(
                {
                    "timestamp": datetime.now().isoformat(),
                    "mode": mode.value,
                    "changed_by": "system",
                }
            )
            await redis._redis.lpush(history_key, history_entry)
            await redis._redis.ltrim(history_key, 0, 99)  # Keep last 100 changes

            logger.info("Enforcement mode set to: %s", mode.value)
            return True

        except Exception as e:
            logger.error("Failed to set enforcement mode: %s", e)
            return False

    async def get_endpoint_enforcement(
        self, endpoint: str
    ) -> Optional[EnforcementMode]:
        """
        Get enforcement mode for specific endpoint (allows per-endpoint control)

        Args:
            endpoint: API endpoint path

        Returns:
            EnforcementMode if set for endpoint, None to use global mode
        """
        try:
            redis = await self._get_redis()
            key = f"feature_flag:access_control:endpoint:{endpoint}"
            mode_str = await redis.get(key)

            if mode_str:
                if isinstance(mode_str, bytes):
                    mode_str = mode_str.decode()
                return EnforcementMode(mode_str)

            return None  # Use global mode

        except Exception as e:
            logger.error("Failed to get endpoint enforcement for %s: %s", endpoint, e)
            return None

    async def set_endpoint_enforcement(
        self, endpoint: str, mode: Optional[EnforcementMode]
    ) -> bool:
        """
        Set enforcement mode for specific endpoint

        Args:
            endpoint: API endpoint path
            mode: Enforcement mode (None to remove override)

        Returns:
            True if successful
        """
        try:
            redis = await self._get_redis()
            key = f"feature_flag:access_control:endpoint:{endpoint}"

            if mode is None:
                # Remove endpoint override
                await redis.delete(key)
                logger.info("Removed enforcement override for %s", endpoint)
            else:
                # Set endpoint override
                await redis.set(key, mode.value)
                logger.info("Set %s enforcement to: %s", endpoint, mode.value)

            return True

        except Exception as e:
            logger.error("Failed to set endpoint enforcement: %s", e)
            return False

    async def get_feature(self, feature_name: str, default: bool = False) -> bool:
        """
        Get boolean feature flag

        Args:
            feature_name: Feature flag name
            default: Default value if not set

        Returns:
            Feature flag value
        """
        try:
            redis = await self._get_redis()
            key = f"feature_flag:{feature_name}"
            value = await redis.get(key)

            if value is None:
                return default

            if isinstance(value, bytes):
                value = value.decode()

            return value.lower() in StringParsingConstants.TRUTHY_STRING_VALUES

        except Exception as e:
            logger.error("Failed to get feature flag %s: %s", feature_name, e)
            return default

    async def set_feature(self, feature_name: str, enabled: bool) -> bool:
        """
        Set boolean feature flag

        Args:
            feature_name: Feature flag name
            enabled: Enable or disable feature

        Returns:
            True if successful
        """
        try:
            redis = await self._get_redis()
            key = f"feature_flag:{feature_name}"
            await redis.set(key, "true" if enabled else "false")

            logger.info("Feature flag %s set to: %s", feature_name, enabled)
            return True

        except Exception as e:
            logger.error("Failed to set feature flag %s: %s", feature_name, e)
            return False

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
            endpoint = key.replace("feature_flag:access_control:endpoint:", "")
            if isinstance(mode_val, bytes):
                mode_val = mode_val.decode()
            endpoint_overrides[endpoint] = mode_val
        return endpoint_overrides

    async def get_rollout_statistics(self) -> Metadata:
        """
        Get rollout statistics and metrics

        Returns:
            Dictionary with rollout statistics
        """
        try:
            redis = await self._get_redis()

            # Get current mode
            mode = await self.get_enforcement_mode()

            # Get and parse change history (Issue #315 - uses helper)
            history_raw = await redis._redis.lrange(
                "feature_flag:access_control:history", 0, 9
            )
            history = self._parse_history_entries(history_raw)

            # Get endpoint overrides
            endpoint_keys = []
            cursor = 0
            while True:
                cursor, keys = await redis._redis.scan(
                    cursor, match="feature_flag:access_control:endpoint:*", count=100
                )
                endpoint_keys.extend(keys)
                if cursor == 0:
                    break

            # Batch fetch endpoint overrides using pipeline (fix N+1 query)
            endpoint_overrides = {}
            if endpoint_keys:
                pipe = redis.pipeline()
                for key in endpoint_keys:
                    pipe.get(key)
                mode_values = await pipe.execute()
                # Use helper to build overrides (Issue #315)
                endpoint_overrides = self._build_endpoint_overrides(
                    endpoint_keys, mode_values
                )

            return {
                "current_mode": mode.value,
                "history": history,
                "endpoint_overrides": endpoint_overrides,
                "total_endpoints_configured": len(endpoint_overrides),
            }

        except Exception as e:
            logger.error("Failed to get rollout statistics: %s", e)
            return {"error": str(e), "current_mode": "unknown"}

    async def clear_all_flags(self) -> bool:
        """
        Clear all feature flags (emergency reset)

        Returns:
            True if successful
        """
        try:
            redis = await self._get_redis()

            # Get all feature flag keys
            cursor = 0
            deleted = 0
            while True:
                cursor, keys = await redis._redis.scan(
                    cursor, match="feature_flag:*", count=100
                )
                if keys:
                    deleted += await redis.delete(*keys)
                if cursor == 0:
                    break

            logger.warning("Cleared %s feature flags", deleted)
            return True

        except Exception as e:
            logger.error("Failed to clear feature flags: %s", e)
            return False


# Global feature flags instance
_feature_flags: Optional[FeatureFlags] = None
_flags_lock = asyncio.Lock()


async def get_feature_flags() -> FeatureFlags:
    """Get or create global feature flags instance"""
    global _feature_flags

    async with _flags_lock:
        if _feature_flags is None:
            _feature_flags = FeatureFlags()
            logger.info("Feature flags service initialized")
        return _feature_flags
