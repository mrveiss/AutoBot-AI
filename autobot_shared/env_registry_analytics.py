# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Codebase-analytics AUTOBOT_* environment variables.

A new ``env_registry_<component>.py`` sibling rather than an addition to
``env_registry_backend.py``, which sits 5 lines under the 600-line ceiling.
Importing this module is what registers them, so ``env_registry`` imports it
for its side effect.
"""

from autobot_shared.env_registry import EnvVarSpec, register_env_var

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_CHAT_TRACE_OUTPUT_MAX_CHARS",
        type=int,
        default=2000,
        description="Characters of one tool result kept in a chat session trace (session_trace.py, #19963).",
        component="backend",
        range=(1, 100000),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_DUPLICATE_ORPHAN_LEASE_SECONDS",
        type=float,
        default=300.0,
        description=(
            "How long an abandoned duplicate scan may keep the single-flight lock after it "
            "was told to stop. Past this the lock is treated as leaked and replaced, so a "
            "scan thread that never exits cannot decline every later call (#18013)."
        ),
        component="backend",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_DUPLICATE_BACKGROUND_TIMEOUT_SECONDS",
        type=float,
        default=3600.0,
        description=(
            "Upper bound for a duplicate scan run by the background (Celery) task. Not the "
            "request deadline: the queued path exists to escape it (#18067)."
        ),
        component="backend",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_DUPLICATE_MAX_RETURNED",
        type=int,
        default=5000,
        description=(
            "Maximum duplicate pairs a scan RETURNS (0 = unlimited). The count and the "
            "statistics always describe every pair found; the analysis reports "
            "`truncated` when the list is shorter (#18067)."
        ),
        component="backend",
    )
)
