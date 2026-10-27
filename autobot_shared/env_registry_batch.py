# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Env vars for the batch-load dispatch (api/batch_dispatch.py, #18765).

A sibling of ``env_registry_backend_services.py``, which sits too close to the file-size ceiling
to take them. Also holds the PR merge-conflict gate retry knobs (#19769).
"""

from __future__ import annotations

from autobot_shared.env_registry import EnvVarSpec, register_env_var

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_BATCH_LOAD_MAX_REQUESTS",
        type=int,
        default=20,
        description=(
            "Most sub-requests one POST /api/batch-jobs/load call may carry "
            "(api/batch_dispatch.py, #18765). A larger batch is refused with 400 before any "
            "sub-request is dispatched. Clamped to 1..100."
        ),
        component="backend",
        range=(1, 100),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_BATCH_LOAD_TIMEOUT_SECONDS",
        type=float,
        default=15.0,
        description=(
            "Per-sub-request timeout for POST /api/batch-jobs/load (api/batch_dispatch.py, "
            "#18765). A sub-request that exceeds it reports 504 in its own result slot; the "
            "rest of the batch is unaffected. Clamped to 1..120."
        ),
        component="backend",
        range=(1.0, 120.0),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_BATCH_LOAD_CONCURRENCY",
        type=int,
        default=5,
        description=(
            "How many sub-requests of one POST /api/batch-jobs/load call run at once "
            "(api/batch_dispatch.py, #18765). The batch as a whole is bounded by "
            "ceil(max_requests / concurrency) * per-sub-request timeout. Clamped to 1..20."
        ),
        component="backend",
        range=(1, 20),
    )
)

register_env_var(
    EnvVarSpec(
        name="PR_CONFLICT_GATE_MAX_ATTEMPTS",
        type=int,
        default=6,
        description=(
            "How many times the PR merge-conflict gate reads a PR whose mergeable state "
            "GitHub reports as unknown before reporting it pending; clamped to 1..10 (#19769)."
        ),
        component="backend",
    )
)

register_env_var(
    EnvVarSpec(
        name="PR_CONFLICT_GATE_BACKOFF_SECONDS",
        type=float,
        default=5.0,
        description=(
            "Initial seconds the PR merge-conflict gate waits between reads of an unknown "
            "mergeable state; doubles each retry, clamped to 0..60 (#19769)."
        ),
        component="backend",
    )
)
