# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Task Pattern Learner (Issue #930)

Analyzes recent task outcomes to extract the best strategy for each task type.
Persists learned patterns to Redis for orchestrator routing decisions.
"""

import json
import os
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Dict, FrozenSet, List

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_mixin import AsyncRedisClientMixin
from autobot_shared.time_utils import utc_timestamp

logger = get_logger(__name__)

# GH#11071: keys are tenant-scoped so one org's synthesized strategy can never be
# read into another org's planning prompt. An empty tenant_id fails closed
# (retrieval/persistence is skipped) rather than falling back to a shared bucket.
REDIS_PATTERNS_KEY = "task:patterns:{tenant_id}:{task_type}"
REDIS_PATTERNS_TTL = 60 * 60 * 24 * 7  # 7 days

# GH#11534: single bucket for any task_type outside the known vocabulary, so
# free-form caller strings can never mint unbounded Redis keys (learner + judge).
OTHER_TASK_TYPE = "other"

# GH#11534: per-tenant cap on distinct task_type keys — a backstop beyond the
# allowlist. Never hard-coded (repo idiom, see chat_history/cache.py): overridable
# via env so a runaway integration can't blow past it silently.
MAX_TASK_TYPE_KEYS_PER_TENANT = int(os.environ.get("AUTOBOT_MAX_TASK_TYPE_KEYS_PER_TENANT", "64"))

# GH#11534: bounded per-key revision history so a single bad synthesized/imported
# strategy can be rolled back without wiping all learned state (clear_strategy).
REDIS_PATTERNS_HISTORY_KEY = "task:patterns:{tenant_id}:{task_type}:history"
STRATEGY_HISTORY_MAX = int(os.environ.get("AUTOBOT_STRATEGY_HISTORY_MAX", "10"))


@lru_cache(maxsize=1)
def _canonical_task_types() -> FrozenSet[str]:
    """Bounded allowlist of legitimate task_type values (GH#11534).

    Built from the canonical ``AgentType`` routing vocabulary plus the plan-level
    ``ExecutionStrategy`` values and the explicit literals the self-improvement
    write paths emit that are not in either enum:
      - ``planning``      → orchestrator._score_plan
      - ``chat_turn``     → chat_workflow.trajectory_context
      - ``llc_heartbeat`` → llc.kb.diary_writer default snapshot

    Imported lazily and cached so module import stays light and the set is
    computed once. Any task_type outside this set collapses to ``OTHER_TASK_TYPE``.
    """
    from agents.agent_orchestration.types import AgentType
    from autobot_shared.workflow import ExecutionStrategy

    vocab = {t.value for t in AgentType}
    vocab |= {s.value for s in ExecutionStrategy}
    vocab |= {"planning", "chat_turn", "llc_heartbeat"}
    return frozenset(vocab)


def normalize_task_type(task_type: str) -> str:
    """Canonicalise + allowlist a task_type to the bounded vocabulary (GH#11534).

    Format-canonicalises (lowercase, strip, ``-``/space → ``_``) then restricts to
    :func:`_canonical_task_types`; anything unknown (or empty) buckets to
    ``OTHER_TASK_TYPE``. Learner and judge both route through this single function
    so their Redis keys always agree for the same input.
    """
    canon = (task_type or "").strip().lower().replace("-", "_").replace(" ", "_")
    if not canon:
        return OTHER_TASK_TYPE
    return canon if canon in _canonical_task_types() else OTHER_TASK_TYPE


async def enforce_key_cap(redis: Any, prefix: str, task_type: str) -> str:
    """Return *task_type*, or ``OTHER_TASK_TYPE`` when the tenant is at the key cap.

    GH#11534 backstop beyond the allowlist: counts the tenant's existing distinct
    task_type keys under *prefix* (e.g. ``task:outcomes:{tid}:``) and, if adding a
    NEW key would exceed :data:`MAX_TASK_TYPE_KEYS_PER_TENANT`, diverts the write
    into the shared ``other`` bucket. Existing keys and the ``other`` bucket itself
    are always allowed. Revision-history sub-keys never count toward the cap.
    Any Redis error fails open (returns *task_type*) — the cap must never drop data.
    """
    if task_type == OTHER_TASK_TYPE:
        return task_type
    try:
        existing: set[str] = set()
        cursor = 0
        pattern = f"{prefix}*"
        while True:
            cursor, keys = await redis.scan(cursor, match=pattern, count=100)
            for k in keys:
                key = k.decode() if isinstance(k, bytes) else k
                suffix = key[len(prefix) :]
                if suffix.endswith(":history"):
                    continue
                existing.add(suffix)
            if cursor == 0:
                break
        if task_type in existing:
            return task_type
        if len(existing) >= MAX_TASK_TYPE_KEYS_PER_TENANT:
            logger.warning(
                "Task-type key cap (%d) reached for prefix %s — bucketing %r into %r (GH#11534)",
                MAX_TASK_TYPE_KEYS_PER_TENANT,
                prefix,
                task_type,
                OTHER_TASK_TYPE,
            )
            return OTHER_TASK_TYPE
        return task_type
    except Exception as exc:
        logger.warning("Key-cap check failed for prefix %s (failing open): %s", prefix, exc)
        return task_type


def _scoped_tenant(tenant_id: str, op: str) -> str | None:
    """Return the normalized tenant_id, or None (fail-closed) when it is empty.

    GH#11071: learned-strategy reads/writes must be tenant-scoped. A missing
    tenant_id is a misconfiguration, not a licence to touch a shared bucket, so
    the caller skips the Redis op and logs a warning.
    """
    tid = (tenant_id or "").strip()
    if not tid:
        logger.warning("TaskPatternLearner.%s: empty tenant_id — skipping (fail-closed, GH#11071)", op)
        return None
    return tid


# Minimum outcomes required before learning is triggered
MIN_OUTCOMES_TO_LEARN = 3

# Confidence thresholds (#2208):
# - 0.7: minimum for using a learned strategy (in AgentRouter._check_learned_strategy)
#   Lower than quick_route to allow learned strategies a fair trial.
# - 0.8: minimum for quick_route_analysis to bypass LLM routing entirely.
LEARNED_STRATEGY_CONFIDENCE = 0.7
# Maximum outcomes considered per analysis window
ANALYSIS_WINDOW = 20


@dataclass
class LearnedStrategy:
    """Best strategy learned from analyzing task outcome history."""

    task_type: str
    best_approach: str
    best_prompt_template: str
    avg_score: float
    sample_size: int
    confidence: float
    failure_patterns: List[str] = field(default_factory=list)
    timestamp: str = field(default_factory=utc_timestamp)
    # GH#11534 provenance + rollback: ``version`` increments on each overwrite,
    # ``tenant_id`` records the owning org, and ``source_outcome_ids`` records the
    # outcomes this revision was synthesized from — so a single bad revision can be
    # traced and reverted (rollback_strategy) instead of wiping all learned state.
    version: int = 1
    tenant_id: str = ""
    source_outcome_ids: List[str] = field(default_factory=list)


class TaskPatternLearner(AsyncRedisClientMixin):
    """Analyzes task outcome history to extract optimal strategies per task type."""

    _redis_database = "main"

    def __init__(self, llm_interface=None):
        """Initialize with optional LLM interface."""
        self._llm = llm_interface

    async def _get_llm(self):
        """Lazily initialize LLM interface."""
        if self._llm is None:
            from services.llm_service import get_llm_service

            self._llm = get_llm_service()
        return self._llm

    @staticmethod
    def normalize_task_type(task_type: str) -> str:
        """Canonicalise + allowlist task_type to the bounded vocabulary (#2208, GH#11534).

        Delegates to the module-level :func:`normalize_task_type` so learner, judge,
        and every caller share one source of truth: format-canonicalise, then
        restrict to the known ``AgentType``/``ExecutionStrategy`` vocabulary,
        bucketing anything unknown into ``OTHER_TASK_TYPE``.
        """
        return normalize_task_type(task_type)

    async def learn_from_outcomes(
        self, task_type: str, outcomes: List[Dict], tenant_id: str = ""
    ) -> LearnedStrategy | None:
        """Analyze recent outcomes and extract the best strategy.

        Args:
            task_type: Task category to analyze (normalised to AgentType vocab)
            outcomes: List of outcome dicts with score, strategy_used, rationale
            tenant_id: Owning tenant — the learned strategy is stored under it
                so it can never be read into another tenant's plan (GH#11071).

        Returns:
            LearnedStrategy if enough data, else None
        """
        tid = _scoped_tenant(tenant_id, "learn_from_outcomes")
        if tid is None:
            return None
        task_type = self.normalize_task_type(task_type)
        if len(outcomes) < MIN_OUTCOMES_TO_LEARN:
            logger.debug("Not enough outcomes to learn from for %s", task_type)
            return None
        recent = outcomes[:ANALYSIS_WINDOW]
        best_outcome = max(recent, key=lambda o: o.get("score", 0.0))
        strategy = await self._synthesize_strategy(task_type, recent, best_outcome)
        if strategy:
            # GH#11534: stamp provenance so a bad revision is traceable + revertible.
            strategy.tenant_id = tid
            strategy.source_outcome_ids = [
                str(o.get("timestamp") or o.get("id") or idx) for idx, o in enumerate(recent)
            ]
            await self._persist_strategy(task_type, strategy, tenant_id)
        return strategy

    async def _synthesize_strategy(
        self,
        task_type: str,
        outcomes: List[Dict],
        best_outcome: Dict,
    ) -> LearnedStrategy | None:
        """Use LLM to synthesize a strategy from outcome history."""
        try:
            llm = await self._get_llm()
            prompt = self._build_synthesis_prompt(task_type, outcomes, best_outcome)
            response = await llm.chat(
                messages=[
                    {"role": "system", "content": self._system_prompt()},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
            )
            return self._parse_strategy_response(response, task_type, outcomes)
        except Exception as exc:
            logger.warning("Error synthesizing strategy for %s: %s", task_type, exc)
            return self._fallback_strategy(task_type, outcomes, best_outcome)

    def _build_synthesis_prompt(self, task_type: str, outcomes: List[Dict], best_outcome: Dict) -> str:
        """Build synthesis prompt from outcome data."""
        summary = json.dumps(
            [
                {
                    "score": o.get("score"),
                    "strategy": o.get("strategy_used"),
                    "rationale": o.get("rationale", "")[:100],
                }
                for o in outcomes
            ],
            indent=2,
        )
        return (
            f"Analyze these {len(outcomes)} task outcomes for task type '{task_type}'.\n\n"
            f"OUTCOMES:\n{summary}\n\n"
            f"BEST OUTCOME: strategy='{best_outcome.get('strategy_used')}', "
            f"score={best_outcome.get('score', 0):.2f}\n\n"
            f"Extract the best strategy. Return JSON with:\n"
            f"- best_approach: description of the optimal approach\n"
            f"- best_prompt_template: a reusable prompt template\n"
            f"- failure_patterns: list of patterns that lead to failure\n"
            f"- confidence: float 0.0-1.0\n"
        )

    def _system_prompt(self) -> str:
        """System prompt for strategy synthesis."""
        return (
            "You are a learning systems analyst. Examine task execution histories "
            "and identify the most effective patterns and strategies. "
            "Return structured JSON only."
        )

    def _parse_strategy_response(self, response: Any, task_type: str, outcomes: List[Dict]) -> LearnedStrategy | None:
        """Parse LLM response into a LearnedStrategy."""
        try:
            content = response if isinstance(response, (str, dict)) else getattr(response, "content", "{}")
            data = content if isinstance(content, dict) else json.loads(content)
            avg_score = sum(o.get("score", 0.0) for o in outcomes) / len(outcomes)
            return LearnedStrategy(
                task_type=task_type,
                best_approach=data.get("best_approach", ""),
                best_prompt_template=data.get("best_prompt_template", ""),
                avg_score=avg_score,
                sample_size=len(outcomes),
                confidence=float(data.get("confidence", 0.5)),
                failure_patterns=data.get("failure_patterns", []),
            )
        except Exception as exc:
            logger.warning("Failed to parse strategy response: %s", exc)
            return None

    def _fallback_strategy(self, task_type: str, outcomes: List[Dict], best_outcome: Dict) -> LearnedStrategy:
        """Build a basic strategy when LLM synthesis is unavailable."""
        avg_score = sum(o.get("score", 0.0) for o in outcomes) / len(outcomes)
        return LearnedStrategy(
            task_type=task_type,
            best_approach=best_outcome.get("strategy_used", "default"),
            best_prompt_template=f"Complete this {task_type} task: {{goal}}",
            avg_score=avg_score,
            sample_size=len(outcomes),
            confidence=0.3,
        )

    async def _persist_strategy(self, task_type: str, strategy: LearnedStrategy, tenant_id: str = "") -> None:
        """Persist learned strategy to Redis, scoped to *tenant_id* (GH#11071).

        GH#11534: before overwriting, the current revision is archived to a bounded
        per-key history list and the new revision's ``version`` is incremented, so a
        bad synthesized/imported strategy can be reverted (rollback_strategy) without
        wiping learned state. A per-tenant key cap bounds distinct task_type keys.
        """
        tid = _scoped_tenant(tenant_id, "_persist_strategy")
        if tid is None:
            return
        try:
            redis = await self._get_redis()
            task_type = await enforce_key_cap(redis, f"task:patterns:{tid}:", task_type)
            key = REDIS_PATTERNS_KEY.format(tenant_id=tid, task_type=task_type)
            prev_raw = await redis.get(key)
            if prev_raw:
                try:
                    strategy.version = int(json.loads(prev_raw).get("version", 1)) + 1
                except Exception:
                    strategy.version = strategy.version + 1
                hist_key = REDIS_PATTERNS_HISTORY_KEY.format(tenant_id=tid, task_type=task_type)
                await redis.lpush(hist_key, prev_raw)
                await redis.ltrim(hist_key, 0, STRATEGY_HISTORY_MAX - 1)
                await redis.expire(hist_key, REDIS_PATTERNS_TTL)
            strategy.tenant_id = tid
            strategy.task_type = task_type
            await redis.set(key, json.dumps(strategy.__dict__), ex=REDIS_PATTERNS_TTL)
        except Exception as exc:
            logger.warning("Failed to persist learned strategy: %s", exc)

    async def rollback_strategy(self, task_type: str, tenant_id: str = "") -> LearnedStrategy | None:
        """Revert a task type's learned strategy to its previous revision (GH#11534).

        Pops the most recent archived revision from the per-key history list and
        restores it as current, so a single bad synthesized/imported strategy can be
        undone without wiping all learned state (unlike clear_strategy). Scoped to
        *tenant_id*; empty fails closed. Returns the restored strategy, or None when
        there is no prior revision to roll back to.
        """
        tid = _scoped_tenant(tenant_id, "rollback_strategy")
        if tid is None:
            return None
        task_type = self.normalize_task_type(task_type)
        try:
            redis = await self._get_redis()
            hist_key = REDIS_PATTERNS_HISTORY_KEY.format(tenant_id=tid, task_type=task_type)
            prev_raw = await redis.lpop(hist_key)
            if not prev_raw:
                logger.info("rollback_strategy: no prior revision for %s (tenant=%s)", task_type, tid)
                return None
            restored = LearnedStrategy(**json.loads(prev_raw))
            key = REDIS_PATTERNS_KEY.format(tenant_id=tid, task_type=task_type)
            await redis.set(key, json.dumps(restored.__dict__), ex=REDIS_PATTERNS_TTL)
            logger.info(
                "rollback_strategy: restored %s to version %s (tenant=%s)",
                task_type,
                getattr(restored, "version", "?"),
                tid,
            )
            return restored
        except Exception as exc:
            logger.warning("Failed to roll back learned strategy: %s", exc)
            return None

    async def get_learned_strategy(self, task_type: str, tenant_id: str = "") -> LearnedStrategy | None:
        """Retrieve persisted learned strategy for a task type, scoped to *tenant_id* (#2208, GH#11071)."""
        tid = _scoped_tenant(tenant_id, "get_learned_strategy")
        if tid is None:
            return None
        task_type = self.normalize_task_type(task_type)
        try:
            redis = await self._get_redis()
            key = REDIS_PATTERNS_KEY.format(tenant_id=tid, task_type=task_type)
            raw = await redis.get(key)
            if raw:
                return LearnedStrategy(**json.loads(raw))
        except Exception as exc:
            logger.warning("Failed to retrieve learned strategy: %s", exc)
        return None

    async def save_strategy(self, strategy: LearnedStrategy, tenant_id: str = "") -> None:
        """Persist an externally-curated strategy for its task type (GH#11151).

        The public import entry point — normalises the task type and reuses the
        same Redis persistence as learned strategies so a reviewer-edited record
        is stored identically to a synthesized one. Scoped to *tenant_id* (GH#11071).
        """
        task_type = self.normalize_task_type(strategy.task_type)
        strategy.task_type = task_type
        await self._persist_strategy(task_type, strategy, tenant_id)

    async def clear_strategy(self, task_type: str, tenant_id: str = "") -> None:
        """Clear the learned strategy for a task type, scoped to *tenant_id* (#2325, GH#11071)."""
        tid = _scoped_tenant(tenant_id, "clear_strategy")
        if tid is None:
            return
        task_type = self.normalize_task_type(task_type)
        try:
            redis = await self._get_redis()
            key = REDIS_PATTERNS_KEY.format(tenant_id=tid, task_type=task_type)
            await redis.delete(key)
        except Exception as exc:
            logger.warning("Failed to clear learned strategy: %s", exc)

    async def get_all_task_types(self, tenant_id: str = "") -> List[str]:
        """List task types that have stored outcomes for *tenant_id* (GH#11071).

        Scoped by tenant so a caller can only enumerate its own task types; an
        empty tenant_id fails closed (returns []), mirroring the store keys.
        """
        tid = _scoped_tenant(tenant_id, "get_all_task_types")
        if tid is None:
            return []
        try:
            redis = await self._get_redis()
            prefix = f"task:outcomes:{tid}:"
            pattern = f"{prefix}*"
            cursor = 0
            types: List[str] = []
            while True:
                cursor, keys = await redis.scan(cursor, match=pattern, count=100)
                for k in keys:
                    key = k.decode() if isinstance(k, bytes) else k
                    types.append(key.replace(prefix, "", 1))
                if cursor == 0:
                    break
            return types
        except Exception as exc:
            logger.warning("Failed to list task types: %s", exc)
            return []
