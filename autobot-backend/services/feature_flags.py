# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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
import os
from datetime import datetime, timezone
from enum import Enum

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_mixin import AsyncRedisClientMixin
from constants.threshold_constants import CategoryDefaults, StringParsingConstants
from type_defs.common import Metadata

logger = get_logger(__name__)


class EnforcementMode(str, Enum):
    """Access control enforcement modes for gradual rollout"""

    DISABLED = "disabled"  # No enforcement, no logging
    LOG_ONLY = "log_only"  # Log violations but don't block
    ENFORCED = "enforced"  # Full enforcement, block violations


class EnforcementModeUnavailable(RuntimeError):
    """The enforcement mode could not be read (#14010).

    Deliberately distinct from :attr:`EnforcementMode.DISABLED`. An operator
    turning enforcement off and the flag store being unreachable are different
    facts, and collapsing them into one value is how an outage silently became
    "authorization is off" platform-wide, with nothing louder than a debug line
    saying so.

    Callers that display the mode may surface this as unknown; callers that
    *gate* on it must not read it as permission.
    """


# The single Redis key the platform's whole access-control posture is read from.
# It was a literal repeated at each reader and writer; provisioning has to name
# the same key, and a fourth copy of a string is how the fourth copy drifts.
ENFORCEMENT_MODE_KEY = "feature_flag:access_control:enforcement_mode"

# Posture provisioning writes when an install has no value of its own (#14866).
# ``log_only`` is the value both issues record: #14010's acceptance criterion 4
# asks for "the ``log_only`` measurement before any flip to ``enforced``", and
# #14866 calls it "the safe first value" because every ownership check runs and
# every violation is audited while nothing that succeeds today starts being
# refused. Flipping to ``enforced`` is a separate, measured step and is
# deliberately NOT made here. Neither is the meaning of an unset key or of
# ``log_only`` changed: this makes *unset* stop being the production state, it
# does not redefine it.
PROVISIONED_ENFORCEMENT_MODE_ENV = "ACCESS_CONTROL_ENFORCEMENT_MODE"
PROVISIONED_ENFORCEMENT_MODE_DEFAULT = EnforcementMode.LOG_ONLY


def resolve_provisioned_enforcement_mode(raw: str | None = None) -> EnforcementMode:
    """Resolve the posture provisioning should write.

    Precedence: an explicit *raw* value (the provisioning entry point's
    ``--mode``), then the ``ACCESS_CONTROL_ENFORCEMENT_MODE`` environment value,
    then :data:`PROVISIONED_ENFORCEMENT_MODE_DEFAULT`.

    An unrecognised value raises instead of falling back. Quietly defaulting a
    misconfigured authorization posture is precisely the defect #14866 exists
    for, and a provisioning run that cannot honour what it was asked for must
    say so rather than write something else.
    """
    value = raw if raw is not None else os.environ.get(PROVISIONED_ENFORCEMENT_MODE_ENV, "")
    if not value or not value.strip():
        return PROVISIONED_ENFORCEMENT_MODE_DEFAULT
    try:
        return EnforcementMode(value.strip().lower())
    except ValueError as exc:
        valid = ", ".join(mode.value for mode in EnforcementMode)
        raise ValueError(f"Unrecognised enforcement mode {value!r}; expected one of: {valid}") from exc


