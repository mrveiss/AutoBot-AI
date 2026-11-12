# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
"""Environment variable helpers shared across AutoBot services."""

import logging
import math
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

    :func:`blank_to_none` decides *whether* the value is blank — one definition of
    "blank" for both routes — but the value itself is returned verbatim. Returning
    ``blank_to_none``'s stripped text instead silently trimmed every real env var
    (#12899), which corrupts any value whose surrounding whitespace is significant,
    such as a password or a delimiter. Numeric parsing is unaffected either way:
    ``int``/``float``/:func:`truthy` all tolerate surrounding whitespace.
    """
    raw = os.environ.get(name)
    return raw if blank_to_none(raw) is not None else None


def env_str(name: str, default: str) -> str:
    """Read a string env var, falling back to *default* when absent OR blank (#12782)."""
    return env_raw(name) or default


def env_float(name: str, default: float, *, reject_nan: bool = False) -> float:
    """Read a float environment variable, falling back to *default* on absence or bad value.

    Returns *default* silently when the var is absent.
    Logs a warning and returns *default* when the var is set but not a valid float.
    ``reject_nan=True`` also treats ``nan`` (which ``float()`` accepts) as invalid;
    callers feeding the value into comparisons or decay maths need that, since a
    NaN compares false against everything. Default False keeps prior behaviour.
    """
    raw = env_raw(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError:
        logger.warning("Invalid %s=%r; using default %s", name, raw, default)
        return default
    if reject_nan and value != value:
        logger.warning("Invalid %s=%r (NaN); using default %s", name, raw, default)
        return default
    return value


def env_int(name: str, default: int) -> int:
    """Read an integer environment variable, falling back to *default* on absence or bad value.

    Returns *default* silently when the var is absent.
    Logs a warning and returns *default* when the var is set but not a valid integer.
    """
    return parse_int_or_default(name, env_raw(name), default)


def parse_int_or_default(name: str, raw: object, default: int) -> int:
    """Parse *raw* as an int, returning *default* (with a warning) when absent, blank or unparseable (#20683).

    The single definition of "tolerant int parse" for both routes: :func:`env_int` feeds it
    ``os.environ``; pydantic ``mode="before"`` field validators feed it the value settings
    loading hands them, so a bad value falls back instead of raising ``ValidationError``.
    """
    if blank_to_none(raw) is None:
        return default
    try:
        return int(str(raw).strip())
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
    return _clamped(name, value, min_v, max_v)


def _clamped(name: str, value, min_v, max_v):
    """Clamp *value*, and say so when clamping changed it.

    A malformed value already warns; a well-formed but out-of-range one did not,
    so a misconfigured ``0`` or ``-1`` was accepted in silence and the operator
    who set it never learned that it had no effect (#15778 review). The clamp
    itself is the right behaviour -- refusing to boot over a bad tuning knob is
    worse -- but a silent correction is indistinguishable from a value that was
    honoured.
    """
    clamped = value
    if min_v is not None:
        clamped = max(min_v, clamped)
    if max_v is not None:
        clamped = min(max_v, clamped)
    if clamped != value:
        logger.warning("%s=%r is outside [%s, %s]; using %r", name, value, min_v, max_v, clamped)
    return clamped


def within_range(name: str, value, bounds: tuple | None) -> bool:
    """True when numeric *value* lies in inclusive ``(min, max)`` *bounds* (``None`` = open end).

    Out of range warns naming the variable and the range only; the value is
    omitted because a registry spec carries no secret marker (#20722).
    Non-numeric values and ``bounds=None`` are never checked.
    """
    if bounds is None or isinstance(value, bool) or not isinstance(value, (int, float)):
        return True
    min_v, max_v = bounds
    if (min_v is None or value >= min_v) and (max_v is None or value <= max_v):
        return True
    logger.warning("%s is outside [%s, %s]; using the default", name, min_v, max_v)
    return False


def env_float_clamped(
    name: str,
    default: float,
    min_v: float | None = None,
    max_v: float | None = None,
    *,
    positive_finite: bool = False,
) -> float:
    """Read a float environment variable with optional min/max clamping.

    ``positive_finite=True`` rejects a value that is NaN, infinite or <= 0 and
    falls back to *default* with a warning, rather than clamping it. Clamping is
    wrong for a timeout: ``float("nan")`` and ``"inf"`` parse cleanly and slip
    past min/max comparisons, and aiohttp treats 0 and NaN as "no timer" and a
    negative as "already expired" (#12979).

    Mirrors :func:`env_int_clamped` for the float case (#14524): a bare
    :func:`env_float` accepts 0 and negatives, and for a value used as a
    signal-escalation grace period, 0 collapses the grace entirely (SIGKILL
    fires with no chance for a well-behaved child to exit on SIGTERM first).
    """
    raw = env_raw(name)
    if raw is None:
        value = default
    else:
        try:
            value = float(raw)
        except ValueError:
            logger.warning("Invalid %s=%r; using %s", name, raw, default)
            value = default
        if positive_finite and not (math.isfinite(value) and value > 0):
            logger.warning("%s=%r must be a positive finite number; using %s", name, raw, default)
            value = default
    return _clamped(name, value, min_v, max_v)


def env_registered(name: str, *, positive_finite: bool = False):
    """A registered numeric env var, read within the range its registry entry declares.

    The default and the ``(min, max)`` come from ``REGISTRY``, so the registered range is the one enforced; a
    malformed value falls back to the default and an out-of-range one is clamped, each with a warning.
    ``positive_finite`` (floats only) also rejects NaN, infinity and non-positive values.
    """
    from autobot_shared.env_registry import REGISTRY

    spec = REGISTRY[name]
    low, high = spec.range or (None, None)
    if spec.type is int:
        return env_int_clamped(name, spec.default, low, high)
    return env_float_clamped(name, spec.default, low, high, positive_finite=positive_finite)


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


_FALSY_VALUES: frozenset[str] = frozenset({"0", "false", "no", "off"})

#: What :func:`env_flag` does with a value that is neither truthy nor falsy (``ture``, ``enabled``).
ON_INVALID_MODES = ("default", "false", "raise")


def env_flag(name: str, default: bool = False, *, on_invalid: str = "default") -> bool:
    """Read a boolean environment variable via the canonical truthy/falsy sets.

    Absent or blank -> *default* (#12782). A recognised truthy value -> True; a recognised
    falsy value (``0/false/no/off``) -> False. Anything else is a typo, and a typo must not
    silently decide a flag, so *on_invalid* says what happens (a warning is always logged):

    * ``"default"`` (the default) -- keep *default*. A protection that defaults on stays on.
    * ``"false"`` -- read it as False. For a flag whose SAFE value is False although it
      defaults True (an auto-approve switch): a typo must not widen what it permits.
    * ``"raise"`` -- ``ValueError``, for flags where guessing is worse than refusing to start.
    """
    if on_invalid not in ON_INVALID_MODES:
        raise ValueError(f"on_invalid must be one of {ON_INVALID_MODES}, got {on_invalid!r}")
    raw = env_raw(name)
    if raw is None:
        return default
    if truthy(raw):
        return True
    if raw.strip().lower() in _FALSY_VALUES:
        return False
    if on_invalid == "raise":
        raise ValueError(f"{name}={raw!r} is not a boolean (use 1/true/yes/on or 0/false/no/off)")
    fallback = default if on_invalid == "default" else False
    logger.warning("Invalid %s=%r; using %s", name, raw, fallback)
    return fallback
