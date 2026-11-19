# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Agent-config read-modify-write under the one config write lock (#21742).

Each writer holds ``services.config_write_lock.CONFIG_WRITE_LOCK`` for its whole
read, write and save, so a concurrent edit or rollback cannot interleave. Synchronous
and lock-holding: never call these while holding an await point open.
"""

from services.config_write_lock import locked_config_write


@locked_config_write
def write_agent_model(config_manager, agent_id: str, base: dict, update) -> dict:
    """Write the new model/provider, save, and return the prior values; *base* holds the defaults."""
    before_config = {
        "model": config_manager.get_nested(f"agents.{agent_id}.model", base["default_model"]),
        "provider": config_manager.get_nested(f"agents.{agent_id}.provider", base["provider"]),
    }
    config_manager.set_nested(f"agents.{agent_id}.model", update.model)
    if update.provider:
        config_manager.set_nested(f"agents.{agent_id}.provider", update.provider)
    config_manager.save_settings()
    return before_config


@locked_config_write
def write_agent_enabled(config_manager, agent_id: str, enabled: bool) -> bool:
    """Write the enabled flag, save, and return the prior flag."""
    before_enabled = config_manager.get_nested(f"agents.{agent_id}.enabled", True)
    config_manager.set_nested(f"agents.{agent_id}.enabled", enabled)
    config_manager.save_settings()
    return before_enabled
