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
