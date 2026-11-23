# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Environment variables of the stale code-sync file cleanup (#22033).

A sibling of ``env_registry_slm.py``, which has no room left under the 600-line ceiling.
"""

from __future__ import annotations

from autobot_shared.env_registry import EnvVarSpec, register_env_var

register_env_var(
    EnvVarSpec(
        name="SLM_STALE_SYNC_FILES_MAX_PER_PROPOSAL",
        type=int,
        default=200,
        description=(
            "Most files one stale-file cleanup proposal lists (one proposal per old sync location per node); "
            "the rest are proposed after this one is decided (slm_stale_file_actions.py, #22033)."
        ),
        component="slm",
        range=(1, 1000),
    )
)

register_env_var(
    EnvVarSpec(
        name="SLM_STALE_SYNC_FILES_SSH_TIMEOUT_SECONDS",
        type=float,
        default=120.0,
        description="Seconds one stale-file listing or removal over ssh may run (stale_sync_remote.py, #22033).",
        component="slm",
        range=(5.0, 900.0),
    )
)
