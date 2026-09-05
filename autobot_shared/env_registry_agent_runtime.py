# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Agent-loop / agent-orchestration AUTOBOT_* environment variable registrations.

New sibling module (#15710), following the pattern ``env_registry_slm.py``'s
docstring records: ``env_registry.py`` is closed to new entries -- it sits at
its grandfathered file-size ceiling (#14236) with no slack, so a variable
that needs registering goes in its own per-component module instead of
raising that ceiling.

These fourteen were read through a bare ``int(os.environ.get(...))`` /
``float(os.environ.get(...))`` cast until #15710 converted each to
``autobot_shared.env_utils``'s ``env_int``/``env_float`` -- crash-safe, but
still unregistered, because ``check_env_var_registry.py`` derives its reader
set from ``os.getenv`` and the ``env_utils`` helper names, and had never
seen ``os.environ.get`` either. Converting made them visible to that
checker for the first time; this module is what answers it.

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
        name="AUTOBOT_A2A_CAPABILITY_TTL",
        type=int,
        default=300,
        description=(
            "How long a fetched remote A2A capability descriptor is cached "
            "before the next check re-fetches it. Raising it reduces repeated "
            "cross-agent capability lookups; lowering it makes a capability "
            "change on the remote side (e.g. a tool removed) visible sooner "
            "(a2a/capability_verifier.py)."
        ),
        component="a2a",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_RUN_CHECKPOINT_TTL_SECONDS",
        type=int,
        default=86400,
        description=(
            "TTL, in seconds, for a run's durable progress checkpoint in "
            "Redis (GH#11175). Raising it lets a crashed/restarted run resume "
            "from a checkpoint over a longer window; lowering it expires "
            "stale checkpoints sooner (agent_loop/loop.py)."
        ),
        component="agent_loop",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_ASK_HUMAN_TIMEOUT_SECONDS",
        type=int,
        default=300,
        description=(
            "Seconds the agent loop suspends waiting for a human to answer "
            "an ask-human question before escalating past it (#10553). "
            "Raising it gives a human longer to respond; lowering it "
            "escalates sooner, risking a question no one had time to see "
            "(agent_loop/types.py)."
        ),
        component="agent_loop",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_MAX_TASK_TYPE_KEYS_PER_TENANT",
        type=int,
        default=64,
        description=(
            "Per-tenant cap on distinct task_type keys the pattern learner "
            "tracks in Redis, beyond the known-vocabulary allowlist (GH#11534). "
            "Raising it tolerates more distinct task types per tenant before "
            "capping; lowering it bounds Redis key growth more tightly "
            "against a runaway integration (agents/task_pattern_learner.py)."
        ),
        component="agents",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_STRATEGY_HISTORY_MAX",
        type=int,
        default=10,
        description=(
            "Bounded per-key revision history the pattern learner keeps for "
            "a learned strategy, so a bad synthesized/imported one can be "
            "rolled back (GH#11534). Raising it keeps more prior revisions "
            "available to roll back to; lowering it keeps fewer, saving "
            "Redis space (agents/task_pattern_learner.py)."
        ),
        component="agents",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_SELF_IMPROVEMENT_MAX_CONCURRENCY",
        type=int,
        default=2,
        description=(
            "Maximum concurrent background self-improvement (judge-LLM) "
            "tasks the workflow runner allows (#11014). Raising it lets more "
            "workflow completions trigger learning concurrently; lowering it "
            "bounds concurrent judge-LLM load more tightly "
            "(orchestration/workflow_runner.py)."
        ),
        component="orchestration",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_KNOWLEDGE_EXPORT_MIN_CONFIDENCE",
        type=float,
        default=0.8,
        description=(
            "Minimum confidence score a learned failure pattern must have to "
            "be included in a governance knowledge export. Raising it "
            "exports only higher-confidence patterns; lowering it includes "
            "more, less-certain ones (api/agents_self_improvement.py)."
        ),
        component="self_improvement",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_KNOWLEDGE_EXPORT_PATTERN_LIMIT",
        type=int,
        default=500,
        description=(
            "Maximum number of failure patterns scanned when building a "
            "governance knowledge export (GH#11179). Raising it scans more "
            "patterns before truncating; lowering it risks silently omitting "
            "patterns beyond the limit (api/agents_self_improvement.py)."
        ),
        component="self_improvement",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_LEARNED_TEMPLATE_MAX",
        type=int,
        default=500,
        description=(
            "Maximum characters kept from untrusted imported free-text when "
            "importing a reviewer-curated learned strategy (#11060). Raising "
            "it preserves more of a long imported template; lowering it "
            "truncates more aggressively, reducing how much unsanitized text "
            "is retained (api/agents_self_improvement.py)."
        ),
        component="self_improvement",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_RANKING_ALPHA",
        type=float,
        default=1.0,
        description=(
            "Multiplicative weight applied to the runtime_risk boost when "
            "ranking anti-pattern findings (0 disables the boost; 1.0 lets a "
            "fully-risky file double its effective score). Raising it "
            "weights runtime risk more heavily in the ranking; lowering it "
            "toward 0 weights it less (code_analysis/src/anti_pattern_detector.py)."
        ),
        component="code_analysis",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_RISK_K",
        type=float,
        default=5.0,
        description=(
            "Decay constant controlling how steeply a file's runtime_risk "
            "score saturates toward 1 as its raw risk grows (a file at "
            "raw_risk == K scores about 0.63). Raising it makes the score "
            "saturate more slowly; lowering it saturates faster "
            "(code_analysis/src/runtime_risk.py)."
        ),
        component="code_analysis",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_MAX_FALLBACK_ATTEMPTS",
        type=int,
        default=3,
        description=(
            "Maximum model-level fallback attempts the coordinator makes "
            "after a quota/rate-limit exhaustion before giving up. Raising it "
            "tries more fallback models before failing; lowering it gives up "
            "sooner, failing faster but with less fallback coverage "
            "(llm_shared/model_fallback_coordinator.py)."
        ),
        component="llm",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_EXTRACT_MAX_RETRIES",
        type=int,
        default=3,
        description=(
            "Maximum LLM call attempts a structured-extraction request makes "
            "before raising ExtractionError. Raising it tolerates more "
            "transient failures before giving up; lowering it fails faster "
            "but is less tolerant of a flaky provider (llm_shared/structured_ops.py)."
        ),
        component="llm",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_EXTRACT_CHUNK_THRESHOLD",
        type=int,
        default=8000,
        description=(
            "Character-count threshold above which structured-extraction "
            "input is auto-chunked before an LLM call. Raising it sends "
            "larger inputs in a single call; lowering it chunks sooner, "
            "trading more calls for a smaller per-call context "
            "(llm_shared/structured_ops.py)."
        ),
        component="llm",
    )
)
