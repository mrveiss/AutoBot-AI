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

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_APPROVAL_DECISION_TTL_SECONDS",
        type=int,
        default=7200,
        description=(
            "How long the per-approval decision claim is held (#20674): longer than the longest command a "
            "decision can start (AUTOBOT_SECURE_COMMAND_TIMEOUT_S, max 3600) plus the retries that persist the "
            "cleared record, so a second worker cannot win the claim while the command runs. Also the crash "
            "safety net: a claim held by a worker that died is freed after this many seconds. A run that fails "
            "releases its claim at once; a successful run keeps it."
        ),
        component="approvals",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_APPROVAL_DECIDED_MARKER_TTL_SECONDS",
        type=int,
        default=2592000,
        description=(
            "How long the durable decided marker of an approval lives (#21174), keyed by its original command id "
            "and written atomically with the decision claim. Must outlast the session record (7 days) and the "
            "chat-history window, so a rebuild from chat history never makes a decided approval decidable "
            "again. A failed run clears it with its claim; a successful run keeps it."
        ),
        component="approvals",
    )
)
