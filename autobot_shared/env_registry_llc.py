# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""LLC (agent orchestration) AUTOBOT_* environment variable registrations.

Split out of ``env_registry.py`` rather than added inline (#13099) — that
file was already at its grandfathered file-size ceiling (#14236) with no
slack, so a same-file addition would have required raising the ceiling,
which the ratchet forbids. ``AUTOBOT_LLC_H2A_BRIEF_CACHE_TTL`` moved here
from its previous inline registration at the same time, so every LLC var
lives in one place instead of being split by accident of when it was added.

Registration contract (import side effect, ordering): see ``env_registry`` (#16415).

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

env_registry.register_env_var(
    env_registry.EnvVarSpec(
        name="AUTOBOT_LLC_DEFAULT_HEARTBEAT_CRON",
        type=str,
        default="* * * * *",
        description=(
            "Cron a hired LLC agent wakes on when the hire request does not name one "
            "(#15907, owner ruling 2026-09-28). The scheduler's gate is "
            "heartbeat_enabled = true AND heartbeat_cron IS NOT NULL, and this field "
            "previously defaulted to NULL, so an agent hired with the flag set and no "
            "cron was never scheduled -- the flag said yes and the column the "
            "scheduler reads said nothing. One minute is affordable because #17726's "
            "idle short-circuit returns before creating a run when the agent's queue "
            "is empty; without that it would be 1,440 full invocations per agent per "
            "day. heartbeat_enabled still defaults false, so a cadence is not an opt-in."
        ),
        component="orchestrator",
    )
)

env_registry.register_env_var(
    env_registry.EnvVarSpec(
        name="AUTOBOT_LLC_HEARTBEAT_IDLE_WAKE_TTL_SECONDS",
        type=float,
        default=604800.0,
        description=(
            "How long the per-agent idle-wake counter and last-idle-wake timestamp are "
            "kept in Redis (#17726). A short-circuited wake writes no llc_heartbeat_runs "
            "row, so these two keys are the only evidence it happened -- without them "
            "'the queue was empty' and 'the scheduler is dead' are the same observation. "
            "A week outlasts any plausible investigation into a quiet agent. A Redis hash "
            "field cannot expire on its own, so the TTL is reapplied to the whole key on "
            "each write."
        ),
        component="orchestrator",
    )
)

env_registry.register_env_var(
    env_registry.EnvVarSpec(
        name="AUTOBOT_LLC_DISPOSAL_EXECUTION_WINDOW_DAYS",
        type=float,
        default=7.0,
        description=(
            "How many days an approved workspace-disposal proposal stays executable (#17738). "
            "An executed proposal keeps status APPROVED -- execution is recorded in its context, "
            "not in the status -- so without a window the hourly sweep re-read its entire "
            "approval history for ever, growing without bound. A time bound also stops a "
            "decision approved months ago being executed against a workspace whose branch and "
            "landedness have moved on since a human looked at it. Aged-out approvals are skipped, "
            "never marked EXPIRED: an unattended change to a human's decision record is what the "
            "propose-then-approve design exists to prevent. Floored at 1 day, because 0 would "
            "place every decision outside the window and disable the sweep silently."
        ),
        component="orchestrator",
    )
)
