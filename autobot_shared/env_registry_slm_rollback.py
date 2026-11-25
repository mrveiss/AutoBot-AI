# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""SLM rollback (#20214) and role-provisioning (#22211) environment variable registrations.

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
        name="SLM_ROLE_PROVISION_RETRY_COOLDOWN_HOURS",
        type=int,
        default=6,
        description=(
            "Hours the fleet update waits before it provisions a role again after an earlier attempt on the "
            "same node (failed, no credential registered, or left stuck at installing). Stops a node whose "
            "provisioning keeps failing being re-provisioned on every update "
            "(services/pending_role_provisioning.py, #22211)."
        ),
        component="slm",
        range=(1, 720),
    )
)

register_env_var(
    EnvVarSpec(
        name="VNC_PORT_WAIT_SECONDS",
        type=int,
        default=60,
        description=(
            "Seconds the vnc role's verify step waits for the RFB and websockify ports after provisioning, "
            "before xrdp removal is allowed (roles/vnc/vars/main.yml, #22211)."
        ),
        component="slm",
        range=(1, 3600),
    )
)

register_env_var(
    EnvVarSpec(
        name="XRDP_PORT_CLOSE_WAIT_SECONDS",
        type=int,
        default=30,
        description=(
            "Seconds the xrdp removal waits for the RDP port to close after the units stop "
            "(roles/xrdp/defaults/main.yml, #22211)."
        ),
        component="slm",
        range=(1, 3600),
    )
)
