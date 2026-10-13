# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Memory / fact-lane / tool-output-spill AUTOBOT_* environment variable registrations.

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
