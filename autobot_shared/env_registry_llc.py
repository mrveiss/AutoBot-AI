# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""LLC (agent orchestration) AUTOBOT_* environment variable registrations.

Split out of ``env_registry.py`` rather than added inline (#13099) — that
file was already at its grandfathered file-size ceiling (#14236) with no
slack, so a same-file addition would have required raising the ceiling,
which the ratchet forbids. ``AUTOBOT_LLC_H2A_BRIEF_CACHE_TTL`` moved here
from its previous inline registration at the same time, so every LLC var
lives in one place instead of being split by accident of when it was added.

The import-as-side-effect registration contract this module relies on --
why importing it is safe, and how it reaches ``env_registry.REGISTRY`` -- is
stated once in ``env_registry_agent_runtime``'s docstring rather than
repeated on every sibling; #16415 tracks consolidating it into one place.

Closes GH#7081.
"""

from __future__ import annotations

from autobot_shared import env_registry

# Module-qualified rather than `from ... import EnvVarSpec, register_env_var`
# (#16284 review): the bare-name form reproduced the same import lines and the
# same `register_env_var(\n    EnvVarSpec(` opening as every sibling
# registration module, which the duplication guard counts across each pair of
# them regardless of which one was added most recently.
env_registry.register_env_var(
    env_registry.EnvVarSpec(
        name="AUTOBOT_LLC_H2A_BRIEF_CACHE_TTL",
        type=int,
        default=86400,
        description=(
            "Cache lifetime in seconds for a human-to-agent handoff brief (llc/services/handoff.py). One day."
        ),
        component="orchestrator",
    )
)

env_registry.register_env_var(
    env_registry.EnvVarSpec(
        name="AUTOBOT_LLC_FIRST_OUTPUT_DEADLINE_SECONDS",
        type=int,
        default=120,
        description=(
            "Seconds after an LLC CLI agent spawns before its output file must have "
            "received at least one byte, or the run is killed as stalled (GH#13099). "
            "The Claude Code and Copilot CLIs both emit their first JSONL line within "
            "a few seconds of a cold start; 120s is generous headroom for that before "
            "'nothing yet' means a hung dispatch rather than a slow one."
        ),
        component="orchestrator",
    )
)

env_registry.register_env_var(
    env_registry.EnvVarSpec(
        name="AUTOBOT_LLC_STALL_DEADLINE_SECONDS",
        type=int,
        default=600,
        description=(
            "Seconds of silence in an LLC CLI agent's output file, after its first "
            "byte, before the run is killed as stalled rather than left to burn out "
            "the full run timeout (GH#13099). Both CLIs stream output line-buffered, "
            "so a healthy run keeps producing it; the one legitimate quiet stretch is "
            "a single long tool call (a build, a test suite), which 600s (10 min) "
            "outlasts without a false positive."
        ),
        component="orchestrator",
    )
)
