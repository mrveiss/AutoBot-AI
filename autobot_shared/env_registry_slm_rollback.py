# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""SLM rollback environment variable registrations (#20214).

A sibling of ``env_registry_slm.py``, which has no room left under the 600-line ceiling.
"""

from __future__ import annotations

from autobot_shared.env_registry import EnvVarSpec, register_env_var

register_env_var(
    EnvVarSpec(
        name="SLM_ROLLBACK_ENABLED",
        type=bool,
        default=False,
        description="Offer the SLM rollback to an earlier commit (api/code_rollback.py). Off until a host test.",
        component="slm",
    )
)

register_env_var(
    EnvVarSpec(
        name="SLM_ROLLBACK_CANDIDATE_LIMIT",
        type=int,
        default=50,
        description="Newest commits the rollback picker offers (services/rollback_commits.py).",
        component="slm",
        range=(1, 500),
    )
)

register_env_var(
    EnvVarSpec(
        name="SLM_ROLLBACK_STATEMENT_TIMEOUT_MS",
        type=int,
        default=10000,
        description="Server-side statement timeout (ms) for the rollback's migration reads (rollback_migrations.py).",
        component="slm",
        range=(1000, 300000),
    )
)

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
