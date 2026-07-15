# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
"""Environment variable helpers shared across AutoBot services."""

import logging
import os

logger = logging.getLogger(__name__)


def env_float(name: str, default: float) -> float:
    """Read a float environment variable, falling back to *default* on absence or bad value.

    Returns *default* silently when the var is absent.
    Logs a warning and returns *default* when the var is set but not a valid float.
    """
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning("Invalid %s=%r; using default %s", name, raw, default)
        return default


def env_int(name: str, default: int) -> int:
    """Read an integer environment variable, falling back to *default* on absence or bad value.

    Returns *default* silently when the var is absent.
    Logs a warning and returns *default* when the var is set but not a valid integer.
    """
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("Invalid %s=%r; using default %d", name, raw, default)
        return default


def env_int_clamped(
    name: str,
    default: int,
    min_v: int | None = None,
    max_v: int | None = None,
) -> int:
    """Read an integer environment variable with optional min/max clamping.

    Falls back to *default* (with a warning) if the env var is set but not a
    valid integer.  Returns *default* silently when the var is absent.
    Clamps to [min_v, max_v] when either bound is provided.
    """
    raw = os.environ.get(name)
    if raw is None:
        value = default
    else:
        try:
            value = int(raw)
        except ValueError:
            logger.warning("Invalid %s=%r; using %d", name, raw, default)
            value = default
    if min_v is not None:
        value = max(min_v, value)
    if max_v is not None:
        value = min(max_v, value)
    return value


# Canonical truthy set for boolean env flags. Single source of truth so guards
# don't drift (config_guard used to omit "on", silently ignoring
# ``AUTOBOT_ALLOW_CONFIG_EDITS=on`` — #11220).
_TRUTHY_VALUES: frozenset[str] = frozenset({"1", "true", "yes", "on"})


def truthy(raw: str | None) -> bool:
    """Return True iff *raw* is a recognized truthy flag value (1/true/yes/on).

    Case-insensitive and whitespace-tolerant. ``None`` and any other value
    (``0``/``false``/``off``/empty) read as False.
    """
    return raw is not None and raw.strip().lower() in _TRUTHY_VALUES


def env_flag(name: str, default: bool = False) -> bool:
    """Read a boolean environment variable via the canonical truthy set.

    Returns *default* when the var is absent; otherwise ``truthy(value)``. Using
    this everywhere guarantees ``on``/``yes``/``true``/``1`` behave identically
    across all flags.
    """
    raw = os.environ.get(name)
    return default if raw is None else truthy(raw)
