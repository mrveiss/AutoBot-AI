# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Pluggable scorer interface for prompt optimization.

Issue #2600: Defines the scoring contract and concrete scorers for
evaluating prompt variants — LLM-as-judge for bulk filtering,
human review for top candidates, val_bpb for AutoResearch.
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict

from autobot_shared.redis_mixin import AsyncRedisClientMixin

if TYPE_CHECKING:
    from services.llm_service import LLMService

from autobot_shared.logging_manager import get_logger
from constants.ttl_constants import TTL_24_HOURS

logger = get_logger(__name__)

# Validation pattern for Redis key components — alphanumeric, hyphens, underscores
_KEY_COMPONENT_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")

# Shared Redis key format strings for human-review scoring.
# routes.py imports HUMAN_REVIEW_NOTIFY_KEY so both sides of the BLPOP
# protocol always reference the same key pattern.
HUMAN_REVIEW_NOTIFY_KEY = "autoresearch:prompt_review:notify:{session_id}:{variant_id}"


@dataclass
class ScorerResult:
    """Result from a single scoring evaluation."""

    score: float  # normalized 0.0-1.0
    raw_score: Any  # scorer-specific value
    metadata: Dict[str, Any] = field(default_factory=dict)
    scorer_name: str = ""

    def __post_init__(self) -> None:
        self.score = max(0.0, min(1.0, self.score))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "score": self.score,
            "raw_score": self.raw_score,
            "metadata": self.metadata,
            "scorer_name": self.scorer_name,
        }


class PromptScorer(ABC):
    """Abstract base for prompt variant scorers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique scorer identifier."""

    @abstractmethod
    async def score(
        self,
        prompt_output: str,
        context: Dict[str, Any],
        subset_fraction: float | None = None,
    ) -> ScorerResult:
        """Score a prompt variant's output.

        Args:
            prompt_output: The text produced by running the prompt variant.
            context: Scorer-specific context (hyperparams, criteria, etc.).
            subset_fraction: If provided (0 < value <= 1), evaluate on this
                fraction of benchmark samples instead of the full set.
                Scorers that do not support subset evaluation ignore this
                parameter.  Pass None (default) for full evaluation.

        Returns:
            ScorerResult with normalized score.
        """


from .models import Experiment, ExperimentTask, HyperParams
from .runner import ExperimentRunner, build_task_inference_params


class ValBpbScorer(PromptScorer):
    """Score prompt variants by running an AutoResearch experiment.

    Uses the prompt output as the hypothesis, runs training via
    ExperimentRunner, and scores by val_bpb improvement over baseline.
    """

    def __init__(
        self,
        runner: ExperimentRunner,
        baseline_val_bpb: float,
    ) -> None:
        if baseline_val_bpb <= 0:
            raise ValueError(f"baseline_val_bpb must be positive, got {baseline_val_bpb}")
        self._runner = runner
        self._baseline = baseline_val_bpb

    @property
    def name(self) -> str:
        return "val_bpb"

    async def score(
        self,
        prompt_output: str,
        context: Dict[str, Any],
        subset_fraction: float | None = None,
    ) -> ScorerResult:
        # subset_fraction is informational for this scorer; full experiment
        # is always required to get a valid val_bpb reading.
        if subset_fraction is not None:
            logger.debug(
                "ValBpbScorer: subset_fraction=%s ignored — full experiment required",
                subset_fraction,
            )
        hp_data = context.get("hyperparams", {})
        hp = HyperParams.from_dict(hp_data) if hp_data else HyperParams()

        # Issue #3259: ValBpb requires deterministic (greedy) output — always
        # set required_temperature=0.0 so the dispatcher overrides whatever
        # experiment-level temperature is configured.
        task = ExperimentTask(
            prompt=prompt_output,
            required_temperature=0.0,
        )
        experiment = Experiment(
            hypothesis=prompt_output,
            description="Prompt optimizer variant",
            hyperparams=hp,
        )
        inference_params = build_task_inference_params(task, experiment)
        logger.debug(
            "ValBpbScorer: dispatching with temperature=%s",
            inference_params["temperature"],
        )

        experiment = await self._runner.run_experiment(experiment)

        val_bpb = experiment.result.val_bpb if experiment.result and experiment.result.val_bpb is not None else None

        if val_bpb is None:
            return ScorerResult(
                score=0.0,
                raw_score=None,
                metadata={"error": (experiment.result.error_message if experiment.result else "no result")},
                scorer_name=self.name,
            )

        # Normalize: improvement as fraction of baseline, clamped 0-1
        improvement = self._baseline - val_bpb
        normalized = max(0.0, improvement / self._baseline) if self._baseline > 0 else 0.0

        return ScorerResult(
            score=normalized,
            raw_score=val_bpb,
            metadata={
                "baseline": self._baseline,
                "improvement": improvement,
                "state": experiment.state.value,
            },
            scorer_name=self.name,
        )


