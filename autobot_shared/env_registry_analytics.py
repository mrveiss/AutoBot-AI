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

# --- indexing subprocess watchdog (#18057) ------------------------------------

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_INDEXING_HARD_TIMEOUT",
        type=int,
        default=1800,
        description="Seconds a codebase indexing subprocess may run in total before it is killed.",
        component="analytics",
        range=(60, 86400),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_INDEXING_PROGRESS_TIMEOUT",
        type=int,
        default=300,
        description="Seconds a codebase indexing subprocess may show no progress before it is killed.",
        component="analytics",
        range=(30, 14400),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_INDEXING_WATCHDOG_INTERVAL",
        type=int,
        default=30,
        description="Seconds between the indexing watchdog's progress checks.",
        component="analytics",
        range=(1, 300),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_CODE_INDEX_RUN_TIMEOUT_SECONDS",
        type=float,
        default=180.0,
        description="Seconds the code-index subprocess may run before the analytics run reports it timed out (#18056).",
        component="analytics",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_MODEL_PULL_TIMEOUT_SECONDS",
        type=float,
        default=1800.0,
        description=(
            "Seconds one `ollama pull` may run in the model optimizer before it is reported timed out (#18056)."
        ),
        component="analytics",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_CODE_TOOL_MAX_ITEMS",
        type=int,
        default=200,
        description=(
            "Entries kept per list in one code.* MCP tool response (code_graph_tools.py, #21327); "
            "the rest are counted in the response's omitted field."
        ),
        component="backend",
        range=(1, 10000),
    )
)
