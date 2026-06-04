# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
"""Environment variable helpers shared across AutoBot services."""

import logging
import os

logger = logging.getLogger(__name__)


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
