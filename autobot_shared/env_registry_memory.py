# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Memory / fact-lane / tool-output-spill / edit-miss-search AUTOBOT_* environment variable registrations.

New sibling module (#17855), following the pattern ``env_registry_slm.py``'s
docstring records: ``env_registry.py`` is closed to new entries.

These twelve were read through private ``os.environ.get`` parsers in
``agent_loop/tool_output_spill.py``, ``memory/essential_story.py`` and
``knowledge/facts.py`` until #17855 moved them onto
``autobot_shared.env_utils``. That made them visible to
``check_env_var_registry.py`` for the first time; this module answers it.

Registration contract (import side effect, ordering): see ``env_registry`` (#16415).
"""

from __future__ import annotations

from autobot_shared import env_registry

env_registry.register_env_var(
    env_registry.EnvVarSpec(
        name="AUTOBOT_TOOL_OUTPUT_SPILL",
        type=bool,
        default=False,
        description=(
            "Master switch for spilling oversized tool output to disk and returning a short excerpt "
            "plus an anchor (agent_loop/tool_output_spill.py)."
        ),
        component="agent_loop",
    )
)

env_registry.register_env_var(
    env_registry.EnvVarSpec(
        name="AUTOBOT_TOOL_OUTPUT_SPILL_THRESHOLD",
        type=int,
        default=8000,
        description=(
            "Tool output longer than this many characters is spilled instead of inlined "
            "(agent_loop/tool_output_spill.py)."
        ),
        component="agent_loop",
    )
)

env_registry.register_env_var(
    env_registry.EnvVarSpec(
        name="AUTOBOT_TOOL_OUTPUT_SPILL_EXCERPT",
        type=int,
        default=2000,
        description=(
            "Characters of a spilled tool result kept inline as the excerpt; clamped below the spill "
            "threshold (agent_loop/tool_output_spill.py)."
        ),
        component="agent_loop",
    )
)

env_registry.register_env_var(
    env_registry.EnvVarSpec(
        name="AUTOBOT_TOOL_OUTPUT_SPILL_MAX",
        type=int,
        default=5000000,
        description=(
            "Largest payload written to a spill artifact; above this the stored copy is truncated and "
            "marked (agent_loop/tool_output_spill.py)."
        ),
        component="agent_loop",
    )
)

env_registry.register_env_var(
    env_registry.EnvVarSpec(
        name="AUTOBOT_TOOL_OUTPUT_SPILL_MAX_WINDOW",
        type=int,
        default=8000,
        description=(
            "Ceiling on one re-read of a spilled artifact, so a huge limit cannot hand the whole "
            "artifact back into context (agent_loop/tool_output_spill.py)."
        ),
        component="agent_loop",
    )
)

env_registry.register_env_var(
    env_registry.EnvVarSpec(
        name="AUTOBOT_ESSENTIAL_STORY_REINFORCE",
        type=bool,
        default=True,
        description=(
            "Rank always-loaded facts by usage-aware effective score instead of static quality_score "
            "alone; off reproduces the pre-A2 ordering (memory/essential_story.py)."
        ),
        component="memory",
    )
)

env_registry.register_env_var(
    env_registry.EnvVarSpec(
        name="AUTOBOT_ESSENTIAL_STORY_REINFORCE_WEIGHT",
        type=float,
        default=0.3,
        description=(
            "Weight of recall frequency and recency in the effective fact score; 0 reproduces the "
            "static quality_score ordering (memory/essential_story.py)."
        ),
        component="memory",
    )
)

env_registry.register_env_var(
    env_registry.EnvVarSpec(
        name="AUTOBOT_ESSENTIAL_STORY_RECENCY_HALFLIFE_SECONDS",
        type=float,
        default=2592000.0,
        description=(
            "Half-life in seconds of the recency boost on a recalled fact (memory/essential_story.py). "
            "Default 30 days."
        ),
        component="memory",
    )
)

env_registry.register_env_var(
    env_registry.EnvVarSpec(
        name="AUTOBOT_FACTS_PRUNE_QUALITY_FLOOR",
        type=float,
        default=0.1,
        description=("A fact is prunable only below this quality score (knowledge/facts.py consolidation)."),
        component="knowledge",
    )
)

env_registry.register_env_var(
    env_registry.EnvVarSpec(
        name="AUTOBOT_FACTS_PRUNE_MAX_AGE_DAYS",
        type=int,
        default=180,
        description=("A fact is prunable only once older than this many days (knowledge/facts.py consolidation)."),
        component="knowledge",
    )
)

env_registry.register_env_var(
    env_registry.EnvVarSpec(
        name="AUTOBOT_FACTS_PRUNE_SCAN_LIMIT",
        type=int,
        default=5000,
        description=("Most facts examined in one consolidation pass (knowledge/facts.py)."),
        component="knowledge",
    )
)

env_registry.register_env_var(
    env_registry.EnvVarSpec(
        name="AUTOBOT_FACTS_PRUNE_MAX_PER_RUN",
        type=int,
        default=100,
        description=(
            "Circuit breaker: a consolidation run that would prune more facts than this refuses and "
            "logs loudly (knowledge/facts.py)."
        ),
        component="knowledge",
    )
)

env_registry.register_env_var(
    env_registry.EnvVarSpec(
        name="AUTOBOT_MEMORY_GRAPH_SCAN_KEY_BUDGET",
        type=int,
        default=20000,
        description=(
            "Most memory:entity:* keys one scan-fallback call (_fallback_search, get_entities_as_of) may "
            "examine before it stops and returns what it found, logging a warning (autobot_memory_graph/queries.py)."
        ),
        component="memory_graph",
    )
)

env_registry.register_env_var(
    env_registry.EnvVarSpec(
        name="AUTOBOT_EDIT_MISS_OLD_TEXT_MAX_CHARS",
        type=int,
        default=2000,
        description=(
            "Longest edit_file old_text that the closest-span search runs for after a miss. A longer "
            "old_text still fails as a miss, and the error says the search was capped (api/filesystem_edit.py, #19463)."
        ),
        component="filesystem_mcp",
    )
)

env_registry.register_env_var(
    env_registry.EnvVarSpec(
        name="AUTOBOT_EDIT_MISS_MAX_WINDOWS",
        type=int,
        default=2000,
        description=(
            "Most line windows that the edit_file closest-span search compares after a miss before it stops "
            "and reports that the search was capped (api/filesystem_edit.py, #19463)."
        ),
        component="filesystem_mcp",
    )
)

env_registry.register_env_var(
    env_registry.EnvVarSpec(
        name="AUTOBOT_EDIT_MISS_SEARCH_BUDGET_SECONDS",
        type=float,
        default=1.0,
        description=(
            "Wall-clock budget for one edit_file closest-span search after a miss. On expiry the search "
            "returns the best span found so far and says it was capped (api/filesystem_edit.py, #19463)."
        ),
        component="filesystem_mcp",
    )
)

env_registry.register_env_var(
    env_registry.EnvVarSpec(
        name="AUTOBOT_MEMORY_SESSION_READ_MAX_CHUNKS",
        type=int,
        default=500,
        description=(
            "Most chunks one memory.session_read call returns for a single session "
            "(memory/verbatim_sessions.py, #11137)."
        ),
        component="memory",
        range=(1, 100_000),
    )
)

env_registry.register_env_var(
    env_registry.EnvVarSpec(
        name="AUTOBOT_MEMORY_SESSION_LIST_MAX_SCAN",
        type=int,
        default=5000,
        description=(
            "Most of the caller's chunks one memory.session_list call scans when grouping them into sessions "
            "(memory/verbatim_sessions.py, #11137)."
        ),
        component="memory",
        range=(1, 1_000_000),
    )
)

env_registry.register_env_var(
    env_registry.EnvVarSpec(
        name="AUTOBOT_MEMORY_SESSION_LIST_LIMIT",
        type=int,
        default=50,
        description=(
            "Default number of sessions memory.session_list returns when the caller gives no limit "
            "(memory/verbatim_sessions.py, #11137)."
        ),
        component="memory",
        range=(1, 10_000),
    )
)

env_registry.register_env_var(
    env_registry.EnvVarSpec(
        name="AUTOBOT_TRANSCRIPT_MAX_DECOMPRESSED_BYTES",
        type=int,
        default=1073741824,
        description=(
            "Most decompressed bytes read from one transcript or history file "
            "before the read stops and reports itself truncated "
            "(services/execution/transcript_normalizer.py, #11137)."
        ),
        component="memory",
    )
)

env_registry.register_env_var(
    env_registry.EnvVarSpec(
        name="AUTOBOT_TRANSCRIPT_MAX_LINE_BYTES",
        type=int,
        default=16777216,
        description=(
            "Longest single line a transcript or history read will load; "
            "a longer line stops the file and reports it truncated "
            "(services/execution/transcript_normalizer.py, #11137)."
        ),
        component="memory",
    )
)

env_registry.register_env_var(
    env_registry.EnvVarSpec(
        name="AUTOBOT_TRANSCRIPT_MAX_EVENTS",
        type=int,
        default=1000000,
        description=(
            "Most events (or history entries) returned from one file "
            "before the read stops and reports itself truncated "
            "(services/execution/transcript_normalizer.py, #11137)."
        ),
        component="memory",
    )
)

env_registry.register_env_var(
    env_registry.EnvVarSpec(
        name="AUTOBOT_TRANSCRIPT_MAX_RETAINED_BYTES",
        type=int,
        default=268435456,
        description=(
            "Most source-line bytes behind the events or entries one transcript or history read retains; "
            "over it the read stops and reports itself truncated "
            "(services/execution/transcript_normalizer.py, #11137)."
        ),
        component="memory",
    )
)

env_registry.register_env_var(
    env_registry.EnvVarSpec(
        name="AUTOBOT_MEMORY_SESSION_READ_MAX_BYTES",
        type=int,
        default=262144,
        description=(
            "Most text bytes one memory.session_read call returns after redaction; "
            "over it the result carries truncated=true "
            "(memory/verbatim_sessions.py, #11137)."
        ),
        component="memory",
    )
)

env_registry.register_env_var(
    env_registry.EnvVarSpec(
        name="AUTOBOT_TRANSCRIPT_EVENT_OVERHEAD_BYTES",
        type=int,
        default=1024,
        description=(
            "Bytes charged per retained event, on top of its source bytes, against "
            "AUTOBOT_TRANSCRIPT_MAX_RETAINED_BYTES (services/execution/transcript_normalizer.py, #11137)."
        ),
        component="memory",
    )
)
