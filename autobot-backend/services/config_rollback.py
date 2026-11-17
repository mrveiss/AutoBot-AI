# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Apply a stored config snapshot to the live config store (#18478).

``ConfigRevisionService.rollback_to_revision`` calls :func:`apply_snapshot`
before it records a rollback row, so a failed apply leaves no row. Stored
snapshots are redacted, so any placeholder value keeps the current live value
instead of overwriting a secret.
"""

import copy
from typing import Any, Dict

from autobot_shared.logging_manager import get_logger
from autobot_shared.secret_redaction import LEGACY_PLACEHOLDERS, REDACTED_PLACEHOLDER
from services.config_service import ConfigService

logger = get_logger(__name__)

_PLACEHOLDERS = frozenset({REDACTED_PLACEHOLDER}) | LEGACY_PLACEHOLDERS
_FULL_CONFIG_IDS = frozenset({"settings", "config", "hardware_priority", "telemetry_settings"})
_AGENT_FIELDS = ("model", "provider", "enabled")


class UnsupportedRollbackTarget(Exception):
    """The entity type/id has no live config writer to roll back to (#18478)."""


def _is_placeholder(value: Any) -> bool:
    return isinstance(value, str) and value in _PLACEHOLDERS


def _restore_value(value: Any, live_value: Any) -> Any:
    """Restore one value: placeholders keep the live value, containers recurse."""
    if isinstance(value, dict):
        return keep_live_secrets(value, live_value if isinstance(live_value, dict) else {})
    if isinstance(value, list):
        live_items = live_value if isinstance(live_value, list) else []
        return [_restore_value(v, live_items[i] if i < len(live_items) else None) for i, v in enumerate(value)]
    return value


def keep_live_secrets(snapshot: Dict[str, Any], live: Dict[str, Any]) -> Dict[str, Any]:
    """Return *snapshot* with every placeholder value replaced by the live value.

    Recurses into dicts and lists. A placeholder with no live counterpart is
    dropped from a dict, never written (#18478).
    """
    live = live if isinstance(live, dict) else {}
    restored: Dict[str, Any] = {}
    for key, value in snapshot.items():
        if _is_placeholder(value):
            if key in live:
                restored[key] = live[key]
        else:
            restored[key] = _restore_value(value, live.get(key))
    return restored


def _apply_agent(agent_id: str, snapshot: Dict[str, Any]) -> None:
    """Write the snapshotted agent fields; restore the prior values if a write fails."""
    from api.agent_config import DEFAULT_AGENT_CONFIGS
    from config import config_manager

    if agent_id not in DEFAULT_AGENT_CONFIGS:
        raise UnsupportedRollbackTarget(f"unknown agent '{agent_id}'")
    paths = {
        f"agents.{agent_id}.{f}": snapshot[f]
        for f in _AGENT_FIELDS
        if f in snapshot and snapshot[f] is not None and not _is_placeholder(snapshot[f])
    }
    missing = object()
    prior = {path: config_manager.get_nested(path, missing) for path in paths}
    try:
        for path, value in paths.items():
            config_manager.set_nested(path, value)
        config_manager.save_settings()
    except Exception:
        for path, old in prior.items():
            if old is not missing:
                config_manager.set_nested(path, old)
        raise
    ConfigService.clear_cache()


def _changed_entries(snapshot: Dict[str, Any], before: Dict[str, Any] | None) -> Dict[str, Any]:
    """Keys the revision itself set: those whose value differs from its before snapshot."""
    if before is None:
        return dict(snapshot)
    return {k: v for k, v in snapshot.items() if before.get(k) != v}


def _apply_system(entity_id: str, snapshot: Dict[str, Any], before: Dict[str, Any] | None) -> None:
    """Merge a system snapshot's delta into the LIVE config; never overwrite it whole."""
    from config.loader import deep_merge

    delta = _changed_entries(snapshot, before)
    if entity_id == "backend":
        live = ConfigService.get_backend_settings()
        ConfigService.update_backend_settings(deep_merge(copy.deepcopy(live), keep_live_secrets(delta, live)))
    elif entity_id in _FULL_CONFIG_IDS:
        live = ConfigService.get_full_config()
        ConfigService.save_full_config(deep_merge(copy.deepcopy(live), keep_live_secrets(delta, live)))
    else:
        raise UnsupportedRollbackTarget(f"no live config writer for system/{entity_id}")
    ConfigService.clear_cache()


def apply_snapshot(
    entity_type: str,
    entity_id: str,
    snapshot: Dict[str, Any],
    before: Dict[str, Any] | None = None,
) -> None:
    """Restore *snapshot* to the live config for the entity, or raise (#18478)."""
    if entity_type == "agent":
        _apply_agent(entity_id, snapshot)
    elif entity_type == "system":
        _apply_system(entity_id, snapshot, before)
    else:
        raise UnsupportedRollbackTarget(f"unsupported entity type '{entity_type}'")
    logger.info("Applied config snapshot to live %s/%s", entity_type, entity_id)
