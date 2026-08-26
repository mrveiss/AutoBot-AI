# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""AI/LLM AUTOBOT_* environment variable registrations.

Split out of ``env_registry.py`` to keep that file under its grandfathered
file-size ceiling (#14236) — the module was already at its ceiling, and this
is the "ai" component's registrations: model selection, provider back-off
and degradation, delegation, plan generation, and trajectory
capture/retrieval/pruning. All genuinely one cohesive area (LLM-facing
behaviour), so it moves as a unit rather than being split arbitrarily
(#14856).

Importing this module registers every variable below into
``autobot_shared.env_registry.REGISTRY`` as a side effect, exactly like the
``register_env_var(...)`` calls in ``env_registry.py`` itself. It is imported
from there, after ``EnvVarSpec``/``register_env_var``/``REGISTRY`` are
defined, so nothing ever observes a partially-populated registry.

Closes GH#7081.
"""

from __future__ import annotations

from autobot_shared.env_registry import EnvVarSpec, register_env_var

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_CLASSIFICATION_MODEL",
        type=str,
        default="gemma2:2b",
        description="Ollama model name used for intent classification.",
        component="ai",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_OLLAMA_BASE_URL",
        type=str,
        default=None,
        description="Base URL of the local Ollama API (e.g. http://localhost:11434).",
        component="ai",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_ORCHESTRATOR_MODEL",
        type=str,
        default="llama3.2:1b",
        description="Ollama model name used for the main orchestrator/routing loop.",
        component="ai",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_LLM_MAX_RETRY_AFTER_SECONDS",
        type=float,
        default=30.0,
        description=(
            "Cap applied to a provider's `Retry-After`. Without it a provider "
            "advertising a long back-off would stall a request for that whole "
            "period (services/llm_service.py)."
        ),
        component="ai",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_OPENVINO_CACHE_DIR",
        type=str,
        default="data/openvino_cache",
        description=(
            "Directory for compiled OpenVINO model artefacts. Relative to the "
            "working directory unless given as an absolute path."
        ),
        component="ai",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_CHAT_TRAJECTORY_CAPTURE_CONCURRENCY",
        type=int,
        default=2,
        description=("Concurrent trajectory judge calls. Bounded so a burst of turns cannot stampede " "the LLM."),
        component="ai",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_CHAT_TRAJECTORY_CONTEXT",
        type=bool,
        default=True,
        description=(
            "Search past trajectories before answering. Defaults on because the search is "
            "one vector query; capture is gated separately since it spends a judge call."
        ),
        component="ai",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_CHAT_TRAJECTORY_TIMEOUT_S",
        type=float,
        default=0.15,
        description=(
            "Seconds the pre-answer trajectory search may take. It rides the response hot "
            "path, so a cold or slow collection must never delay first token."
        ),
        component="ai",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_CHAT_TRAJECTORY_TOP_K",
        type=int,
        default=3,
        description=("How many past trajectories the pre-answer search retrieves."),
        component="ai",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_DELEGATION_ENABLED",
        type=bool,
        default=False,
        description=(
            "Master switch for the delegate tool. Off, it records the delegation request " "and does not dispatch it."
        ),
        component="ai",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_FACT_FORCING",
        type=bool,
        default=False,
        description=("Enable the fact-forcing gate, which requires an answer to cite retrieved " "facts."),
        component="ai",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_LLM_TOKEN_BUDGET_PER_RUN",
        type=int,
        default=0,
        description=(
            "Cumulative token ceiling (input plus output) for one run. Zero disables the "
            "gate, which is the shipped default (#11541)."
        ),
        component="ai",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_LLM_TOKEN_BUDGET_TTL_SECONDS",
        type=int,
        default=86400,
        description=(
            "Seconds a run's cumulative token counter survives in Redis, bounding memory "
            "for abandoned sessions. Refreshed on every increment."
        ),
        component="ai",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_MAX_DELEGATIONS_PER_TURN",
        type=int,
        default=5,
        description=("Delegate calls allowed in a single LLM turn — a fan-out bound, not a quality " "setting."),
        component="ai",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_MAX_DELEGATION_DEPTH",
        type=int,
        default=2,
        description=("How deep delegation may nest before it is refused, bounding runaway recursive " "delegation."),
        component="ai",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_PLAN_BEST_OF_N_COUNT",
        type=int,
        default=3,
        description=(
            "How many candidate plans best-of-N generates before selection. Clamped to a "
            "minimum of 2, since best-of-1 is not a selection."
        ),
        component="ai",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_PROVIDER_DEGRADATION_TTL_SECONDS",
        type=int,
        default=300,
        description=(
            "Seconds a provider stays marked degraded after a failure before traffic is " "offered to it again."
        ),
        component="ai",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_TRAJECTORY_CONSOLIDATE_SCAN_LIMIT",
        type=int,
        default=50000,
        description=("Rows a consolidation pass may scan, keeping the pass bounded on a large " "trajectory store."),
        component="ai",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_TRAJECTORY_OUTCOME_PARTIAL_MIN",
        type=float,
        default=0.4,
        description=(
            "Reward at or above which a trajectory outcome is 'partial'. Below it the " "outcome is a failure (#11280)."
        ),
        component="ai",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_TRAJECTORY_OUTCOME_SUCCESS_MIN",
        type=float,
        default=0.7,
        description=(
            "Reward at or above which a trajectory outcome is 'success'. The canonical "
            "threshold, so callers stop re-deriving it inline (#11280)."
        ),
        component="ai",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_TRAJECTORY_PRUNE_MAX_AGE_DAYS",
        type=int,
        default=30,
        description=("Age in days beyond which a low-reward trajectory is eligible for pruning " "(#11263)."),
        component="ai",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_TRAJECTORY_PRUNE_REWARD_FLOOR",
        type=float,
        default=0.4,
        description=(
            "Reward below which an aged trajectory is pruned. Stale low-reward failures are "
            "noise that costs retrieval precision (#11263)."
        ),
        component="ai",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_TRAJECTORY_USER_SCOPED",
        type=bool,
        default=True,
        description=(
            "Scope trajectory retrieval by user as well as tenant. tenant_id alone is "
            "insufficient in single-company deployments where org_id is empty or identical "
            "for everyone (#11089)."
        ),
        component="ai",
    )
)
