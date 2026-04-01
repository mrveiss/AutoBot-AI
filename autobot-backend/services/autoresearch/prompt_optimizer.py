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
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional

from .scorers import PromptScorer, ScorerResult

logger = logging.getLogger(__name__)


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


@dataclass
class OptimizationSession:
    """Top-level record for a prompt optimization run."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    target: Optional[PromptOptTarget] = None
    status: OptimizationStatus = OptimizationStatus.PENDING
    rounds_completed: int = 0
    max_rounds: int = 3
    best_variant: Optional[PromptVariant] = None
    baseline_score: float = 0.0
    all_variants: List[PromptVariant] = field(default_factory=list)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "target": {
                "agent_name": self.target.agent_name,
                "scorer_chain": self.target.scorer_chain,
                "mutation_count": self.target.mutation_count,
                "top_k": self.target.top_k,
            }
            if self.target
            else None,
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


class PromptOptimizer:
    """Generic prompt optimizer with pluggable scorers.

    Drives a mutation -> benchmark -> score -> keep/discard loop.
    """

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
    ) -> None:
        self._scorers = scorers
        self._llm = llm_service
        self._cancel_event = asyncio.Event()
        self._current_session: Optional[OptimizationSession] = None
        self._redis = None

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

        session = OptimizationSession(
            target=target,
            status=OptimizationStatus.RUNNING,
            max_rounds=max_rounds,
            started_at=time.time(),
        )
        self._current_session = session

        if not pre_cancelled:
            self._cancel_event.clear()

        current_best_prompt = target.current_prompt

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

                round_variants = await self._run_round(
                    current_best_prompt=current_best_prompt,
                    target=target,
                    benchmark_fn=benchmark_fn,
                    round_number=round_num,
                    session=session,
                )

                if round_variants:
                    best_in_round = max(round_variants, key=lambda v: v.final_score)
                    if best_in_round.final_score > session.baseline_score:
                        session.best_variant = best_in_round
                        session.baseline_score = best_in_round.final_score
                        current_best_prompt = best_in_round.prompt_text
                        logger.info(
                            "PromptOptimizer: new best variant %s (score=%.3f)",
                            best_in_round.id,
                            best_in_round.final_score,
                        )

                session.rounds_completed = round_num
                await self._save_session(session)

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

    async def _run_round(
        self,
        current_best_prompt: str,
        target: PromptOptTarget,
        benchmark_fn: BenchmarkFn,
        round_number: int,
        session: OptimizationSession,
    ) -> List[PromptVariant]:
        """Execute a single mutation -> benchmark -> score round."""
        # 1. Mutate
        prompt_texts = await self._mutate_prompt(
            current_best_prompt, target.mutation_count
        )

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

        # 3. Score through the chain
        candidates = variants
        for scorer_name in target.scorer_chain:
            scorer = self._scorers.get(scorer_name)
            if scorer is None:
                logger.warning(
                    "PromptOptimizer: scorer %r not found, skipping", scorer_name
                )
                continue

            for variant in candidates:
                result = await scorer.score(
                    variant.output,
                    {
                        "session_id": session.id,
                        "variant_id": variant.id,
                    },
                )
                variant.scores[scorer_name] = result.score
                # Final score = average across all scorers so far
                variant.final_score = (
                    sum(variant.scores.values()) / len(variant.scores)
                )

            # Keep top-K for next scorer
            candidates = sorted(
                candidates, key=lambda v: v.final_score, reverse=True
            )[: target.top_k]

        session.all_variants.extend(variants)
        return candidates

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
    def current_session(self) -> Optional[OptimizationSession]:
        return self._current_session

    async def _get_redis(self):
        if self._redis is None:
            from autobot_shared.redis_client import get_redis_client

            self._redis = get_redis_client(async_client=True, database="main")
        return self._redis

    async def _save_session(self, session: OptimizationSession) -> None:
        """Persist session to Redis."""
        try:
            redis = await self._get_redis()
            key = f"autoresearch:prompt_opt:session:{session.id}"
            await redis.set(key, json.dumps(session.to_dict()), ex=86400 * 7)
        except Exception:
            logger.exception("Failed to save optimization session %s", session.id)
