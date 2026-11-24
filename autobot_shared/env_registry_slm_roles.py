# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""SLM role-provisioning env vars (#22211); imported by env_registry_slm so they register with it."""

from autobot_shared.env_registry import EnvVarSpec, register_env_var

register_env_var(
    EnvVarSpec(
        name="SLM_ROLE_PROVISION_RETRY_COOLDOWN_HOURS",
        type=int,
        default=6,
        description=(
            "Hours the fleet update waits before it provisions a role again after an earlier attempt on the "
            "same node (failed, no credential registered, or left stuck at installing). Stops a node whose "
            "provisioning keeps failing being re-provisioned on every update "
            "(services/pending_role_provisioning.py, #22211). Range: 1-720."
        ),
        component="slm",
        range=(1, 720),
    )
)
