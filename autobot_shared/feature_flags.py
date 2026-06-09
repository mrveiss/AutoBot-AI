#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Feature Flag Utilities
======================

Convenience helpers for checking and enforcing subsystem feature flags.
All flag values are read from ``FeatureConfig`` (SSOT), which in turn reads
``AUTOBOT_FEATURE_*`` environment variables.

Subsystem flags (all default ``True``):

* ``npu``              — NPU / OpenVINO acceleration (AUTOBOT_FEATURE_NPU)
* ``voice``            — TTS / STT processing (AUTOBOT_FEATURE_VOICE)
* ``browser``          — browser automation via Playwright (AUTOBOT_FEATURE_BROWSER)
* ``computer_vision``  — CV / image processing (AUTOBOT_FEATURE_COMPUTER_VISION)
* ``training``         — model training / fine-tuning (AUTOBOT_FEATURE_TRAINING)
* ``osint``            — OSINT sweep engine (AUTOBOT_FEATURE_OSINT)

Usage::

    from autobot_shared.feature_flags import is_feature_enabled, require_feature

    if is_feature_enabled("npu"):
        run_npu_inference()

    @require_feature("voice")
    def synthesize_speech(text: str) -> bytes:
        ...

Issue: #3017 — No feature flag system for optional subsystems
"""

from __future__ import annotations

import functools
import logging
from typing import Callable, List, TypeVar

logger = logging.getLogger(__name__)

# Mapping of public flag name → FeatureConfig attribute name.
# Extend this dict whenever a new subsystem flag is added to FeatureConfig.
_SUBSYSTEM_FLAG_MAP: dict[str, str] = {
    "npu": "npu_enabled",
    "voice": "voice_enabled",
    "browser": "browser_enabled",
    "computer_vision": "computer_vision_enabled",
    "training": "training_enabled",
    "osint": "osint_enabled",
}

F = TypeVar("F", bound=Callable)


class FeatureDisabledError(RuntimeError):
    """Raised by ``require_feature`` when a subsystem flag is disabled."""

    def __init__(self, feature_name: str) -> None:
        super().__init__(
            f"Subsystem '{feature_name}' is disabled on this node. "
            f"Set AUTOBOT_FEATURE_{feature_name.upper()}=true to enable it."
        )
        self.feature_name = feature_name


def _get_feature_config():
    """Return the live FeatureConfig instance.

    Imported lazily to avoid circular imports at module load time.
    """
    from autobot_shared.ssot_config import get_config  # noqa: PLC0415

    return get_config().feature


def is_feature_enabled(feature_name: str) -> bool:
    """Return ``True`` when *feature_name* is enabled on this node.

    Args:
        feature_name: One of the subsystem keys defined in ``_SUBSYSTEM_FLAG_MAP``
                      (e.g. ``"npu"``, ``"voice"``).

    Returns:
        Boolean flag value from FeatureConfig.

    Raises:
        ValueError: If *feature_name* is not a recognised subsystem flag.
    """
    attr = _SUBSYSTEM_FLAG_MAP.get(feature_name)
    if attr is None:
        known = sorted(_SUBSYSTEM_FLAG_MAP)
        raise ValueError(f"Unknown feature flag '{feature_name}'. Known flags: {known}")
    enabled: bool = getattr(_get_feature_config(), attr)
    logger.debug("Feature '%s' is %s", feature_name, "enabled" if enabled else "disabled")
    return enabled


def get_enabled_features() -> List[str]:
    """Return a sorted list of all enabled subsystem feature names.

    Returns:
        Sorted list of subsystem names that are currently enabled.
    """
    feature_cfg = _get_feature_config()
    enabled = [name for name, attr in _SUBSYSTEM_FLAG_MAP.items() if getattr(feature_cfg, attr)]
    result = sorted(enabled)
    logger.debug("Enabled subsystem features: %s", result)
    return result


def require_feature(feature_name: str) -> Callable[[F], F]:
    """Decorator — raise ``FeatureDisabledError`` when the subsystem is off.

    Usage::

        @require_feature("browser")
        def open_browser_session() -> None:
            ...

    Args:
        feature_name: Subsystem flag name (e.g. ``"browser"``).

    Returns:
        Decorator that wraps the target function with a feature gate check.

    Raises:
        ValueError: At decoration time if *feature_name* is unrecognised.
        FeatureDisabledError: At call time if the subsystem is disabled.
    """
    # Validate the flag name eagerly so typos surface at import time.
    if feature_name not in _SUBSYSTEM_FLAG_MAP:
        known = sorted(_SUBSYSTEM_FLAG_MAP)
        raise ValueError(f"Unknown feature flag '{feature_name}'. Known flags: {known}")

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if not is_feature_enabled(feature_name):
                raise FeatureDisabledError(feature_name)
            return func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator


__all__ = [
    "FeatureDisabledError",
    "is_feature_enabled",
    "get_enabled_features",
    "require_feature",
]
