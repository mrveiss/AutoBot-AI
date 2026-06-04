# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Generic Prompt Optimizer

Issue #2600: Mutates agent prompts, benchmarks via pluggable scorers,
and keeps/discards based on improvement. AutoResearchAgent is the first
optimization target; any agent can register a PromptOptTarget.

Loop:
  1. Mutate current best prompt into N variants (via LLM)
  2. Run each variant through benchmark_fn to get output
  3. Score all variants via first scorer in chain (fast filter)
  4. Pass top-K candidates to next scorer (deeper evaluation)
  5. If best variant improves over baseline -> KEEP, update baseline
  6. Persist all results
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_mixin import AsyncRedisClientMixin
from constants.ttl_constants import TTL_7_DAYS

from .archive import Archive
from .config import AutoResearchConfig
from .models import VariantArchiveEntry
from .scorers import PromptScorer

logger = get_logger(__name__)


class OptimizationStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass
class PromptOptTarget:
    """Registration for an agent that opts into prompt optimization."""

    agent_name: str
    current_prompt: str
    scorer_chain: List[str]  # scorer names in evaluation order
    mutation_count: int = 5
    top_k: int = 2


@dataclass
class PromptVariant:
    """A single mutated prompt and its evaluation results."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    prompt_text: str = ""
    output: str = ""
    scores: Dict[str, float] = field(default_factory=dict)
    final_score: float = 0.0
    round_number: int = 0
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "prompt_text": self.prompt_text,
            "output": self.output,
            "scores": self.scores,
            "final_score": self.final_score,
            "round_number": self.round_number,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PromptVariant":
        return cls(
            id=data.get("id", ""),
            prompt_text=data.get("prompt_text", ""),
            output=data.get("output", ""),
            scores=data.get("scores", {}),
            final_score=data.get("final_score", 0.0),
            round_number=data.get("round_number", 0),
            created_at=data.get("created_at", 0.0),
        )


@dataclass
class OptimizationSession:
    """Top-level record for a prompt optimization run."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    target: PromptOptTarget | None = None
    status: OptimizationStatus = OptimizationStatus.PENDING
    rounds_completed: int = 0
    max_rounds: int = 3
    best_variant: PromptVariant | None = None
    baseline_score: float = 0.0
    all_variants: List[PromptVariant] = field(default_factory=list)
    started_at: float | None = None
    completed_at: float | None = None
    error_message: str | None = None
    # Issue #3222: quality-diversity archive (not serialised inline — persisted
    # separately under autoresearch:archive:{session_id})
    archive: "Archive" | None = field(default=None, repr=False)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "target": (
                {
                    "agent_name": self.target.agent_name,
                    "scorer_chain": self.target.scorer_chain,
                    "mutation_count": self.target.mutation_count,
                    "top_k": self.target.top_k,
                }
                if self.target
                else None
            ),
            "status": self.status.value,
            "rounds_completed": self.rounds_completed,
            "max_rounds": self.max_rounds,
            "best_variant": self.best_variant.to_dict() if self.best_variant else None,
            "baseline_score": self.baseline_score,
            "all_variants": [v.to_dict() for v in self.all_variants],
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error_message": self.error_message,
        }


# Type for benchmark functions: takes a prompt string, returns output string
BenchmarkFn = Callable[[str], Coroutine[Any, Any, str]]


