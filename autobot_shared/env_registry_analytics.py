# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Codebase-analytics AUTOBOT_* environment variables (added with #18013; sibling rationale recorded per #18571).

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
            "Maximum duplicate clusters a scan RETURNS (0 = unlimited). The count and the "
            "statistics always describe every cluster found; the analysis reports "
            "`truncated` when the list is shorter (#18067)."
        ),
        component="backend",
    )
)

# --- indexing subprocess watchdog (#18057) ------------------------------------

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_INDEXING_ABANDON_GRACE_SECONDS",
        type=int,
        default=300,
        description="Seconds past the hard timeout before a still-running indexing run reads as abandoned.",
        component="analytics",
        range=(30, 86400),
    )
)

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
        name="AUTOBOT_AGENT_FEED_RECORDS",
        type=int,
        default=20,
        description="Task records read per agent for the Agent Activity feeds (agent_activity_feed.py, #21270).",
        component="analytics",
        range=(1, 200),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_AGENT_FEED_MAX_AGENTS",
        type=int,
        default=200,
        description="Agents whose activity feed one /agents/status call reads; the rest report not-measured (#21270).",
        component="analytics",
        range=(1, 5000),
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

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_CALL_GRAPH_SUMMARY_TTL",
        type=int,
        default=2592000,
        description=(
            "Seconds the persisted per-source call-graph summary (#20945) is kept after the last build. Unlike the "
            "5-minute call-graph cache it outlives it, so the knowledge graph can report a codebase's size without "
            "rebuilding the graph; a rebuild overwrites it. Clamped to 3600-7776000."
        ),
        component="analytics",
        range=(3600, 7776000),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_API_CALL_PATTERNS_MAX",
        type=int,
        default=10000,
        description=(
            "Most recent API calls the in-process analytics state keeps (analytics_controller.py). Older calls drop "
            "off; the persisted copy in Redis is trimmed to the same count (#21684)."
        ),
        component="analytics",
        range=(100, 1000000),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_BUG_PREDICTION_MAX_PATTERN_LENGTH",
        type=int,
        default=128,
        description=(
            "Longest include_pattern (characters) the bug-prediction routes accept before it reaches the file walk "
            "(#18030); a longer one is refused with 422."
        ),
        component="analytics",
        range=(1, 1024),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_VOICE_REALTIME_ABANDONED_SESSION_SECONDS",
        type=int,
        default=7200,
        description=(
            "How long a realtime voice session that never ended (a dropped connection) stays in the in-memory "
            "session map before it is evicted (voice_realtime_telemetry.py, #21678). Never effective below "
            "AUTOBOT_VOICE_REALTIME_MAX_SECONDS plus a 300 s margin. Finished sessions are released at once."
        ),
        component="voice",
        range=(60, 604800),
    )
)
