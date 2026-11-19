# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Direct ``config_manager`` writes under the one config write lock (#21858).

Each helper holds ``services.config_write_lock.CONFIG_WRITE_LOCK`` for its whole
read, write and save, so it cannot interleave with a ``ConfigService`` write or a
rollback. Synchronous: never call these while holding an await point open.
"""

from services.config_write_lock import locked_config_write


@locked_config_write
def set_nested_and_save(config_manager, key: str, value) -> None:
    """Write *value* at *key* and save, as one locked operation."""
    config_manager.set_nested(key, value)
    config_manager.save_settings()


@locked_config_write
def merge_nested_and_save(config_manager, key: str, changes: dict) -> dict:
    """Read the dict at *key*, merge *changes* into it, save, and return the merged dict."""
    merged = config_manager.get_nested(key, {})
    merged.update(changes)
    config_manager.set_nested(key, merged)
    config_manager.save_settings()
    return merged