class PromptOptimizer(AsyncRedisClientMixin):
    """Generic prompt optimizer with pluggable scorers.

    Drives a mutation -> benchmark -> score -> keep/discard loop.

    Agents other than autoresearch_hypothesis can opt in by calling
    ``register_optimization_target``.  The registry maps agent_id to a
    (PromptOptTarget, BenchmarkFn) pair so ``start_optimization`` can look
    them up without hard-coding names in the route layer.
    """

    _redis_database = "main"

    _MUTATION_SYSTEM_PROMPT = (
        "You are a prompt engineering expert. Generate {n} distinct variations "
        "of the following prompt template. Each variation should preserve the "
        "core intent but try a different approach: rephrasing, expanding detail, "
        "adding constraints, or restructuring.\n\n"
        "Return a JSON array of {n} strings, each being a complete prompt variant.\n\n"
        "Original prompt:\n{prompt}"
    )

    def __init__(
        self,
        scorers: Dict[str, PromptScorer],
        llm_service: Any,
        config: AutoResearchConfig | None = None,
    ) -> None:
        self._scorers = scorers
        self._llm = llm_service
        self._config = config or AutoResearchConfig()
        self._cancel_event = asyncio.Event()
        self._current_session: OptimizationSession | None = None
        # Registry: agent_id -> (PromptOptTarget, BenchmarkFn)
        self._targets: Dict[str, tuple] = {}

    def register_optimization_target(
        self,
        agent_id: str,
        target: PromptOptTarget,
        benchmark_fn: BenchmarkFn,
    ) -> None:
        """Register an agent so it can be addressed by start_optimization.

        Args:
            agent_id: Unique identifier used in StartOptimizationRequest.agent_name.
            target: Pre-configured PromptOptTarget for this agent.
            benchmark_fn: Async function that runs the prompt and returns output text.
        """
        self._targets[agent_id] = (target, benchmark_fn)
        logger.info("PromptOptimizer: registered optimization target %r", agent_id)

    def get_registered_targets(self) -> list:
        """Return a list of all registered agent_id strings."""
        return list(self._targets.keys())

    def get_target(self, agent_id: str) -> tuple | None:
        """Return (PromptOptTarget, BenchmarkFn) for agent_id, or None."""
        return self._targets.get(agent_id)

    async def optimize(
        self,
        target: PromptOptTarget,
        benchmark_fn: BenchmarkFn,
        max_rounds: int = 3,
    ) -> OptimizationSession:
        """Run the optimization loop for a target.

        Args:
            target: Agent's prompt optimization registration.
            benchmark_fn: Async function that runs the prompt and returns output.
            max_rounds: Number of mutation rounds.

        Returns:
            Completed OptimizationSession.
        """
        # Capture pre-cancel state before starting (caller may have called cancel())
        pre_cancelled = self._cancel_event.is_set()

        archive_max_size = getattr(target, "archive_max_size", target.top_k * 10)
        archive = Archive(max_size=archive_max_size)

        session = OptimizationSession(
            target=target,
            status=OptimizationStatus.RUNNING,
            max_rounds=max_rounds,
            started_at=time.time(),
            archive=archive,
        )
        self._current_session = session

        if not pre_cancelled:
            self._cancel_event.clear()

        current_best_prompt = target.current_prompt
        parent_id: str | None = None

        try:
            for round_num in range(1, max_rounds + 1):
                if self._cancel_event.is_set():
                    session.status = OptimizationStatus.CANCELLED
                    break

                logger.info(
                    "PromptOptimizer: round %d/%d for %s",
                    round_num,
                    max_rounds,
                    target.agent_name,
                )

                round_variants, failed_ids = await self._run_round(
                    current_best_prompt=current_best_prompt,
                    target=target,
                    benchmark_fn=benchmark_fn,
                    round_number=round_num,
                    session=session,
                )

                if round_variants:
                    current_best_prompt, parent_id = self._update_archive(
                        archive=archive,
                        round_variants=round_variants,
                        failed_ids=failed_ids,
                        parent_id=parent_id,
                        round_num=round_num,
                        session=session,
                    )

                session.rounds_completed = round_num
                await self._save_session(session)
                await self._save_archive(session.id, archive)

            if session.status == OptimizationStatus.RUNNING:
                session.status = OptimizationStatus.COMPLETED
        except Exception as exc:
            session.status = OptimizationStatus.FAILED
            session.error_message = str(exc)
            logger.exception("PromptOptimizer: optimization failed")
        finally:
            session.completed_at = time.time()
            await self._save_session(session)
            self._current_session = None

        return session

    def _update_archive(
        self,
        archive: Archive,
        round_variants: List[PromptVariant],
        failed_ids: set,
        parent_id: str | None,
        round_num: int,
        session: OptimizationSession,
    ) -> tuple:
        """Add round variants to archive, mark failures, select next parent.

        Returns (new_best_prompt, new_parent_id).
        """
        for v in round_variants:
            archive.add(
                VariantArchiveEntry(
                    variant_id=v.id,
                    variant=v,
                    score=v.final_score,
                    parent_id=parent_id,
                    generation=round_num,
                    valid_parent=v.id not in failed_ids,
                )
            )

        best_in_round = max(round_variants, key=lambda v: v.final_score)
        if best_in_round.final_score > session.baseline_score:
            session.best_variant = best_in_round
            session.baseline_score = best_in_round.final_score
            logger.info(
                "PromptOptimizer: new best variant %s (score=%.3f)",
                best_in_round.id,
                best_in_round.final_score,
            )

        chosen = archive.select_parent()
        if chosen is not None:
            logger.debug(
                "PromptOptimizer: selected parent %s (score=%.3f)",
                chosen.variant_id,
                chosen.score,
            )
            return chosen.variant.prompt_text, chosen.variant_id
        return best_in_round.prompt_text, best_in_round.id

    async def _run_round(
        self,
        current_best_prompt: str,
        target: PromptOptTarget,
        benchmark_fn: BenchmarkFn,
        round_number: int,
        session: OptimizationSession,
    ) -> tuple:
        """Execute a single mutation -> benchmark -> score round.

        Returns (variants, failed_ids) where failed_ids is the set of variant
        IDs that raised a scorer exception. Caller marks those invalid after
        adding all entries to the archive.
        """
        # 1. Mutate
        prompt_texts = await self._mutate_prompt(current_best_prompt, target.mutation_count)

        # 2. Benchmark each variant
        variants: List[PromptVariant] = []
        for prompt_text in prompt_texts:
            output = await benchmark_fn(prompt_text)
            variant = PromptVariant(
                prompt_text=prompt_text,
                output=output,
                round_number=round_number,
            )
            variants.append(variant)

        # 3. Score through the chain with staged gating; collect failed IDs
        failed_ids = await self._score_through_chain(
            variants=variants,
            target=target,
            session=session,
        )

        session.all_variants.extend(variants)
        return variants, failed_ids

    async def _score_through_chain(
        self,
        variants: List[PromptVariant],
        target: PromptOptTarget,
        session: OptimizationSession,
    ) -> set:
        """Run staged scoring chain with threshold gating between tiers.

        Tier-1 uses subset_fraction for cheap evaluation.  Variants that do
        not clear staged_eval_threshold are finalized at their current score
        and excluded from subsequent (more expensive) tiers.

        Returns the set of variant IDs that raised a scorer exception.
        """
        candidates = list(variants)
        threshold = self._config.staged_eval_threshold
        failed_ids: set = set()

        for tier_idx, scorer_name in enumerate(target.scorer_chain):
            scorer = self._scorers.get(scorer_name)
            if scorer is None:
                logger.warning("PromptOptimizer: scorer %r not found, skipping", scorer_name)
                continue

            subset_frac = self._config.staged_eval_fraction if tier_idx == 0 else None
            candidates, tier_failed = await self._score_tier(
                scorer=scorer,
                scorer_name=scorer_name,
                variants=candidates,
                session=session,
                subset_fraction=subset_frac,
            )
            failed_ids.update(tier_failed)

            # Gate: drop variants below threshold before next tier
            passed = [v for v in candidates if v.final_score >= threshold]
            gated_out = len(candidates) - len(passed)
            if gated_out:
                logger.info(
                    "PromptOptimizer: staged gate after %r — %d variant(s) below " "threshold %.2f (kept %d)",
                    scorer_name,
                    gated_out,
                    threshold,
                    len(passed),
                )
            candidates = passed

            if not candidates:
                logger.info("PromptOptimizer: no candidates passed gate after %r", scorer_name)
                break

        return failed_ids

    async def _score_tier(
        self,
        scorer: PromptScorer,
        scorer_name: str,
        variants: List[PromptVariant],
        session: OptimizationSession,
        subset_fraction: float | None,
    ) -> tuple:
        """Score all variants with one scorer and update final_score.

        Returns (variants, failed_ids) where failed_ids contains IDs of
        variants that raised a scorer exception.
        """
        failed_ids: set = set()
        for variant in variants:
            try:
                result = await scorer.score(
                    variant.output,
                    {"session_id": session.id, "variant_id": variant.id},
                    subset_fraction=subset_fraction,
                )
                variant.scores[scorer_name] = result.score
                variant.final_score = sum(variant.scores.values()) / len(variant.scores)
            except Exception as exc:
                logger.warning(
                    "PromptOptimizer: scorer %r failed for variant %s: %s",
                    scorer_name,
                    variant.id,
                    exc,
                )
                failed_ids.add(variant.id)
        return variants, failed_ids

    async def _mutate_prompt(self, base_prompt: str, n: int) -> List[str]:
        """Generate N prompt variants using LLM."""
        system_msg = self._MUTATION_SYSTEM_PROMPT.format(n=n, prompt=base_prompt)

        try:
            response = await self._llm.chat(
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": "Generate the variants now."},
                ],
                temperature=0.9,
                max_tokens=2000,
            )
            variants = json.loads(response.content)
            if isinstance(variants, list):
                return [str(v) for v in variants[:n]]
        except (json.JSONDecodeError, Exception) as exc:
            logger.warning("PromptOptimizer: mutation failed: %s", exc)

        return [base_prompt]  # fallback: return original

    def cancel(self) -> None:
        """Signal the running optimization to stop."""
        self._cancel_event.set()

    @property
    def current_session(self) -> OptimizationSession | None:
        return self._current_session

    async def _save_session(self, session: OptimizationSession) -> None:
        """Persist session to Redis."""
        try:
            redis = await self._get_redis()
            key = f"autoresearch:prompt_opt:session:{session.id}"
            await redis.set(key, json.dumps(session.to_dict()), ex=TTL_7_DAYS)
        except Exception:
            logger.exception("Failed to save optimization session %s", session.id)

    async def _save_archive(self, session_id: str, archive: "Archive") -> None:
        """Persist quality-diversity archive to Redis.

        Key: autoresearch:archive:{session_id}  (Issue #3222)
        """
        try:
            redis = await self._get_redis()
            key = f"autoresearch:archive:{session_id}"
            await redis.set(key, archive.to_json(), ex=TTL_7_DAYS)
        except Exception:
            logger.exception("Failed to save archive for session %s", session_id)

    async def load_archive(self, session_id: str) -> "Archive" | None:
        """Restore a previously persisted archive from Redis."""
        try:
            redis = await self._get_redis()
            key = f"autoresearch:archive:{session_id}"
            raw = await redis.get(key)
            if raw is None:
                return None
            return Archive.from_json(
                raw if isinstance(raw, str) else raw.decode("utf-8"),
                PromptVariant,
            )
        except Exception:
            logger.exception("Failed to load archive for session %s", session_id)
            return None
