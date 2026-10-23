# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one home of the web research settings (#19226).

The settings API, the startup initializer and ``WebResearcher`` all read and write the
``web_research`` config section through this module. Before it, PUT /web-research/settings
wrote most fields to ``agents.research.*``, which nothing at runtime reads, and dropped the
privacy flags entirely.

API field names are the keys of ``DEFAULTS``; ``_CONFIG_KEYS`` maps the two whose stored key
differs.
"""

import copy
from typing import Any, Dict, Protocol

SECTION = "web_research"

# Web research is on until an admin turns it off: the startup initializer enabled it
# unconditionally before #19226, so an install that never saved a value keeps that behaviour.
DEFAULTS: Dict[str, Any] = {
    "enabled": True,
    "require_user_confirmation": True,
    "preferred_method": "basic",
    "max_results": 5,
    "timeout_seconds": 30,
    "auto_research_threshold": 0.3,
    "rate_limit_requests": 5,
    "rate_limit_window": 60,
    "daily_limit": 50,
    "quality_threshold": 0.5,
    "store_results_in_kb": True,
    "filter_adult_content": True,
    "anonymize_requests": True,
}

_CONFIG_KEYS = {"daily_limit": "daily_research_limit", "quality_threshold": "min_result_quality"}

# Fields the old PUT wrote to ``agents.research.*`` only; a value saved there before #19226
# is carried over when ``web_research`` has none, so no saved setting is lost.
_LEGACY_SECTION = "agents.research"
_LEGACY_FIELDS = (
    "enabled",
    "preferred_method",
    "max_results",
    "timeout_seconds",
    "rate_limit_requests",
    "rate_limit_window",
)


class ConfigManagerLike(Protocol):
    def get_nested(self, path: str, default: Any = None) -> Any: ...
    def set_nested(self, path: str, value: Any) -> None: ...
    def save_settings(self) -> None: ...


def _config_key(field: str) -> str:
    return _CONFIG_KEYS.get(field, field)


def load_settings(manager: ConfigManagerLike) -> Dict[str, Any]:
    """Every web research setting, by API field name: stored, else legacy, else default."""
    stored = manager.get_nested(SECTION, {}) or {}
    legacy = manager.get_nested(_LEGACY_SECTION, {}) or {}
    settings = {}
    for field, default in DEFAULTS.items():
        key = _config_key(field)
        if key in stored:
            settings[field] = stored[key]
        elif field in _LEGACY_FIELDS and field in legacy:
            settings[field] = legacy[field]
        else:
            settings[field] = default
    return settings


def save_settings(manager: ConfigManagerLike, changes: Dict[str, Any]) -> Dict[str, Any]:
    """Persist ``changes`` (API field names) to the ``web_research`` section; returns the full set."""
    unknown = set(changes) - set(DEFAULTS)
    if unknown:
        raise ValueError(f"unknown web research settings: {sorted(unknown)}")
    before = copy.deepcopy(manager.get_nested(SECTION, None))
    for field, value in changes.items():
        manager.set_nested(f"{SECTION}.{_config_key(field)}", value)
    try:
        manager.save_settings()
    except Exception:
        # A failed save must not leave the unsaved values in memory for the next read to report.
        manager.set_nested(SECTION, before if before is not None else {})
        raise
    return load_settings(manager)


def researcher_config(manager: ConfigManagerLike) -> Dict[str, Any]:
    """The raw section ``WebResearcher`` is built from, with every setting filled in."""
    section = dict(manager.get_nested(SECTION, {}) or {})
    for field, value in load_settings(manager).items():
        section[_config_key(field)] = value
    return section
