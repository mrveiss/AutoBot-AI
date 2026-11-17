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


def keep_live_secrets(snapshot: Dict[str, Any], live: Dict[str, Any]) -> Dict[str, Any]:
    """Return *snapshot* with every placeholder value replaced by the live value.

    A placeholder with no live counterpart is dropped, never written (#18478).
    """
    restored: Dict[str, Any] = {}
    for key, value in snapshot.items():
        live_value = live.get(key) if isinstance(live, dict) else None
        if isinstance(value, str) and value in _PLACEHOLDERS:
            if key in (live or {}):
                restored[key] = live_value
        elif isinstance(value, dict):
            restored[key] = keep_live_secrets(value, live_value if isinstance(live_value, dict) else {})
        else:
            restored[key] = value
    return restored


def _apply_agent(agent_id: str, snapshot: Dict[str, Any]) -> None:
    """Write the snapshotted agent fields through the agent config writer."""
    from api.agent_config import DEFAULT_AGENT_CONFIGS
    from config import config_manager

    if agent_id not in DEFAULT_AGENT_CONFIGS:
        raise UnsupportedRollbackTarget(f"unknown agent '{agent_id}'")
    for field in _AGENT_FIELDS:
        if field in snapshot and snapshot[field] is not None and snapshot[field] not in _PLACEHOLDERS:
            config_manager.set_nested(f"agents.{agent_id}.{field}", snapshot[field])
    config_manager.save_settings()
    ConfigService.clear_cache()


def _apply_system(entity_id: str, snapshot: Dict[str, Any]) -> None:
    """Write a system snapshot through the writer that owns that entity."""
    if entity_id == "backend":
        live = ConfigService.get_backend_settings()
        ConfigService.update_backend_settings(keep_live_secrets(snapshot, live))
    elif entity_id in _FULL_CONFIG_IDS:
        live = ConfigService.get_full_config()
        ConfigService.save_full_config(keep_live_secrets(copy.deepcopy(snapshot), live))
    else:
        raise UnsupportedRollbackTarget(f"no live config writer for system/{entity_id}")
    ConfigService.clear_cache()


def apply_snapshot(entity_type: str, entity_id: str, snapshot: Dict[str, Any]) -> None:
    """Restore *snapshot* to the live config for the entity, or raise (#18478)."""
    if entity_type == "agent":
        _apply_agent(entity_id, snapshot)
    elif entity_type == "system":
        _apply_system(entity_id, snapshot)
    else:
        raise UnsupportedRollbackTarget(f"unsupported entity type '{entity_type}'")
    logger.info("Applied config snapshot to live %s/%s", entity_type, entity_id)
