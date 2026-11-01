# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Env vars for the approval gate's background work (services/approval_expiry_scheduler.py, #18412)."""

from __future__ import annotations

from autobot_shared.env_registry import EnvVarSpec, register_env_var

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_APPROVAL_EXPIRY_SWEEP_INTERVAL_S",
        type=float,
        default=60.0,
        range=(1, None),
        description=(
            "Seconds between sweeps that move pending approvals past their expires_at to EXPIRED and "
            "resume the work that was waiting on them as expired (services/approval_expiry_scheduler.py, "
            "#18412). A sweep only changes status; it deletes nothing. A past-expiry approve is refused "
            "at decision time regardless, so this bounds how long an unanswered request keeps its "
            "source waiting. Minimum 1."
        ),
        component="approvals",
    )
)