_RATING_PATTERN = re.compile(r"(\d+)\s*(?:/\s*10|out of\s*10)")

_JUDGE_SYSTEM_PROMPT = (
    "You are a prompt quality evaluator. Rate the following output on a scale "
    "of 0-10 based on these criteria: {criteria}.\n\n"
    'Respond with JSON: {{"rating": <0-10>, "reasoning": "<brief explanation>"}}'
)


class LLMJudgeScorer(PromptScorer):
    """Score prompt variants using an LLM as judge.

    Sends the prompt output to LLMService with evaluation criteria,
    parses a 0-10 rating, normalizes to 0.0-1.0.
    """

    def __init__(
        self,
        llm_service: "LLMService",
        criteria: list[str],
    ) -> None:
        self._llm = llm_service
        self._criteria = criteria

    @property
    def name(self) -> str:
        return "llm_judge"

    async def score(
        self,
        prompt_output: str,
        context: Dict[str, Any],
        subset_fraction: float | None = None,
    ) -> ScorerResult:
        # subset_fraction: LLMJudgeScorer evaluates a single output text so
        # sub-sampling is not applicable; parameter accepted for interface compat.
        criteria_str = ", ".join(self._criteria)
        system_msg = _JUDGE_SYSTEM_PROMPT.format(criteria=criteria_str)

        try:
            response = await self._llm.chat(
                messages=[
                    {"role": "system", "content": system_msg},
                    {
                        "role": "user",
                        "content": f"Evaluate this output:\n\n{prompt_output}",
                    },
                ],
                temperature=0.1,
                max_tokens=200,
            )
            rating = self._parse_rating(response.content)
        except Exception as exc:
            logger.warning("LLMJudgeScorer: LLM call failed: %s", exc)
            return ScorerResult(
                score=0.0,
                raw_score=None,
                metadata={"error": str(exc)},
                scorer_name=self.name,
            )

        return ScorerResult(
            score=rating / 10.0,
            raw_score=rating,
            metadata={"criteria": self._criteria},
            scorer_name=self.name,
        )

    @staticmethod
    def _parse_rating(content: str) -> int:
        """Extract rating from LLM response — try JSON first, then regex."""
        try:
            data = json.loads(content)
            raw = int(data["rating"])
            return max(0, min(10, raw))
        except (json.JSONDecodeError, KeyError, ValueError, TypeError):
            pass

        match = _RATING_PATTERN.search(content)
        if match:
            return max(0, min(10, int(match.group(1))))

        logger.warning("LLMJudgeScorer: could not parse rating from: %s", content[:100])
        return 0