class FeatureFlags(AsyncRedisClientMixin):
    """
    Redis-backed feature flags for access control rollout

    Uses Redis DB 5 (cache) for feature flag storage
    Supports real-time updates across distributed VMs
    """

    _redis_database = "cache"

    def __init__(self) -> None:
        """Initialize feature flags service"""
        self._cache = {}
        self._cache_ttl = 5  # seconds
        self._last_refresh = {}
        self._enforcement_default_logged = False

    async def get_enforcement_mode(self) -> EnforcementMode:
        """
        Get current access control enforcement mode

        Returns:
            EnforcementMode enum value
        """
        try:
            redis = await self._get_redis()
            mode_str = await redis.get(ENFORCEMENT_MODE_KEY)

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
            # NOT a fail-safe: this is an authorization control, and returning
            # DISABLED here made an unreachable flag store indistinguishable
            # from a deliberate "off" (#14010). Raise so the caller decides,
            # rather than deciding "no enforcement" on its behalf.
            logger.error("Could not read enforcement mode: %s", e)
            raise EnforcementModeUnavailable(str(e)) from e

    @staticmethod
    async def _read_enforcement_mode(redis) -> EnforcementMode | None:
        """Return the mode currently stored, or ``None`` when the key is absent."""
        raw = await redis.get(ENFORCEMENT_MODE_KEY)
        if isinstance(raw, bytes):
            raw = raw.decode()
        return EnforcementMode(raw) if raw else None

    async def seed_enforcement_mode(
        self, mode: EnforcementMode | None = None, dry_run: bool = False
    ) -> tuple[bool, EnforcementMode]:
        """Give an install a deliberate enforcement posture without clobbering one.

        Writes *mode* only when the key is absent, with ``SET NX`` so the check
        and the write are one atomic Redis operation: two provisioning runs
        racing cannot both write, and re-provisioning never overwrites a value an
        operator set on purpose (#14866). That is the whole of the idempotency
        guarantee -- it is Redis's, not a read-then-write of ours.

        Returns ``(written, effective_mode)``.
        """
        target = mode or resolve_provisioned_enforcement_mode()
        redis = await self._get_redis()
        if redis is None:
            raise EnforcementModeUnavailable("no Redis client available to provision the enforcement mode")

        if dry_run:
            existing = await self._read_enforcement_mode(redis)
            return existing is None, existing or target

        if await redis.set(ENFORCEMENT_MODE_KEY, target.value, nx=True):
            logger.info("Provisioned access control enforcement mode: %s", target.value)
            return True, target

        existing = await self._read_enforcement_mode(redis)
        if existing is None:
            raise EnforcementModeUnavailable("enforcement mode was neither written nor readable")
        logger.info("Access control enforcement mode already set to %s; left unchanged", existing.value)
        return False, existing

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
            await redis.set(ENFORCEMENT_MODE_KEY, mode.value)

            # Record change in history
            history_key = "feature_flag:access_control:history"
            history_entry = json.dumps(
                {
                    "timestamp": datetime.now(tz=timezone.utc).isoformat(),
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

    async def get_endpoint_enforcement(self, endpoint: str) -> EnforcementMode | None:
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

    async def set_endpoint_enforcement(self, endpoint: str, mode: EnforcementMode | None) -> bool:
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

    async def get_feature_override(self, feature_name: str) -> bool | None:
        """
        Read a feature flag without applying a default (GH#12820).

        :meth:`get_feature` cannot distinguish "explicitly set to false" from "never
        set", which is exactly the difference between an operator turning something
        off and simply not having an opinion. Callers that must show whether an
        override exists — and offer to clear it — need the unset case back.

        Args:
            feature_name: Feature flag name

        Returns:
            The stored boolean, or None when no override is stored.
        """
        try:
            redis = await self._get_redis()
            value = await redis.get(f"feature_flag:{feature_name}")

            if value is None:
                return None

            if isinstance(value, bytes):
                value = value.decode()

            return value.lower() in StringParsingConstants.TRUTHY_STRING_VALUES

        except Exception as e:
            logger.error("Failed to read feature flag override %s: %s", feature_name, e)
            return None

    async def clear_feature(self, feature_name: str) -> bool:
        """
        Remove a feature flag override so its caller-supplied default applies again.

        The service could set a flag but never unset one, which made "revert to
        default" impossible to express (GH#12820).

        Args:
            feature_name: Feature flag name

        Returns:
            True if the key was removed or already absent.
        """
        try:
            redis = await self._get_redis()
            await redis.delete(f"feature_flag:{feature_name}")

            logger.info("Feature flag %s override cleared", feature_name)
            return True

        except Exception as e:
            logger.error("Failed to clear feature flag %s: %s", feature_name, e)
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
            history_raw = await redis._redis.lrange("feature_flag:access_control:history", 0, 9)
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
                endpoint_overrides = self._build_endpoint_overrides(endpoint_keys, mode_values)

            return {
                "current_mode": mode.value,
                "history": history,
                "endpoint_overrides": endpoint_overrides,
                "total_endpoints_configured": len(endpoint_overrides),
            }

        except Exception as e:
            logger.error("Failed to get rollout statistics: %s", e)
            return {
                "error": "Failed to retrieve rollout statistics",
                "current_mode": CategoryDefaults.UNKNOWN,
            }

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
                cursor, keys = await redis._redis.scan(cursor, match="feature_flag:*", count=100)
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
_feature_flags: FeatureFlags | None = None
_flags_lock = asyncio.Lock()


async def get_feature_flags() -> FeatureFlags:
    """Get or create global feature flags instance"""
    global _feature_flags

    async with _flags_lock:
        if _feature_flags is None:
            _feature_flags = FeatureFlags()
            logger.info("Feature flags service initialized")
        return _feature_flags
