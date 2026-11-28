# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""AUTOBOT_* variables for the SLM admin file browser (#21029)."""

from autobot_shared.env_registry import EnvVarSpec, register_env_var

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_ADMIN_RAW_CHUNK_BYTES",
        type=int,
        default=64 * 1024,
        description="Read size per chunk when the admin raw download streams a file.",
        component="slm",
        range=(1024, 16 * 1024 * 1024),
    )
)
