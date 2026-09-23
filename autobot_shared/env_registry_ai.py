# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""AI/LLM AUTOBOT_* environment variable registrations.

Split out of ``env_registry.py`` to keep that file under its grandfathered
file-size ceiling (#14236) — the module was already at its ceiling, and this
is the "ai" component's registrations: provider back-off and degradation,
delegation, plan generation, and trajectory capture/retrieval/pruning. All
genuinely one cohesive area (LLM-facing behaviour), so it moves as a unit
rather than being split arbitrarily (#14856).

Three "ai" vars — ``AUTOBOT_CLASSIFICATION_MODEL``, ``AUTOBOT_OLLAMA_BASE_URL``,
``AUTOBOT_ORCHESTRATOR_MODEL`` — stay behind in ``env_registry.py`` rather than
moving here, deliberately: each carries a hardcoded default or description
value already recorded in ``pipeline-scripts/hardcoded_values_baseline.txt``
keyed to ``autobot_shared/env_registry.py``, and ``check_baseline_no_growth.sh``
has no route to repoint a baseline entry onto a file that did not exist at the
PR's base ref — by its own documented design, a moved file's new path is
always "this change created it, so the value in it is new, not pre-existing"
(#14856). Moving those three would either strand the old baseline entries
(failing ``--audit-baseline``) or add new ones the growth guard refuses
outright. Leaving them in place sidesteps a real gap in that guard rather than
working around it. See #13131 for the same shape in a different tool
(Semgrep).

Registration contract (import side effect, ordering): see ``env_registry`` (#16415).

Closes GH#7081.
"""

from __future__ import annotations

from autobot_shared.env_registry import EnvVarSpec, register_env_var

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
        name="AUTOBOT_LLM_QUOTA_HEADROOM_TTL_SECONDS",
        type=int,
        default=3600,
        description=("Seconds a recorded provider rate-limit headroom reading stays valid before " "it expires."),
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


# ---------------------------------------------------------------------------
# Pricing (#16229, #16230).
#
# These lived in env_registry_backend_services.py until #16230's three additions
# took that file to 632 against the 600 hard limit. They are here rather than in
# a new env_registry_pricing.py for one reason worth stating: a new module needs
# a new import line in env_registry.py, which is grandfathered at its own
# ceiling with nothing to spare, and every way of freeing that line is worse.
# Relocating specs out of the parent is refused by the hardcoded-value baseline,
# which is keyed by file and deliberately does not cover a move -- correctly,
# since it cannot tell a moved value from a newly authored one.
#
# So: the file that already owns the LLM-facing variables takes the prices of
# the LLMs. They keep component="pricing", so the generated docs and any
# component query are unaffected by which file they sit in.
# ---------------------------------------------------------------------------

#: Default pricing catalogue URLs, keyed by the variable that overrides each (#16229).
#: One home for the value: live_sources.py reads it back from REGISTRY, so the code,
#: the registry and the generated docs table cannot drift apart.
_PRICING_LITELLM_FILE = "model_prices_and_context_window.json"
_PRICING_URL_DEFAULTS = {
    "AUTOBOT_PRICING_LITELLM_URL": "https://raw.githubusercontent.com/BerriAI/litellm/main/" + _PRICING_LITELLM_FILE,
    "AUTOBOT_PRICING_OPENROUTER_URL": "https://openrouter.ai/api/v1/models",
}

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_PRICING_CROSSCHECK_TOLERANCE_PERCENT",
        type=float,
        default=10.0,
        description=(
            "Percent difference between LiteLLM's and OpenRouter's price for one model above which the "
            "pricing refresh flags a disagreement. Flagged, never resolved silently (#16229)."
        ),
        component="pricing",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_PRICING_FETCH_TIMEOUT_SECONDS",
        type=float,
        default=30.0,
        description=(
            "Total timeout, in seconds, for one live pricing catalogue fetch. A timed-out fetch is a failed "
            "refresh and leaves stored prices to age, never looking fresh (#16229)."
        ),
        component="pricing",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_PRICING_LITELLM_URL",
        type=str,
        default=_PRICING_URL_DEFAULTS["AUTOBOT_PRICING_LITELLM_URL"],
        description=(
            "URL of LiteLLM's model price map, the primary live pricing catalogue. Fetched public-only "
            "through the egress guard (#16229)."
        ),
        component="pricing",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_PRICING_OPENROUTER_URL",
        type=str,
        default=_PRICING_URL_DEFAULTS["AUTOBOT_PRICING_OPENROUTER_URL"],
        description=(
            "URL of OpenRouter's public models API, the cross-check pricing catalogue. Fetched public-only "
            "through the egress guard (#16229)."
        ),
        component="pricing",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_PRICING_REFRESH_INTERVAL_HOURS",
        type=int,
        default=24,
        description=(
            "Hours between automatic pricing refreshes: the Celery beat cadence, and the floor under the "
            "Redis TTL so stored prices can never expire before the next scheduled refresh (#16231)."
        ),
        component="pricing",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_PRICING_LOCAL_CACHE_REFRESH_INTERVAL_S",
        type=int,
        default=300,
        description=(
            "Seconds between re-reads of the pricing store into each process's own in-memory mirror "
            "(llm_shared/pricing/sync_cache.py, #16230). Independent of "
            "AUTOBOT_PRICING_REFRESH_INTERVAL_HOURS, which is how often Redis itself is refreshed from "
            "the live catalogues: this only has to stay close enough to that upstream write to be a "
            "mirror, and a short interval also recovers a worker that restarted mid-cycle rather than "
            "leaving it cold for the rest of the daily cadence."
        ),
        component="pricing",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_PRICING_FIRST_REFRESH_TIMEOUT_S",
        type=float,
        default=10.0,
        description=(
            "Bound, in seconds, on the single pricing refresh awaited at startup before the app "
            "serves traffic (#16230). Without it the scheduler's first tick raced incoming "
            "requests, and budget.py refuses a cost event against a cold cache rather than "
            "recording zero. Exceeding the bound is non-fatal: the cache begins cold, which every "
            "caller already handles, and the next scheduled tick fills it."
        ),
        component="pricing",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_PRICING_LOCAL_CACHE_MAX_AGE_S",
        type=int,
        default=3600,
        description=(
            "Age, in seconds, past which a process's pricing mirror is refused as stale rather than "
            "served (PricingCacheStale, #16230). This is what stops a scheduler that quietly stopped "
            "refreshing from looking identical to one that is working -- above this bound a reader gets "
            "an exception, never an old price presented as current. Must exceed "
            "AUTOBOT_PRICING_LOCAL_CACHE_REFRESH_INTERVAL_S by enough to survive a few failed ticks."
        ),
        component="pricing",
    )
)