class HumanReviewScorer(AsyncRedisClientMixin, PromptScorer):
    """Queue a prompt variant for human review and wait for a score via BLPOP.

    Stores the variant in Redis; the API endpoint allows humans to
    submit a 0-10 score and pushes a notification to the notify key.
    Uses BLPOP instead of polling to avoid wasting async slots.

    The writer (routes.py submit_variant_score) must LPUSH to the
    _NOTIFY_KEY after SET-ting the _REVIEW_KEY result.
    """

    _REVIEW_KEY = "autoresearch:prompt_review:{session_id}:{variant_id}"
    _PENDING_KEY = "autoresearch:prompt_review:pending:{session_id}:{variant_id}"
    _NOTIFY_KEY = HUMAN_REVIEW_NOTIFY_KEY
    _TTL_SECONDS = TTL_24_HOURS
    _redis_database = "main"

    def __init__(
        self,
        poll_interval: float = 5.0,
        timeout: float = 300.0,
    ) -> None:
        # poll_interval is kept for interface compatibility but no longer used
        # internally — BLPOP blocks efficiently without periodic wakeups.
        self._poll_interval = poll_interval
        self._timeout = timeout

    @property
    def name(self) -> str:
        return "human_review"

    @staticmethod
    def _validate_key_component(value: str, name: str) -> str:
        """Validate a string is safe for use in Redis key patterns."""
        if not _KEY_COMPONENT_PATTERN.match(value):
            raise ValueError(f"{name} must be alphanumeric/hyphens/underscores (1-64 chars), got {value!r}")
        return value

    async def score(
        self,
        prompt_output: str,
        context: Dict[str, Any],
        subset_fraction: float | None = None,
    ) -> ScorerResult:
        # subset_fraction: HumanReviewScorer queues the variant for a human;
        # sub-sampling does not apply — parameter accepted for interface compat.
        session_id = self._validate_key_component(context.get("session_id", "unknown"), "session_id")
        variant_id = self._validate_key_component(context.get("variant_id", "unknown"), "variant_id")

        redis = await self._get_redis()

        # Store pending review — only safe fields, not raw context
        pending_key = self._PENDING_KEY.format(session_id=session_id, variant_id=variant_id)
        await redis.set(
            pending_key,
            json.dumps(
                {
                    "prompt_output": prompt_output[:5000],
                    "session_id": session_id,
                    "variant_id": variant_id,
                }
            ),
            ex=self._TTL_SECONDS,
        )

        review_key = self._REVIEW_KEY.format(session_id=session_id, variant_id=variant_id)
        notify_key = self._NOTIFY_KEY.format(session_id=session_id, variant_id=variant_id)

        # Check if the result was already written before we start waiting —
        # avoids a race where the human submits between SET and BLPOP.
        raw = await redis.get(review_key)
        if raw is None:
            # Block until the writer pushes to notify_key or the timeout fires.
            # BLPOP returns (key, value) on success or None on timeout.
            blpop_result = await redis.blpop(notify_key, timeout=int(self._timeout))
            if blpop_result is None:
                logger.info(
                    "HumanReviewScorer: timed out for session=%s variant=%s",
                    session_id,
                    variant_id,
                )
                return ScorerResult(
                    score=0.0,
                    raw_score=None,
                    metadata={"status": "timeout"},
                    scorer_name=self.name,
                )
            # Notification received — clean up the notify key (BLPOP already
            # consumed the item) and read the actual result.
            raw = await redis.get(review_key)

        if raw is None:
            # Notify key fired but result key is missing — treat as timeout.
            logger.warning(
                "HumanReviewScorer: notify fired but review key absent " "for session=%s variant=%s",
                session_id,
                variant_id,
            )
            return ScorerResult(
                score=0.0,
                raw_score=None,
                metadata={"status": "timeout"},
                scorer_name=self.name,
            )

        data = json.loads(raw if isinstance(raw, str) else raw.decode("utf-8"))
        rating = max(0, min(10, int(data.get("score", 0))))
        return ScorerResult(
            score=rating / 10.0,
            raw_score=rating,
            metadata={
                "comment": data.get("comment", ""),
                "status": "reviewed",
            },
            scorer_name=self.name,
        )
