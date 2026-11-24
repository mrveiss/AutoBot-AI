# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The telemetry opt-in/out state: one reader for every consumer (#9035, #21684).

The admin consent POST saves the choice to the config file; it never touches the SSOT settings object
(``autobot_shared.ssot_config.config.telemetry``), which is built from env / ``.env``. A consumer reading the SSOT
object alone therefore ignores an opt-out saved at runtime. The saved value wins here and the SSOT setting is only the
default until one is saved.
"""

from config import config_manager
from type_defs.common import Metadata


def persisted_telemetry() -> Metadata:
    """The telemetry section saved by the admin consent POST (empty until one was saved)."""
    persisted = config_manager.get_nested("telemetry", {})
    return dict(persisted) if isinstance(persisted, dict) else {}


def get_telemetry_settings() -> Metadata:
    """The effective ``enabled`` / ``anonymous_usage_stats`` / ``first_run_prompt_shown`` values."""
    from autobot_shared.ssot_config import config as ssot

    defaults = {
        "enabled": ssot.telemetry.enabled,
        "anonymous_usage_stats": ssot.telemetry.anonymous_usage_stats,
        "first_run_prompt_shown": ssot.telemetry.first_run_prompt_shown,
    }
    saved = persisted_telemetry()
    return {key: saved[key] if saved.get(key) is not None else value for key, value in defaults.items()}
