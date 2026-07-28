# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
"""Environment variable helpers shared across AutoBot services."""

import logging
import os

logger = logging.getLogger(__name__)


def blank_to_none(value: object) -> str | None:
    """Collapse a blank value to ``None`` — the canonical "blank means absent" rule (#12782).

    Exists separately from :func:`env_raw` because the same defect arrives by two
    routes. ``env_raw`` covers values read from ``os.environ``; this covers values
    that reach code through ``ssot_config``, whose optional knobs are declared
    ``str = Field(default="")``. An unset knob therefore surfaces as ``""``, not
    ``None``, so ``if raw is None`` never fires and ``int("")`` raises — which is
    why six settings logged a spurious "invalid value" warning on every boot while
    quietly using their defaults.

    Kept as one function rather than repeating ``or None`` / ``.strip()`` at each
    call site, so "what counts as blank" has a single definition.
    """
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def env_raw(name: str) -> str | None:
    """Read an env var, treating a blank value as absent (#12782).

    A deployment template that renders an undefined variable exports ``NAME=``
    rather than omitting the line. That blank is worse than absence: it looks
    "set" to any presence check, and ``os.environ.get(name, default)`` returns
    ``""`` — NOT the default — so every default-argument fallback in the codebase
    is silently defeated. Same root pattern as #12778, where a blank REDIS_HOST
    defeated its fallback and the backend refused to connect.

    Collapsing blank to ``None`` here means callers get their default rather than
    an empty string that only fails later, at parse time or at use.
    """
    return blank_to_none(os.environ.get(name))


def env_str(name: str, default: str) -> str:
    """Read a string env var, falling back to *default* when absent OR blank (#12782)."""
    return env_raw(name) or default


def env_float(name: str, default: float) -> float:
    """Read a float environment variable, falling back to *default* on absence or bad value.

    Returns *default* silently when the var is absent.
    Logs a warning and returns *default* when the var is set but not a valid float.
    """
    raw = env_raw(name)
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
    raw = env_raw(name)
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
    raw = env_raw(name)
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
    # #12782: a blank export must yield the default, not truthy("") -> False.
    # A flag defaulting to True would otherwise silently flip off.
    raw = env_raw(name)
    return default if raw is None else truthy(raw)
