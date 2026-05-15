# AutoResearch M3: Self-Improvement + Frontend Dashboard — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a generic prompt optimizer with pluggable scorers, a knowledge synthesizer for distilled experiment insights, and a Vue 3 experiment dashboard with inline approval and notification integration.

**Architecture:** Layered backend services (scorers → prompt optimizer → knowledge synthesizer) added to the existing `services/autoresearch/` package. New API endpoints extend the existing router. Vue 3 frontend with composable + Pinia store + modular components.

**Tech Stack:** Python 3.11+, FastAPI, Redis, ChromaDB, LLMService, Vue 3 (Composition API), TypeScript, Tailwind CSS 4, ApexCharts, Pinia

**Spec:** `docs/superpowers/specs/2026-04-01-autoresearch-m3-design.md`
**Issue:** #2600 (child of #1440)

---

## Phase 1: Backend

### Task 1: Scorer Interface + ScorerResult Model

**Files:**
- Create: `autobot-backend/services/autoresearch/scorers.py`
- Create: `autobot-backend/services/autoresearch/scorers_test.py`

- [ ] **Step 1: Write the failing test for ScorerResult**

```python
# autobot-backend/services/autoresearch/scorers_test.py

# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for autoresearch scorers — Issue #2600."""

from __future__ import annotations

import pytest

from services.autoresearch.scorers import ScorerResult


class TestScorerResult:
    def test_to_dict(self):
        result = ScorerResult(
            score=0.85,
            raw_score=4.2,
            metadata={"model": "test"},
            scorer_name="test_scorer",
        )
        d = result.to_dict()
        assert d["score"] == 0.85
        assert d["raw_score"] == 4.2
        assert d["metadata"] == {"model": "test"}
        assert d["scorer_name"] == "test_scorer"

    def test_score_clamped_to_range(self):
        result = ScorerResult(score=1.5, raw_score=1.5, metadata={}, scorer_name="t")
        assert result.score == 1.0

    def test_score_floor(self):
        result = ScorerResult(score=-0.5, raw_score=-0.5, metadata={}, scorer_name="t")
        assert result.score == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd autobot-backend && python -m pytest services/autoresearch/scorers_test.py::TestScorerResult -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'services.autoresearch.scorers'`

- [ ] **Step 3: Implement ScorerResult and PromptScorer ABC**

```python
# autobot-backend/services/autoresearch/scorers.py

# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Pluggable scorer interface for prompt optimization.

Issue #2600: Defines the scoring contract and concrete scorers for
evaluating prompt variants — LLM-as-judge for bulk filtering,
human review for top candidates, val_bpb for AutoResearch.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


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
    async def score(self, prompt_output: str, context: Dict[str, Any]) -> ScorerResult:
        """Score a prompt variant's output.

        Args:
            prompt_output: The text produced by running the prompt variant.
            context: Scorer-specific context (hyperparams, criteria, etc.).

        Returns:
            ScorerResult with normalized score.
        """
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd autobot-backend && python -m pytest services/autoresearch/scorers_test.py::TestScorerResult -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add autobot-backend/services/autoresearch/scorers.py autobot-backend/services/autoresearch/scorers_test.py
git commit -m "feat(autoresearch): add scorer interface and ScorerResult model (#2600)"
```

---

### Task 2: ValBpbScorer

**Files:**
- Modify: `autobot-backend/services/autoresearch/scorers.py`
- Modify: `autobot-backend/services/autoresearch/scorers_test.py`

- [ ] **Step 1: Write the failing test**

```python
# Append to scorers_test.py

from unittest.mock import AsyncMock, MagicMock

from services.autoresearch.models import Experiment, ExperimentResult, ExperimentState
from services.autoresearch.scorers import ValBpbScorer


class TestValBpbScorer:
    @pytest.fixture
    def mock_runner(self):
        runner = AsyncMock()
        return runner

    @pytest.fixture
    def scorer(self, mock_runner):
        return ValBpbScorer(runner=mock_runner, baseline_val_bpb=5.0)

    @pytest.mark.asyncio
    async def test_score_improvement(self, scorer, mock_runner):
        experiment = Experiment(state=ExperimentState.KEPT)
        experiment.result = ExperimentResult(val_bpb=4.5)
        experiment.baseline_val_bpb = 5.0
        mock_runner.run_experiment.return_value = experiment

        result = await scorer.score(
            "test hypothesis",
            {"hyperparams": {}},
        )
        assert result.score > 0.0
        assert result.raw_score == 4.5
        assert result.scorer_name == "val_bpb"

    @pytest.mark.asyncio
    async def test_score_no_improvement(self, scorer, mock_runner):
        experiment = Experiment(state=ExperimentState.DISCARDED)
        experiment.result = ExperimentResult(val_bpb=5.5)
        experiment.baseline_val_bpb = 5.0
        mock_runner.run_experiment.return_value = experiment

        result = await scorer.score("test hypothesis", {"hyperparams": {}})
        assert result.score == 0.0
        assert result.raw_score == 5.5

    @pytest.mark.asyncio
    async def test_score_failed_experiment(self, scorer, mock_runner):
        experiment = Experiment(state=ExperimentState.FAILED)
        experiment.result = ExperimentResult(error_message="OOM")
        mock_runner.run_experiment.return_value = experiment

        result = await scorer.score("test hypothesis", {"hyperparams": {}})
        assert result.score == 0.0
        assert result.raw_score is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd autobot-backend && python -m pytest services/autoresearch/scorers_test.py::TestValBpbScorer -v`
Expected: FAIL — `ImportError: cannot import name 'ValBpbScorer'`

- [ ] **Step 3: Implement ValBpbScorer**

Append to `scorers.py`:

```python
from .models import Experiment, ExperimentResult, HyperParams
from .runner import ExperimentRunner


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
        self._runner = runner
        self._baseline = baseline_val_bpb

    @property
    def name(self) -> str:
        return "val_bpb"

    async def score(self, prompt_output: str, context: Dict[str, Any]) -> ScorerResult:
        hp_data = context.get("hyperparams", {})
        hp = HyperParams.from_dict(hp_data) if hp_data else HyperParams()

        experiment = Experiment(
            hypothesis=prompt_output,
            description="Prompt optimizer variant",
            hyperparams=hp,
        )

        experiment = await self._runner.run_experiment(experiment)

        val_bpb = (
            experiment.result.val_bpb
            if experiment.result and experiment.result.val_bpb is not None
            else None
        )

        if val_bpb is None:
            return ScorerResult(
                score=0.0,
                raw_score=None,
                metadata={"error": experiment.result.error_message if experiment.result else "no result"},
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd autobot-backend && python -m pytest services/autoresearch/scorers_test.py::TestValBpbScorer -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add autobot-backend/services/autoresearch/scorers.py autobot-backend/services/autoresearch/scorers_test.py
git commit -m "feat(autoresearch): add ValBpbScorer for experiment-based scoring (#2600)"
```

---

### Task 3: LLMJudgeScorer

**Files:**
- Modify: `autobot-backend/services/autoresearch/scorers.py`
- Modify: `autobot-backend/services/autoresearch/scorers_test.py`

- [ ] **Step 1: Write the failing test**

```python
# Append to scorers_test.py

from services.autoresearch.scorers import LLMJudgeScorer


class TestLLMJudgeScorer:
    @pytest.fixture
    def mock_llm(self):
        llm = AsyncMock()
        return llm

    @pytest.fixture
    def scorer(self, mock_llm):
        return LLMJudgeScorer(
            llm_service=mock_llm,
            criteria=["relevance", "specificity", "actionability"],
        )

    @pytest.mark.asyncio
    async def test_score_parses_llm_rating(self, scorer, mock_llm):
        mock_response = MagicMock()
        mock_response.content = '{"rating": 8, "reasoning": "Good hypothesis"}'
        mock_llm.chat.return_value = mock_response

        result = await scorer.score("A detailed hypothesis", {})
        assert result.score == 0.8  # 8/10 normalized
        assert result.raw_score == 8
        assert result.scorer_name == "llm_judge"

    @pytest.mark.asyncio
    async def test_score_handles_non_json_response(self, scorer, mock_llm):
        mock_response = MagicMock()
        mock_response.content = "I rate this 7 out of 10"
        mock_llm.chat.return_value = mock_response

        result = await scorer.score("A hypothesis", {})
        # Falls back to regex extraction
        assert result.score == 0.7
        assert result.raw_score == 7

    @pytest.mark.asyncio
    async def test_score_handles_llm_failure(self, scorer, mock_llm):
        mock_llm.chat.side_effect = Exception("LLM unavailable")

        result = await scorer.score("A hypothesis", {})
        assert result.score == 0.0
        assert "error" in result.metadata
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd autobot-backend && python -m pytest services/autoresearch/scorers_test.py::TestLLMJudgeScorer -v`
Expected: FAIL — `ImportError: cannot import name 'LLMJudgeScorer'`

- [ ] **Step 3: Implement LLMJudgeScorer**

Append to `scorers.py`:

```python
import re


_RATING_PATTERN = re.compile(r"(\d+)\s*(?:/\s*10|out of\s*10)")

_JUDGE_SYSTEM_PROMPT = (
    "You are a prompt quality evaluator. Rate the following output on a scale "
    "of 0-10 based on these criteria: {criteria}.\n\n"
    "Respond with JSON: {{\"rating\": <0-10>, \"reasoning\": \"<brief explanation>\"}}"
)


class LLMJudgeScorer(PromptScorer):
    """Score prompt variants using an LLM as judge.

    Sends the prompt output to LLMService with evaluation criteria,
    parses a 0-10 rating, normalizes to 0.0-1.0.
    """

    def __init__(
        self,
        llm_service: Any,
        criteria: list[str],
    ) -> None:
        self._llm = llm_service
        self._criteria = criteria

    @property
    def name(self) -> str:
        return "llm_judge"

    async def score(self, prompt_output: str, context: Dict[str, Any]) -> ScorerResult:
        criteria_str = ", ".join(self._criteria)
        system_msg = _JUDGE_SYSTEM_PROMPT.format(criteria=criteria_str)

        try:
            response = await self._llm.chat(
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": f"Evaluate this output:\n\n{prompt_output}"},
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd autobot-backend && python -m pytest services/autoresearch/scorers_test.py::TestLLMJudgeScorer -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add autobot-backend/services/autoresearch/scorers.py autobot-backend/services/autoresearch/scorers_test.py
git commit -m "feat(autoresearch): add LLMJudgeScorer for automated prompt evaluation (#2600)"
```

---

### Task 4: HumanReviewScorer

**Files:**
- Modify: `autobot-backend/services/autoresearch/scorers.py`
- Modify: `autobot-backend/services/autoresearch/scorers_test.py`

- [ ] **Step 1: Write the failing test**

```python
# Append to scorers_test.py

from services.autoresearch.scorers import HumanReviewScorer


class TestHumanReviewScorer:
    @pytest.fixture
    def mock_redis(self):
        redis = AsyncMock()
        return redis

    @pytest.fixture
    def scorer(self, mock_redis):
        s = HumanReviewScorer(poll_interval=0.01, timeout=0.05)
        s._redis = mock_redis
        return s

    @pytest.mark.asyncio
    async def test_score_approved_with_rating(self, scorer, mock_redis):
        # Simulate human submitting a score
        mock_redis.get.side_effect = [
            None,  # first poll: no score yet
            json.dumps({"score": 9, "comment": "excellent"}).encode(),  # second poll
        ]
        result = await scorer.score(
            "test output",
            {"session_id": "s1", "variant_id": "v1"},
        )
        assert result.score == 0.9
        assert result.raw_score == 9
        assert result.scorer_name == "human_review"

    @pytest.mark.asyncio
    async def test_score_timeout_returns_none(self, scorer, mock_redis):
        mock_redis.get.return_value = None  # never receives a score

        result = await scorer.score(
            "test output",
            {"session_id": "s1", "variant_id": "v1"},
        )
        assert result.score == 0.0
        assert result.metadata.get("status") == "timeout"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd autobot-backend && python -m pytest services/autoresearch/scorers_test.py::TestHumanReviewScorer -v`
Expected: FAIL — `ImportError: cannot import name 'HumanReviewScorer'`

- [ ] **Step 3: Implement HumanReviewScorer**

Append to `scorers.py`:

```python
class HumanReviewScorer(PromptScorer):
    """Queue a prompt variant for human review and poll for a score.

    Stores the variant in Redis; the API endpoint allows humans to
    submit a 0-10 score. Polls until scored or timeout.
    """

    _REVIEW_KEY = "autoresearch:prompt_review:{session_id}:{variant_id}"
    _PENDING_KEY = "autoresearch:prompt_review:pending:{session_id}:{variant_id}"
    _TTL_SECONDS = 86400

    def __init__(
        self,
        poll_interval: float = 5.0,
        timeout: float = 300.0,
    ) -> None:
        self._poll_interval = poll_interval
        self._timeout = timeout
        self._redis = None

    async def _get_redis(self):
        if self._redis is None:
            from autobot_shared.redis_client import get_redis_client

            self._redis = get_redis_client(async_client=True, database="main")
        return self._redis

    @property
    def name(self) -> str:
        return "human_review"

    async def score(self, prompt_output: str, context: Dict[str, Any]) -> ScorerResult:
        session_id = context.get("session_id", "unknown")
        variant_id = context.get("variant_id", "unknown")

        redis = await self._get_redis()

        # Store pending review
        pending_key = self._PENDING_KEY.format(
            session_id=session_id, variant_id=variant_id
        )
        await redis.set(
            pending_key,
            json.dumps({"prompt_output": prompt_output[:5000], "context": context}),
            ex=self._TTL_SECONDS,
        )

        # Poll for score
        review_key = self._REVIEW_KEY.format(
            session_id=session_id, variant_id=variant_id
        )
        deadline = time.monotonic() + self._timeout

        while time.monotonic() < deadline:
            raw = await redis.get(review_key)
            if raw is not None:
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
            await asyncio.sleep(self._poll_interval)

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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd autobot-backend && python -m pytest services/autoresearch/scorers_test.py::TestHumanReviewScorer -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add autobot-backend/services/autoresearch/scorers.py autobot-backend/services/autoresearch/scorers_test.py
git commit -m "feat(autoresearch): add HumanReviewScorer for manual prompt evaluation (#2600)"
```

---

### Task 5: Prompt Optimizer — Models and Core Loop

**Files:**
- Create: `autobot-backend/services/autoresearch/prompt_optimizer.py`
- Create: `autobot-backend/services/autoresearch/prompt_optimizer_test.py`

- [ ] **Step 1: Write the failing test for PromptVariant and OptimizationSession**

```python
# autobot-backend/services/autoresearch/prompt_optimizer_test.py

# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for prompt optimizer — Issue #2600."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from services.autoresearch.prompt_optimizer import (
    OptimizationSession,
    OptimizationStatus,
    PromptOptTarget,
    PromptVariant,
)


class TestPromptVariantModel:
    def test_to_dict(self):
        variant = PromptVariant(
            id="v1",
            prompt_text="test prompt",
            output="test output",
            scores={"llm_judge": 0.8},
            final_score=0.8,
        )
        d = variant.to_dict()
        assert d["id"] == "v1"
        assert d["prompt_text"] == "test prompt"
        assert d["scores"] == {"llm_judge": 0.8}
        assert d["final_score"] == 0.8


class TestOptimizationSession:
    def test_to_dict(self):
        target = PromptOptTarget(
            agent_name="test_agent",
            current_prompt="base prompt",
            scorer_chain=["llm_judge"],
            mutation_count=3,
            top_k=1,
        )
        session = OptimizationSession(target=target)
        d = session.to_dict()
        assert d["status"] == "pending"
        assert d["target"]["agent_name"] == "test_agent"
        assert d["rounds_completed"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd autobot-backend && python -m pytest services/autoresearch/prompt_optimizer_test.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement models and PromptOptimizer class**

```python
# autobot-backend/services/autoresearch/prompt_optimizer.py

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

    Drives a mutation → benchmark → score → keep/discard loop.
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
        session = OptimizationSession(
            target=target,
            status=OptimizationStatus.RUNNING,
            max_rounds=max_rounds,
            started_at=time.time(),
        )
        self._current_session = session
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
        """Execute a single mutation → benchmark → score round."""
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
                logger.warning("PromptOptimizer: scorer %r not found, skipping", scorer_name)
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
                variant.final_score = result.score

            # Keep top-K for next scorer
            candidates = sorted(candidates, key=lambda v: v.final_score, reverse=True)[
                : target.top_k
            ]

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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd autobot-backend && python -m pytest services/autoresearch/prompt_optimizer_test.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add autobot-backend/services/autoresearch/prompt_optimizer.py autobot-backend/services/autoresearch/prompt_optimizer_test.py
git commit -m "feat(autoresearch): add PromptOptimizer with mutation and scorer chain (#2600)"
```

---

### Task 6: Prompt Optimizer — Optimization Loop Tests

**Files:**
- Modify: `autobot-backend/services/autoresearch/prompt_optimizer_test.py`

- [ ] **Step 1: Write the failing test for the full optimization loop**

```python
# Append to prompt_optimizer_test.py

import json

from services.autoresearch.prompt_optimizer import PromptOptimizer
from services.autoresearch.scorers import ScorerResult


class TestPromptOptimizerLoop:
    @pytest.fixture
    def mock_llm(self):
        llm = AsyncMock()
        # Return 3 variants as JSON array
        mock_response = MagicMock()
        mock_response.content = json.dumps(["variant A", "variant B", "variant C"])
        llm.chat.return_value = mock_response
        return llm

    @pytest.fixture
    def mock_scorer(self):
        scorer = AsyncMock()
        scorer.name = "test_scorer"
        scorer.score.side_effect = [
            ScorerResult(score=0.3, raw_score=3, metadata={}, scorer_name="test_scorer"),
            ScorerResult(score=0.8, raw_score=8, metadata={}, scorer_name="test_scorer"),
            ScorerResult(score=0.5, raw_score=5, metadata={}, scorer_name="test_scorer"),
        ]
        return scorer

    @pytest.fixture
    def optimizer(self, mock_llm, mock_scorer):
        opt = PromptOptimizer(
            scorers={"test_scorer": mock_scorer},
            llm_service=mock_llm,
        )
        opt._redis = AsyncMock()
        return opt

    @pytest.mark.asyncio
    async def test_optimize_selects_best_variant(self, optimizer, mock_scorer):
        target = PromptOptTarget(
            agent_name="test",
            current_prompt="base prompt",
            scorer_chain=["test_scorer"],
            mutation_count=3,
            top_k=1,
        )

        async def benchmark_fn(prompt: str) -> str:
            return f"output for: {prompt}"

        session = await optimizer.optimize(target, benchmark_fn, max_rounds=1)

        assert session.status.value == "completed"
        assert session.rounds_completed == 1
        assert session.best_variant is not None
        assert session.best_variant.final_score == 0.8
        assert len(session.all_variants) == 3

    @pytest.mark.asyncio
    async def test_optimize_cancel(self, optimizer):
        target = PromptOptTarget(
            agent_name="test",
            current_prompt="base",
            scorer_chain=["test_scorer"],
            mutation_count=1,
            top_k=1,
        )
        optimizer.cancel()

        async def benchmark_fn(prompt: str) -> str:
            return "output"

        session = await optimizer.optimize(target, benchmark_fn, max_rounds=5)
        assert session.status.value == "cancelled"
        assert session.rounds_completed == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd autobot-backend && python -m pytest services/autoresearch/prompt_optimizer_test.py::TestPromptOptimizerLoop -v`
Expected: FAIL (tests rely on the implementation from Step 3 of Task 5 — if that's already in, verify they pass)

- [ ] **Step 3: Run tests and fix any issues**

Run: `cd autobot-backend && python -m pytest services/autoresearch/prompt_optimizer_test.py -v`
Expected: PASS (4 tests total)

- [ ] **Step 4: Commit**

```bash
git add autobot-backend/services/autoresearch/prompt_optimizer_test.py
git commit -m "test(autoresearch): add optimization loop and cancellation tests (#2600)"
```

---

### Task 7: Knowledge Synthesizer

**Files:**
- Create: `autobot-backend/services/autoresearch/knowledge_synthesizer.py`
- Create: `autobot-backend/services/autoresearch/knowledge_synthesizer_test.py`

- [ ] **Step 1: Write the failing test**

```python
# autobot-backend/services/autoresearch/knowledge_synthesizer_test.py

# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for knowledge synthesizer — Issue #2600."""

from __future__ import annotations

import json

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.autoresearch.knowledge_synthesizer import (
    ExperimentInsight,
    KnowledgeSynthesizer,
)
from services.autoresearch.models import (
    Experiment,
    ExperimentResult,
    ExperimentState,
    HyperParams,
)


class TestExperimentInsight:
    def test_to_dict(self):
        insight = ExperimentInsight(
            statement="Dropout < 0.1 degrades val_bpb",
            confidence=0.85,
            supporting_experiments=["exp1", "exp2"],
            related_hyperparams=["dropout"],
        )
        d = insight.to_dict()
        assert d["statement"] == "Dropout < 0.1 degrades val_bpb"
        assert d["confidence"] == 0.85
        assert len(d["supporting_experiments"]) == 2


class TestKnowledgeSynthesizer:
    @pytest.fixture
    def mock_store(self):
        store = AsyncMock()
        store.list_experiments.return_value = [
            Experiment(
                id="e1",
                hypothesis="Lower dropout to 0.05",
                state=ExperimentState.DISCARDED,
                hyperparams=HyperParams(dropout=0.05),
                result=ExperimentResult(val_bpb=6.0),
                baseline_val_bpb=5.5,
            ),
            Experiment(
                id="e2",
                hypothesis="Increase warmup to 300",
                state=ExperimentState.KEPT,
                hyperparams=HyperParams(warmup_steps=300),
                result=ExperimentResult(val_bpb=5.2),
                baseline_val_bpb=5.5,
            ),
        ]
        return store

    @pytest.fixture
    def mock_llm(self):
        llm = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = json.dumps([
            {
                "statement": "Warmup steps >= 300 improve convergence",
                "confidence": 0.8,
                "supporting_experiments": ["e2"],
                "related_hyperparams": ["warmup_steps"],
            }
        ])
        llm.chat.return_value = mock_response
        return llm

    @pytest.fixture
    def mock_chromadb(self):
        collection = AsyncMock()
        return collection

    @pytest.fixture
    def synthesizer(self, mock_store, mock_llm, mock_chromadb):
        s = KnowledgeSynthesizer(
            store=mock_store,
            llm_service=mock_llm,
        )
        s._insights_collection = mock_chromadb
        return s

    @pytest.mark.asyncio
    async def test_synthesize_session(self, synthesizer, mock_llm, mock_chromadb):
        insights = await synthesizer.synthesize_session("session-1")

        assert len(insights) == 1
        assert insights[0].statement == "Warmup steps >= 300 improve convergence"
        assert insights[0].confidence == 0.8
        mock_llm.chat.assert_called_once()
        mock_chromadb.upsert.assert_called_once()

    @pytest.mark.asyncio
    async def test_query_insights(self, synthesizer, mock_chromadb):
        mock_chromadb.query.return_value = {
            "ids": [["i1"]],
            "documents": [["Warmup steps >= 300 improve convergence"]],
            "metadatas": [[{
                "confidence": 0.8,
                "supporting_experiments": "e2",
                "related_hyperparams": "warmup_steps",
                "session_id": "s1",
            }]],
        }
        results = await synthesizer.query_insights("warmup", limit=5)
        assert len(results) == 1
        assert "Warmup" in results[0].statement
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd autobot-backend && python -m pytest services/autoresearch/knowledge_synthesizer_test.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement KnowledgeSynthesizer**

```python
# autobot-backend/services/autoresearch/knowledge_synthesizer.py

# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Knowledge Synthesizer for AutoResearch

Issue #2600: Two-layer ChromaDB intelligence:
  1. Enhanced per-experiment indexing (richer documents)
  2. Distilled cross-experiment insights (synthesized lessons)

Insights are generated by LLM after each ExperimentSession completes
and stored in a dedicated ChromaDB collection for RAG queries.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .config import AutoResearchConfig
from .store import ExperimentStore

logger = logging.getLogger(__name__)

_SYNTHESIS_SYSTEM_PROMPT = (
    "You are an ML experiment analyst. Analyze the following experiment results "
    "and extract reusable insights about what works and what doesn't.\n\n"
    "For each insight, provide:\n"
    "- statement: A clear, actionable finding\n"
    "- confidence: 0.0-1.0 based on how many experiments support it\n"
    "- supporting_experiments: List of experiment IDs that support this finding\n"
    "- related_hyperparams: List of hyperparameter names involved\n\n"
    "Return a JSON array of insight objects."
)


@dataclass
class ExperimentInsight:
    """A distilled cross-experiment finding."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    statement: str = ""
    confidence: float = 0.0
    supporting_experiments: List[str] = field(default_factory=list)
    related_hyperparams: List[str] = field(default_factory=list)
    synthesized_at: float = field(default_factory=time.time)
    session_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "statement": self.statement,
            "confidence": self.confidence,
            "supporting_experiments": self.supporting_experiments,
            "related_hyperparams": self.related_hyperparams,
            "synthesized_at": self.synthesized_at,
            "session_id": self.session_id,
        }


class KnowledgeSynthesizer:
    """Synthesize cross-experiment insights and store in ChromaDB."""

    INSIGHTS_COLLECTION = "autoresearch_insights"

    def __init__(
        self,
        store: ExperimentStore,
        llm_service: Any,
        config: Optional[AutoResearchConfig] = None,
    ) -> None:
        self._store = store
        self._llm = llm_service
        self._config = config or AutoResearchConfig()
        self._insights_collection = None

    async def _get_insights_collection(self):
        if self._insights_collection is None:
            from utils.chromadb_client import get_async_chromadb_client

            client = await get_async_chromadb_client()
            self._insights_collection = await client.get_or_create_collection(
                name=self.INSIGHTS_COLLECTION,
                metadata={"description": "Distilled AutoResearch experiment insights"},
            )
        return self._insights_collection

    async def synthesize_session(self, session_id: str) -> List[ExperimentInsight]:
        """Synthesize insights from all experiments in a session.

        Args:
            session_id: The experiment session to analyze.

        Returns:
            List of generated ExperimentInsight objects.
        """
        experiments = await self._store.list_experiments(limit=100)
        session_experiments = [
            e for e in experiments if f"session:{session_id}" in e.tags
        ]

        if not session_experiments:
            logger.info("No experiments found for session %s", session_id)
            return []

        experiment_summary = self._build_experiment_summary(session_experiments)

        try:
            response = await self._llm.chat(
                messages=[
                    {"role": "system", "content": _SYNTHESIS_SYSTEM_PROMPT},
                    {"role": "user", "content": experiment_summary},
                ],
                temperature=0.3,
                max_tokens=2000,
            )
            raw_insights = json.loads(response.content)
        except (json.JSONDecodeError, Exception) as exc:
            logger.warning("KnowledgeSynthesizer: LLM synthesis failed: %s", exc)
            return []

        insights = []
        for raw in raw_insights:
            insight = ExperimentInsight(
                statement=raw.get("statement", ""),
                confidence=max(0.0, min(1.0, float(raw.get("confidence", 0.0)))),
                supporting_experiments=raw.get("supporting_experiments", []),
                related_hyperparams=raw.get("related_hyperparams", []),
                session_id=session_id,
            )
            insights.append(insight)

        await self._index_insights(insights)
        return insights

    async def query_insights(
        self, query: str, limit: int = 5
    ) -> List[ExperimentInsight]:
        """Semantic search over distilled insights.

        Args:
            query: Free-text search query.
            limit: Maximum results to return.

        Returns:
            List of matching ExperimentInsight objects.
        """
        collection = await self._get_insights_collection()
        results = await collection.query(
            query_texts=[query],
            n_results=limit,
        )

        insights = []
        if results and results.get("ids") and results["ids"][0]:
            for i, doc_id in enumerate(results["ids"][0]):
                meta = results["metadatas"][0][i] if results.get("metadatas") else {}
                document = (
                    results["documents"][0][i] if results.get("documents") else ""
                )
                insight = ExperimentInsight(
                    id=doc_id,
                    statement=document,
                    confidence=float(meta.get("confidence", 0.0)),
                    supporting_experiments=meta.get(
                        "supporting_experiments", ""
                    ).split(","),
                    related_hyperparams=meta.get("related_hyperparams", "").split(","),
                    session_id=meta.get("session_id"),
                )
                insights.append(insight)

        return insights

    async def get_relevant_context(self, topic: str, limit: int = 3) -> str:
        """Build RAG context string for hypothesis generation.

        Args:
            topic: Research topic to find relevant insights for.
            limit: Number of insights to include.

        Returns:
            Formatted context string, empty if no insights found.
        """
        insights = await self.query_insights(topic, limit=limit)
        if not insights:
            return ""

        lines = ["Prior experiment insights:"]
        for insight in insights:
            lines.append(
                f"- {insight.statement} (confidence: {insight.confidence:.0%})"
            )
        return "\n".join(lines)

    def _build_experiment_summary(self, experiments: list) -> str:
        """Build a text summary of experiments for LLM synthesis."""
        parts = []
        for exp in experiments:
            hp_dict = exp.hyperparams.to_dict()
            summary = (
                f"Experiment {exp.id}:\n"
                f"  Hypothesis: {exp.hypothesis}\n"
                f"  State: {exp.state.value}\n"
                f"  Hyperparams: {json.dumps(hp_dict)}\n"
            )
            if exp.result and exp.result.val_bpb is not None:
                summary += f"  val_bpb: {exp.result.val_bpb}\n"
                if exp.baseline_val_bpb is not None:
                    improvement = exp.baseline_val_bpb - exp.result.val_bpb
                    summary += (
                        f"  Baseline: {exp.baseline_val_bpb}, "
                        f"Improvement: {improvement:.4f}\n"
                    )
            parts.append(summary)
        return "\n".join(parts)

    async def _index_insights(self, insights: List[ExperimentInsight]) -> None:
        """Store insights in ChromaDB."""
        if not insights:
            return

        collection = await self._get_insights_collection()
        ids = [i.id for i in insights]
        documents = [i.statement for i in insights]
        metadatas = [
            {
                "confidence": i.confidence,
                "supporting_experiments": ",".join(i.supporting_experiments),
                "related_hyperparams": ",".join(i.related_hyperparams),
                "session_id": i.session_id or "",
                "synthesized_at": i.synthesized_at,
            }
            for i in insights
        ]

        try:
            await collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
            logger.info("Indexed %d insights in ChromaDB", len(insights))
        except Exception:
            logger.exception("Failed to index insights in ChromaDB")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd autobot-backend && python -m pytest services/autoresearch/knowledge_synthesizer_test.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add autobot-backend/services/autoresearch/knowledge_synthesizer.py autobot-backend/services/autoresearch/knowledge_synthesizer_test.py
git commit -m "feat(autoresearch): add KnowledgeSynthesizer for distilled experiment insights (#2600)"
```

---

### Task 8: Enrich ExperimentStore Indexing

**Files:**
- Modify: `autobot-backend/services/autoresearch/store.py:131-163`

- [ ] **Step 1: Write the failing test**

```python
# Append to autobot-backend/services/autoresearch/store_chromadb_test.py
# (or create test in the existing file)

class TestEnrichedIndexing:
    def test_build_document_includes_hyperparams(self):
        from services.autoresearch.store import ExperimentStore
        from services.autoresearch.models import (
            Experiment,
            ExperimentResult,
            ExperimentState,
            HyperParams,
        )

        store = ExperimentStore()
        exp = Experiment(
            hypothesis="Test hypothesis",
            description="Test description",
            hyperparams=HyperParams(learning_rate=1e-4, dropout=0.1),
            result=ExperimentResult(val_bpb=4.5),
            baseline_val_bpb=5.0,
            state=ExperimentState.KEPT,
            tags=["session:s1", "attention"],
        )

        doc = store._build_document(exp)
        assert "learning_rate" in doc
        assert "1e-4" in doc or "0.0001" in doc
        assert "dropout" in doc
        assert "Baseline: 5.0" in doc
        assert "Improvement: 0.5" in doc

    def test_build_metadata_includes_hyperparams(self):
        from services.autoresearch.store import ExperimentStore
        from services.autoresearch.models import (
            Experiment,
            ExperimentResult,
            ExperimentState,
            HyperParams,
        )

        store = ExperimentStore()
        exp = Experiment(
            hypothesis="Test",
            hyperparams=HyperParams(learning_rate=1e-4),
            result=ExperimentResult(val_bpb=4.5),
            state=ExperimentState.KEPT,
            tags=["session:s1"],
        )

        meta = store._build_metadata(exp)
        assert "learning_rate" in meta
        assert meta["learning_rate"] == 1e-4
        assert "session_id" in meta
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd autobot-backend && python -m pytest services/autoresearch/store_chromadb_test.py::TestEnrichedIndexing -v`
Expected: FAIL — `"learning_rate" not in doc` (current implementation doesn't include hyperparams)

- [ ] **Step 3: Update `_build_document` and `_build_metadata` in store.py**

Replace `_build_document` (lines 131-149) with:

```python
    def _build_document(self, experiment: Experiment) -> str:
        """Build a searchable text document from experiment data."""
        parts = [
            f"Hypothesis: {experiment.hypothesis}",
            f"Description: {experiment.description}",
        ]
        # Include hyperparams for richer search
        hp_dict = experiment.hyperparams.to_dict()
        parts.append(f"Hyperparams: {', '.join(f'{k}={v}' for k, v in hp_dict.items())}")

        if experiment.result:
            parts.append(f"val_bpb: {experiment.result.val_bpb}")
            if experiment.baseline_val_bpb is not None:
                improvement = experiment.baseline_val_bpb - (experiment.result.val_bpb or 0)
                pct = (
                    (improvement / experiment.baseline_val_bpb * 100)
                    if experiment.baseline_val_bpb
                    else 0
                )
                parts.append(
                    f"Baseline: {experiment.baseline_val_bpb}, "
                    f"Improvement: {improvement:.4f} ({pct:.2f}%)"
                )
        if experiment.code_diff:
            parts.append(f"Code change:\n{experiment.code_diff[:500]}")
        # Session context from tags
        session_tags = [t for t in experiment.tags if t.startswith("session:")]
        if session_tags:
            parts.append(f"Session: {session_tags[0].split(':', 1)[1]}")
        return "\n".join(parts)
```

Replace `_build_metadata` (lines 151-163) with:

```python
    def _build_metadata(self, experiment: Experiment) -> Dict[str, Any]:
        """Build ChromaDB metadata for filtering."""
        meta: Dict[str, Any] = {
            "state": experiment.state.value,
            "created_at": experiment.created_at,
        }
        if experiment.result and experiment.result.val_bpb is not None:
            meta["val_bpb"] = experiment.result.val_bpb
        if experiment.improvement is not None:
            meta["improvement"] = experiment.improvement
        if experiment.tags:
            meta["tags"] = ",".join(experiment.tags)
        # Include key hyperparams for filtering
        hp_dict = experiment.hyperparams.to_dict()
        for key in ("learning_rate", "dropout", "batch_size", "n_layer", "n_head"):
            if key in hp_dict:
                meta[key] = hp_dict[key]
        # Extract session ID from tags
        for tag in experiment.tags:
            if tag.startswith("session:"):
                meta["session_id"] = tag.split(":", 1)[1]
                break
        return meta
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd autobot-backend && python -m pytest services/autoresearch/store_chromadb_test.py::TestEnrichedIndexing -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Run all existing store tests to ensure no regressions**

Run: `cd autobot-backend && python -m pytest services/autoresearch/store_chromadb_test.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add autobot-backend/services/autoresearch/store.py autobot-backend/services/autoresearch/store_chromadb_test.py
git commit -m "feat(autoresearch): enrich ChromaDB experiment indexing with hyperparams and session context (#2600)"
```

---

### Task 9: API Endpoints — Prompt Optimizer + Approvals + Insights

**Files:**
- Modify: `autobot-backend/services/autoresearch/routes.py`

- [ ] **Step 1: Write the failing test for new endpoints**

```python
# Append to autobot-backend/services/autoresearch/routes_test.py

class TestPromptOptimizerEndpoints:
    @pytest.mark.asyncio
    async def test_get_optimizer_status_no_session(self, client):
        response = await client.get("/autoresearch/prompt-optimizer/status")
        assert response.status_code == 200
        data = response.json()
        assert data["running"] is False

    @pytest.mark.asyncio
    async def test_cancel_when_not_running(self, client):
        response = await client.post("/autoresearch/prompt-optimizer/cancel")
        assert response.status_code == 409


class TestApprovalEndpoints:
    @pytest.mark.asyncio
    async def test_pending_approvals_empty(self, client):
        response = await client.get("/autoresearch/approvals/pending")
        assert response.status_code == 200
        assert response.json()["approvals"] == []


class TestInsightsEndpoints:
    @pytest.mark.asyncio
    async def test_list_insights_empty(self, client):
        response = await client.get("/autoresearch/insights")
        assert response.status_code == 200
        assert response.json()["insights"] == []
```

Note: Adapt the `client` fixture to match the existing test pattern in `routes_test.py` — use `httpx.AsyncClient` with the FastAPI test app.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd autobot-backend && python -m pytest services/autoresearch/routes_test.py -v -k "Optimizer or Approval or Insights"`
Expected: FAIL — 404 for new routes

- [ ] **Step 3: Add new endpoints to routes.py**

Append to `autobot-backend/services/autoresearch/routes.py`:

```python
# --- Imports to add at top ---
from .knowledge_synthesizer import KnowledgeSynthesizer
from .prompt_optimizer import PromptOptimizer, PromptOptTarget


# --- New request models ---

class StartOptimizationRequest(BaseModel):
    agent_name: str = Field(..., max_length=100)
    max_rounds: int = Field(default=3, ge=1, le=10)


class SubmitScoreRequest(BaseModel):
    score: int = Field(..., ge=0, le=10)
    comment: str = Field(default="", max_length=1000)


class ApprovalDecisionRequest(BaseModel):
    decision: str = Field(..., pattern="^(approved|rejected)$")


class SynthesizeRequest(BaseModel):
    session_id: str = Field(..., max_length=100)


# --- Lazy singletons ---

_optimizer: Optional[PromptOptimizer] = None
_synthesizer: Optional[KnowledgeSynthesizer] = None


def _get_optimizer(request: Request) -> PromptOptimizer:
    global _optimizer
    app_opt = getattr(request.app.state, "autoresearch_optimizer", None)
    if app_opt is not None:
        return app_opt
    if _optimizer is None:
        from services.llm_service import get_llm_service

        _optimizer = PromptOptimizer(
            scorers={},  # scorers registered at runtime
            llm_service=get_llm_service(),
        )
    request.app.state.autoresearch_optimizer = _optimizer
    return _optimizer


def _get_synthesizer(request: Request) -> KnowledgeSynthesizer:
    global _synthesizer
    app_synth = getattr(request.app.state, "autoresearch_synthesizer", None)
    if app_synth is not None:
        return app_synth
    if _synthesizer is None:
        from services.llm_service import get_llm_service

        store = _get_store(request)
        _synthesizer = KnowledgeSynthesizer(
            store=store,
            llm_service=get_llm_service(),
        )
    request.app.state.autoresearch_synthesizer = _synthesizer
    return _synthesizer


# --- Prompt Optimizer Endpoints ---


@router.get("/prompt-optimizer/status")
async def get_optimizer_status(
    request: Request,
    _admin: bool = Depends(check_admin_permission),
):
    """Get current prompt optimization session status."""
    optimizer = _get_optimizer(request)
    session = optimizer.current_session
    if session is None:
        return {"running": False, "session": None}
    return {"running": True, "session": session.to_dict()}


@router.post("/prompt-optimizer/start")
async def start_optimization(
    request: Request,
    body: StartOptimizationRequest,
    background_tasks: BackgroundTasks,
    _admin: bool = Depends(check_admin_permission),
):
    """Start prompt optimization for a registered target."""
    optimizer = _get_optimizer(request)
    if optimizer.current_session is not None:
        raise HTTPException(status_code=409, detail="Optimization already running")

    # For now, only autoresearch_hypothesis is a valid target
    if body.agent_name != "autoresearch_hypothesis":
        raise HTTPException(
            status_code=400,
            detail=f"Unknown agent target: {body.agent_name}",
        )

    target = PromptOptTarget(
        agent_name=body.agent_name,
        current_prompt="",  # loaded from agent at runtime
        scorer_chain=["val_bpb"],
    )

    async def _benchmark(prompt: str) -> str:
        return prompt  # placeholder — real benchmark set up by agent

    background_tasks.add_task(optimizer.optimize, target, _benchmark, body.max_rounds)
    return {"status": "started", "agent_name": body.agent_name}


@router.post("/prompt-optimizer/cancel")
async def cancel_optimization(
    request: Request,
    _admin: bool = Depends(check_admin_permission),
):
    """Cancel running optimization."""
    optimizer = _get_optimizer(request)
    if optimizer.current_session is None:
        raise HTTPException(status_code=409, detail="No optimization running")
    optimizer.cancel()
    return {"status": "cancelling"}


@router.get("/prompt-optimizer/variants/{session_id}")
async def get_variants(
    request: Request,
    session_id: str,
    _admin: bool = Depends(check_admin_permission),
):
    """List prompt variants for an optimization session."""
    from autobot_shared.redis_client import get_redis_client
    import json as _json

    redis = get_redis_client(async_client=True, database="main")
    key = f"autoresearch:prompt_opt:session:{session_id}"
    raw = await redis.get(key)
    if raw is None:
        raise HTTPException(status_code=404, detail="Session not found")
    data = _json.loads(raw)
    return {"variants": data.get("all_variants", [])}


@router.post("/prompt-optimizer/variants/{variant_id}/score")
async def submit_variant_score(
    request: Request,
    variant_id: str,
    body: SubmitScoreRequest,
    _admin: bool = Depends(check_admin_permission),
):
    """Submit a human score for a prompt variant."""
    from autobot_shared.redis_client import get_redis_client
    import json as _json

    redis = get_redis_client(async_client=True, database="main")
    # HumanReviewScorer polls this key
    # We need session_id — accept it as query param
    session_id = request.query_params.get("session_id", "unknown")
    key = f"autoresearch:prompt_review:{session_id}:{variant_id}"
    await redis.set(
        key,
        _json.dumps({"score": body.score, "comment": body.comment}),
        ex=86400,
    )
    return {"status": "scored", "variant_id": variant_id, "score": body.score}


# --- Approval Endpoints ---


@router.get("/approvals/pending")
async def list_pending_approvals(
    request: Request,
    _admin: bool = Depends(check_admin_permission),
):
    """List pending approval requests."""
    from autobot_shared.redis_client import get_redis_client
    import json as _json

    redis = get_redis_client(async_client=True, database="main")
    # Scan for pending approval keys
    approvals = []
    async for key in redis.scan_iter("autoresearch:approval:pending:*"):
        raw = await redis.get(key)
        if raw:
            data = _json.loads(raw if isinstance(raw, str) else raw.decode("utf-8"))
            # Check if still pending
            key_str = key if isinstance(key, str) else key.decode("utf-8")
            parts = key_str.split(":")
            if len(parts) >= 5:
                status_key = f"autoresearch:approval:status:{parts[3]}:{parts[4]}"
                status = await redis.get(status_key)
                status_str = (
                    status.decode("utf-8") if isinstance(status, bytes) else status
                ) if status else "unknown"
                if status_str == "pending":
                    data["status"] = "pending"
                    approvals.append(data)
    return {"approvals": approvals}


@router.post("/approvals/{session_id}/{experiment_id}")
async def submit_approval_decision(
    request: Request,
    session_id: str,
    experiment_id: str,
    body: ApprovalDecisionRequest,
    _admin: bool = Depends(check_admin_permission),
):
    """Submit approve/reject decision for an experiment."""
    from autobot_shared.redis_client import get_redis_client

    redis = get_redis_client(async_client=True, database="main")
    status_key = f"autoresearch:approval:status:{session_id}:{experiment_id}"
    current = await redis.get(status_key)
    if current is None:
        raise HTTPException(status_code=404, detail="Approval request not found")
    await redis.set(status_key, body.decision, ex=86400)
    return {
        "session_id": session_id,
        "experiment_id": experiment_id,
        "decision": body.decision,
    }


# --- Knowledge Insights Endpoints ---


@router.get("/insights")
async def list_insights(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    min_confidence: float = Query(default=0.0, ge=0.0, le=1.0),
    _admin: bool = Depends(check_admin_permission),
):
    """List distilled experiment insights."""
    synthesizer = _get_synthesizer(request)
    insights = await synthesizer.query_insights("*", limit=limit)
    filtered = [i for i in insights if i.confidence >= min_confidence]
    return {"insights": [i.to_dict() for i in filtered], "count": len(filtered)}


@router.get("/insights/search")
async def search_insights(
    request: Request,
    q: str = Query(..., min_length=1, max_length=500),
    limit: int = Query(default=5, ge=1, le=50),
    _admin: bool = Depends(check_admin_permission),
):
    """Semantic search over experiment insights."""
    synthesizer = _get_synthesizer(request)
    insights = await synthesizer.query_insights(q, limit=limit)
    return {"insights": [i.to_dict() for i in insights], "query": q}


@router.post("/insights/synthesize")
async def trigger_synthesis(
    request: Request,
    body: SynthesizeRequest,
    _admin: bool = Depends(check_admin_permission),
):
    """Manually trigger insight synthesis for a session."""
    synthesizer = _get_synthesizer(request)
    insights = await synthesizer.synthesize_session(body.session_id)
    return {
        "session_id": body.session_id,
        "insights_generated": len(insights),
        "insights": [i.to_dict() for i in insights],
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd autobot-backend && python -m pytest services/autoresearch/routes_test.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add autobot-backend/services/autoresearch/routes.py autobot-backend/services/autoresearch/routes_test.py
git commit -m "feat(autoresearch): add API endpoints for prompt optimizer, approvals, and insights (#2600)"
```

---

### Task 9b: Notification Integration on Approval Request

**Files:**
- Modify: `autobot-backend/services/autoresearch/auto_research_agent.py:777-824`

- [ ] **Step 1: Add notification dispatch to `_handle_approval_gate`**

At the end of the `_handle_approval_gate` method (after `request_approval` is called, before `wait_for_approval`), add a notification dispatch:

```python
        # Dispatch notification for approval_needed event
        try:
            from services.notification_service import (
                NotificationEvent,
                NotificationService,
            )

            notification_service = NotificationService()
            await notification_service.send(
                event=NotificationEvent.APPROVAL_NEEDED,
                workflow_id=f"autoresearch:{session.id}",
                payload={
                    "experiment_id": experiment.id,
                    "topic": session.topic,
                    "improvement_pct": metrics.improvement_pct,
                    "val_bpb": metrics.result_val_bpb,
                    "baseline_val_bpb": metrics.baseline_val_bpb,
                },
                config=self._get_notification_config(),
            )
        except Exception:
            logger.warning(
                "Failed to send approval notification for experiment %s",
                experiment.id,
            )
```

Also add a helper method to `AutoResearchAgent`:

```python
    def _get_notification_config(self):
        """Return a default notification config for autoresearch events."""
        from services.notification_service import NotificationConfig

        return NotificationConfig(
            channels={"approval_needed": ["in_app"]},
        )
```

- [ ] **Step 2: Run existing auto_research_agent tests to verify no regressions**

Run: `cd autobot-backend && python -m pytest services/autoresearch/auto_research_agent_test.py -v`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add autobot-backend/services/autoresearch/auto_research_agent.py
git commit -m "feat(autoresearch): dispatch notification on approval request (#2600)"
```

---

### Task 10: Update `__init__.py` Exports

**Files:**
- Modify: `autobot-backend/services/autoresearch/__init__.py`

- [ ] **Step 1: Add new exports**

Add to the imports section:

```python
from .knowledge_synthesizer import ExperimentInsight, KnowledgeSynthesizer
from .prompt_optimizer import (
    BenchmarkFn,
    OptimizationSession,
    OptimizationStatus,
    PromptOptimizer,
    PromptOptTarget,
    PromptVariant,
)
from .scorers import (
    HumanReviewScorer,
    LLMJudgeScorer,
    PromptScorer,
    ScorerResult,
    ValBpbScorer,
)
```

Add to `__all__`:

```python
    # M3: Self-improvement (Issue #2600)
    "PromptOptimizer",
    "PromptOptTarget",
    "PromptVariant",
    "OptimizationSession",
    "OptimizationStatus",
    "BenchmarkFn",
    "PromptScorer",
    "ScorerResult",
    "ValBpbScorer",
    "LLMJudgeScorer",
    "HumanReviewScorer",
    "KnowledgeSynthesizer",
    "ExperimentInsight",
```

- [ ] **Step 2: Verify imports work**

Run: `cd autobot-backend && python -c "from services.autoresearch import PromptOptimizer, KnowledgeSynthesizer, ValBpbScorer, LLMJudgeScorer, HumanReviewScorer; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Run all autoresearch tests**

Run: `cd autobot-backend && python -m pytest services/autoresearch/ -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add autobot-backend/services/autoresearch/__init__.py
git commit -m "feat(autoresearch): export M3 components from package init (#2600)"
```

---

### Task 11: Integration Test — Full M3 Loop

**Files:**
- Create: `autobot-backend/tests/test_autoresearch_m3.py`

- [ ] **Step 1: Write the integration test**

```python
# autobot-backend/tests/test_autoresearch_m3.py

# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Integration test for AutoResearch M3 — Issue #2600."""

from __future__ import annotations

import json

import pytest
from unittest.mock import AsyncMock, MagicMock

from services.autoresearch.knowledge_synthesizer import KnowledgeSynthesizer
from services.autoresearch.models import Experiment, ExperimentResult, ExperimentState, HyperParams
from services.autoresearch.prompt_optimizer import PromptOptimizer, PromptOptTarget
from services.autoresearch.scorers import LLMJudgeScorer, ScorerResult


class TestM3Integration:
    """Test the full M3 pipeline: optimize → synthesize → query insights."""

    @pytest.fixture
    def mock_llm(self):
        llm = AsyncMock()
        # For mutation: return variants
        mutation_response = MagicMock()
        mutation_response.content = json.dumps(["variant A", "variant B"])

        # For judge: return rating
        judge_response = MagicMock()
        judge_response.content = '{"rating": 7, "reasoning": "Good"}'

        # For synthesis: return insights
        synthesis_response = MagicMock()
        synthesis_response.content = json.dumps([
            {
                "statement": "Higher warmup improves convergence",
                "confidence": 0.9,
                "supporting_experiments": ["e1"],
                "related_hyperparams": ["warmup_steps"],
            }
        ])

        # Cycle through responses
        llm.chat.side_effect = [
            mutation_response,  # optimizer mutation
            judge_response,     # scorer: variant A
            judge_response,     # scorer: variant B
            synthesis_response, # knowledge synthesis
        ]
        return llm

    @pytest.mark.asyncio
    async def test_optimize_then_synthesize(self, mock_llm):
        # Setup scorer
        scorer = LLMJudgeScorer(
            llm_service=mock_llm,
            criteria=["relevance"],
        )

        # Setup optimizer
        optimizer = PromptOptimizer(
            scorers={"llm_judge": scorer},
            llm_service=mock_llm,
        )
        optimizer._redis = AsyncMock()

        target = PromptOptTarget(
            agent_name="test_agent",
            current_prompt="base prompt",
            scorer_chain=["llm_judge"],
            mutation_count=2,
            top_k=1,
        )

        async def benchmark(prompt: str) -> str:
            return f"Output from: {prompt}"

        # Run optimization
        session = await optimizer.optimize(target, benchmark, max_rounds=1)
        assert session.status.value == "completed"
        assert session.best_variant is not None

        # Setup synthesizer with mock store
        mock_store = AsyncMock()
        mock_store.list_experiments.return_value = [
            Experiment(
                id="e1",
                hypothesis="test",
                state=ExperimentState.KEPT,
                hyperparams=HyperParams(warmup_steps=300),
                result=ExperimentResult(val_bpb=4.5),
                tags=["session:test-session"],
            ),
        ]

        synthesizer = KnowledgeSynthesizer(
            store=mock_store,
            llm_service=mock_llm,
        )
        mock_collection = AsyncMock()
        synthesizer._insights_collection = mock_collection

        # Run synthesis
        insights = await synthesizer.synthesize_session("test-session")
        assert len(insights) == 1
        assert insights[0].statement == "Higher warmup improves convergence"
        mock_collection.upsert.assert_called_once()
```

- [ ] **Step 2: Run the integration test**

Run: `cd autobot-backend && python -m pytest tests/test_autoresearch_m3.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add autobot-backend/tests/test_autoresearch_m3.py
git commit -m "test(autoresearch): add M3 integration test for optimize-synthesize pipeline (#2600)"
```

---

## Phase 2: Frontend

### Task 12: `useAutoResearch.ts` Composable

**Files:**
- Create: `autobot-frontend/src/composables/useAutoResearch.ts`

- [ ] **Step 1: Create the composable**

```typescript
// autobot-frontend/src/composables/useAutoResearch.ts

// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { ref, type Ref } from 'vue'
import { useApi } from './useApi'

// --- Types ---

export interface ExperimentResult {
  val_bpb: number | null
  train_loss: number | null
  val_loss: number | null
  steps_completed: number
  tokens_per_second: number | null
  wall_time_seconds: number
  error_message: string | null
}

export interface Experiment {
  id: string
  hypothesis: string
  description: string
  state: string
  hyperparams: Record<string, unknown>
  result: ExperimentResult | null
  baseline_val_bpb: number | null
  tags: string[]
  created_at: number
  started_at: number | null
  completed_at: number | null
}

export interface ExperimentStats {
  total_experiments: number
  completed: number
  failed: number
  kept: number
  discarded: number
  best_val_bpb: number | null
  baseline_val_bpb: number | null
  avg_wall_time: number
  total_wall_time: number
  improvement_trend: number[]
}

export interface PromptVariant {
  id: string
  prompt_text: string
  output: string
  scores: Record<string, number>
  final_score: number
  round_number: number
  created_at: number
}

export interface OptimizationSession {
  id: string
  status: string
  rounds_completed: number
  max_rounds: number
  best_variant: PromptVariant | null
  baseline_score: number
  all_variants: PromptVariant[]
}

export interface ApprovalRequest {
  session_id: string
  experiment_id: string
  details: Record<string, unknown>
  requested_at: number
  status: string
}

export interface ExperimentInsight {
  id: string
  statement: string
  confidence: number
  supporting_experiments: string[]
  related_hyperparams: string[]
  synthesized_at: number
  session_id: string | null
}

// --- Composable ---

export function useAutoResearch() {
  const api = useApi()

  const experiments: Ref<Experiment[]> = ref([])
  const stats: Ref<ExperimentStats | null> = ref(null)
  const loading = ref(false)
  const error: Ref<string | null> = ref(null)

  const optimizerStatus: Ref<OptimizationSession | null> = ref(null)
  const variants: Ref<PromptVariant[]> = ref([])

  const pendingApprovals: Ref<ApprovalRequest[]> = ref([])

  const insights: Ref<ExperimentInsight[]> = ref([])

  let pollTimer: ReturnType<typeof setInterval> | null = null

  // --- Experiments ---

  async function fetchExperiments(params?: {
    limit?: number
    offset?: number
    state?: string
  }): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const query = new URLSearchParams()
      if (params?.limit) query.set('limit', String(params.limit))
      if (params?.offset) query.set('offset', String(params.offset))
      if (params?.state) query.set('state', params.state)
      const response = await api.get(`/api/autoresearch/experiments?${query}`)
      experiments.value = response.experiments ?? []
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err)
    } finally {
      loading.value = false
    }
  }

  async function fetchStats(): Promise<void> {
    try {
      const response = await api.get('/api/autoresearch/experiments/stats')
      stats.value = response
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err)
    }
  }

  // --- Prompt Optimizer ---

  async function fetchOptimizerStatus(): Promise<void> {
    try {
      const response = await api.get('/api/autoresearch/prompt-optimizer/status')
      optimizerStatus.value = response.session ?? null
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err)
    }
  }

  async function startOptimization(
    agentName: string,
    maxRounds: number = 3,
  ): Promise<void> {
    await api.post('/api/autoresearch/prompt-optimizer/start', {
      agent_name: agentName,
      max_rounds: maxRounds,
    })
    await fetchOptimizerStatus()
  }

  async function cancelOptimization(): Promise<void> {
    await api.post('/api/autoresearch/prompt-optimizer/cancel')
    await fetchOptimizerStatus()
  }

  async function fetchVariants(sessionId: string): Promise<void> {
    const response = await api.get(
      `/api/autoresearch/prompt-optimizer/variants/${sessionId}`,
    )
    variants.value = response.variants ?? []
  }

  async function scoreVariant(
    variantId: string,
    sessionId: string,
    score: number,
    comment: string = '',
  ): Promise<void> {
    await api.post(
      `/api/autoresearch/prompt-optimizer/variants/${variantId}/score?session_id=${sessionId}`,
      { score, comment },
    )
  }

  // --- Approvals ---

  async function fetchPendingApprovals(): Promise<void> {
    const response = await api.get('/api/autoresearch/approvals/pending')
    pendingApprovals.value = response.approvals ?? []
  }

  async function approveExperiment(
    sessionId: string,
    experimentId: string,
  ): Promise<void> {
    await api.post(
      `/api/autoresearch/approvals/${sessionId}/${experimentId}`,
      { decision: 'approved' },
    )
    await fetchPendingApprovals()
  }

  async function rejectExperiment(
    sessionId: string,
    experimentId: string,
  ): Promise<void> {
    await api.post(
      `/api/autoresearch/approvals/${sessionId}/${experimentId}`,
      { decision: 'rejected' },
    )
    await fetchPendingApprovals()
  }

  // --- Insights ---

  async function fetchInsights(minConfidence: number = 0): Promise<void> {
    const response = await api.get(
      `/api/autoresearch/insights?min_confidence=${minConfidence}`,
    )
    insights.value = response.insights ?? []
  }

  async function searchInsights(query: string): Promise<void> {
    const response = await api.get(
      `/api/autoresearch/insights/search?q=${encodeURIComponent(query)}`,
    )
    insights.value = response.insights ?? []
  }

  // --- Polling ---

  function startPolling(intervalMs: number = 10000): void {
    stopPolling()
    pollTimer = setInterval(async () => {
      await Promise.all([
        fetchExperiments(),
        fetchStats(),
        fetchOptimizerStatus(),
        fetchPendingApprovals(),
      ])
    }, intervalMs)
  }

  function stopPolling(): void {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  return {
    experiments,
    stats,
    loading,
    error,
    fetchExperiments,
    fetchStats,
    optimizerStatus,
    startOptimization,
    cancelOptimization,
    variants,
    fetchVariants,
    scoreVariant,
    pendingApprovals,
    fetchPendingApprovals,
    approveExperiment,
    rejectExperiment,
    insights,
    fetchInsights,
    searchInsights,
    startPolling,
    stopPolling,
  }
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd autobot-frontend && npx vue-tsc --noEmit --pretty 2>&1 | grep -i "useAutoResearch" | head -5`
Expected: No errors related to useAutoResearch.ts (some project-wide errors may exist)

- [ ] **Step 3: Commit**

```bash
git add autobot-frontend/src/composables/useAutoResearch.ts
git commit -m "feat(frontend): add useAutoResearch composable for experiment dashboard (#2600)"
```

---

### Task 13: Pinia Store

**Files:**
- Create: `autobot-frontend/src/stores/useAutoResearchStore.ts`

- [ ] **Step 1: Create the store**

```typescript
// autobot-frontend/src/stores/useAutoResearchStore.ts

// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { defineStore } from 'pinia'
import { ref } from 'vue'
import type {
  Experiment,
  ExperimentStats,
  OptimizationSession,
  ApprovalRequest,
  ExperimentInsight,
} from '@/composables/useAutoResearch'

export const useAutoResearchStore = defineStore('autoResearch', () => {
  const experiments = ref<Experiment[]>([])
  const stats = ref<ExperimentStats | null>(null)
  const optimizerSession = ref<OptimizationSession | null>(null)
  const pendingApprovals = ref<ApprovalRequest[]>([])
  const insights = ref<ExperimentInsight[]>([])
  const isPolling = ref(false)
  const lastFetchedAt = ref<number | null>(null)

  function setExperiments(data: Experiment[]) {
    experiments.value = data
    lastFetchedAt.value = Date.now()
  }

  function setStats(data: ExperimentStats) {
    stats.value = data
  }

  function setOptimizerSession(session: OptimizationSession | null) {
    optimizerSession.value = session
  }

  function setPendingApprovals(approvals: ApprovalRequest[]) {
    pendingApprovals.value = approvals
  }

  function setInsights(data: ExperimentInsight[]) {
    insights.value = data
  }

  function setPolling(polling: boolean) {
    isPolling.value = polling
  }

  return {
    experiments,
    stats,
    optimizerSession,
    pendingApprovals,
    insights,
    isPolling,
    lastFetchedAt,
    setExperiments,
    setStats,
    setOptimizerSession,
    setPendingApprovals,
    setInsights,
    setPolling,
  }
})
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd autobot-frontend && npx vue-tsc --noEmit --pretty 2>&1 | grep -i "autoResearchStore" | head -5`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add autobot-frontend/src/stores/useAutoResearchStore.ts
git commit -m "feat(frontend): add Pinia store for AutoResearch experiment state (#2600)"
```

---

### Task 14: ApprovalCard Component

**Files:**
- Create: `autobot-frontend/src/components/autoresearch/ApprovalCard.vue`

- [ ] **Step 1: Create the component**

```vue
<!-- autobot-frontend/src/components/autoresearch/ApprovalCard.vue -->

<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->

<script setup lang="ts">
import { ref } from 'vue'

interface ApprovalDetails {
  sessionId: string
  experimentId: string
  topic?: string
  iteration?: number
  metrics?: {
    baseline_val_bpb?: number
    result_val_bpb?: number
    improvement?: number
    improvement_pct?: number
  }
}

const props = defineProps<{
  approval: ApprovalDetails
}>()

const emit = defineEmits<{
  approve: [sessionId: string, experimentId: string]
  reject: [sessionId: string, experimentId: string]
}>()

const deciding = ref(false)

async function handleApprove() {
  deciding.value = true
  emit('approve', props.approval.sessionId, props.approval.experimentId)
}

async function handleReject() {
  deciding.value = true
  emit('reject', props.approval.sessionId, props.approval.experimentId)
}
</script>

<template>
  <div class="rounded-lg border border-amber-200 bg-amber-50 p-4 dark:border-amber-800 dark:bg-amber-950">
    <div class="mb-2 flex items-center gap-2">
      <span class="inline-block h-2 w-2 rounded-full bg-amber-500"></span>
      <span class="text-sm font-medium text-amber-800 dark:text-amber-200">
        Approval Required
      </span>
    </div>

    <div v-if="approval.metrics" class="mb-3 grid grid-cols-2 gap-2 text-sm">
      <div>
        <span class="text-neutral-500">Baseline val_bpb:</span>
        <span class="ml-1 font-mono">{{ approval.metrics.baseline_val_bpb?.toFixed(4) ?? '—' }}</span>
      </div>
      <div>
        <span class="text-neutral-500">Result val_bpb:</span>
        <span class="ml-1 font-mono">{{ approval.metrics.result_val_bpb?.toFixed(4) ?? '—' }}</span>
      </div>
      <div v-if="approval.metrics.improvement_pct != null" class="col-span-2">
        <span class="text-neutral-500">Improvement:</span>
        <span class="ml-1 font-mono text-green-600 dark:text-green-400">
          {{ approval.metrics.improvement_pct.toFixed(2) }}%
        </span>
      </div>
    </div>

    <div class="flex gap-2">
      <button
        :disabled="deciding"
        class="rounded-md bg-green-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-50"
        @click="handleApprove"
      >
        Approve
      </button>
      <button
        :disabled="deciding"
        class="rounded-md bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
        @click="handleReject"
      >
        Reject
      </button>
    </div>
  </div>
</template>
```

- [ ] **Step 2: Commit**

```bash
git add autobot-frontend/src/components/autoresearch/ApprovalCard.vue
git commit -m "feat(frontend): add ApprovalCard component for experiment approval UI (#2600)"
```

---

### Task 15: ExperimentTimeline Component

**Files:**
- Create: `autobot-frontend/src/components/autoresearch/ExperimentTimeline.vue`

- [ ] **Step 1: Create the component**

```vue
<!-- autobot-frontend/src/components/autoresearch/ExperimentTimeline.vue -->

<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->

<script setup lang="ts">
import { computed } from 'vue'
import type { Experiment } from '@/composables/useAutoResearch'
import ApprovalCard from './ApprovalCard.vue'

const props = defineProps<{
  experiments: Experiment[]
  pendingApprovals: Array<{
    session_id: string
    experiment_id: string
    details: Record<string, unknown>
  }>
}>()

const emit = defineEmits<{
  approve: [sessionId: string, experimentId: string]
  reject: [sessionId: string, experimentId: string]
}>()

const stateColors: Record<string, string> = {
  pending: 'bg-neutral-400',
  running: 'bg-blue-500',
  completed: 'bg-green-500',
  failed: 'bg-red-500',
  kept: 'bg-emerald-600',
  discarded: 'bg-orange-500',
}

const sortedExperiments = computed(() =>
  [...props.experiments].sort((a, b) => b.created_at - a.created_at),
)

function formatTime(timestamp: number): string {
  return new Date(timestamp * 1000).toLocaleString()
}

function getApproval(experimentId: string) {
  return props.pendingApprovals.find((a) => a.experiment_id === experimentId)
}
</script>

<template>
  <div class="space-y-3">
    <div v-if="sortedExperiments.length === 0" class="py-8 text-center text-neutral-500">
      No experiments yet
    </div>

    <div
      v-for="exp in sortedExperiments"
      :key="exp.id"
      class="rounded-lg border border-neutral-200 p-4 dark:border-neutral-700"
    >
      <div class="mb-2 flex items-center justify-between">
        <div class="flex items-center gap-2">
          <span
            :class="stateColors[exp.state] ?? 'bg-neutral-400'"
            class="inline-block h-2 w-2 rounded-full"
          ></span>
          <span class="text-sm font-medium capitalize">{{ exp.state }}</span>
        </div>
        <span class="text-xs text-neutral-500">{{ formatTime(exp.created_at) }}</span>
      </div>

      <p class="mb-2 text-sm text-neutral-700 dark:text-neutral-300">
        {{ exp.hypothesis || 'No hypothesis' }}
      </p>

      <div v-if="exp.result" class="flex gap-4 text-xs text-neutral-500">
        <span v-if="exp.result.val_bpb != null">
          val_bpb: <span class="font-mono">{{ exp.result.val_bpb.toFixed(4) }}</span>
        </span>
        <span v-if="exp.result.wall_time_seconds > 0">
          {{ exp.result.wall_time_seconds.toFixed(0) }}s
        </span>
        <span v-if="exp.result.tokens_per_second != null">
          {{ exp.result.tokens_per_second.toFixed(0) }} tok/s
        </span>
      </div>

      <!-- Inline approval card -->
      <ApprovalCard
        v-if="getApproval(exp.id)"
        :approval="{
          sessionId: getApproval(exp.id)!.session_id,
          experimentId: exp.id,
          metrics: exp.result
            ? {
                baseline_val_bpb: exp.baseline_val_bpb ?? undefined,
                result_val_bpb: exp.result.val_bpb ?? undefined,
              }
            : undefined,
        }"
        class="mt-3"
        @approve="emit('approve', $event, exp.id)"
        @reject="emit('reject', $event, exp.id)"
      />
    </div>
  </div>
</template>
```

- [ ] **Step 2: Commit**

```bash
git add autobot-frontend/src/components/autoresearch/ExperimentTimeline.vue
git commit -m "feat(frontend): add ExperimentTimeline component with inline approvals (#2600)"
```

---

### Task 16: PromptOptimizerPanel + InsightsPanel Components

**Files:**
- Create: `autobot-frontend/src/components/autoresearch/PromptOptimizerPanel.vue`
- Create: `autobot-frontend/src/components/autoresearch/InsightsPanel.vue`

- [ ] **Step 1: Create PromptOptimizerPanel**

```vue
<!-- autobot-frontend/src/components/autoresearch/PromptOptimizerPanel.vue -->

<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->

<script setup lang="ts">
import { ref } from 'vue'
import type { OptimizationSession, PromptVariant } from '@/composables/useAutoResearch'

const props = defineProps<{
  session: OptimizationSession | null
  variants: PromptVariant[]
}>()

const emit = defineEmits<{
  start: [agentName: string, maxRounds: number]
  cancel: []
  scoreVariant: [variantId: string, score: number, comment: string]
}>()

const agentName = ref('autoresearch_hypothesis')
const maxRounds = ref(3)
const reviewScore = ref(5)
const reviewComment = ref('')
const reviewingVariantId = ref<string | null>(null)

function handleStart() {
  emit('start', agentName.value, maxRounds.value)
}

function submitScore(variantId: string) {
  emit('scoreVariant', variantId, reviewScore.value, reviewComment.value)
  reviewingVariantId.value = null
  reviewScore.value = 5
  reviewComment.value = ''
}
</script>

<template>
  <div>
    <h3 class="mb-3 text-lg font-semibold">Prompt Optimizer</h3>

    <!-- Start/Cancel controls -->
    <div v-if="!session" class="mb-4 flex items-end gap-3">
      <div>
        <label class="mb-1 block text-xs text-neutral-500">Target Agent</label>
        <input
          v-model="agentName"
          class="rounded-md border px-3 py-1.5 text-sm dark:border-neutral-600 dark:bg-neutral-800"
        />
      </div>
      <div>
        <label class="mb-1 block text-xs text-neutral-500">Max Rounds</label>
        <input
          v-model.number="maxRounds"
          type="number"
          min="1"
          max="10"
          class="w-20 rounded-md border px-3 py-1.5 text-sm dark:border-neutral-600 dark:bg-neutral-800"
        />
      </div>
      <button
        class="rounded-md bg-blue-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-blue-700"
        @click="handleStart"
      >
        Start Optimization
      </button>
    </div>

    <div v-else class="mb-4">
      <div class="flex items-center gap-3">
        <span class="text-sm">
          Status: <span class="font-medium capitalize">{{ session.status }}</span>
        </span>
        <span class="text-sm text-neutral-500">
          Round {{ session.rounds_completed }}/{{ session.max_rounds }}
        </span>
        <button
          v-if="session.status === 'running'"
          class="rounded-md bg-red-600 px-3 py-1 text-sm text-white hover:bg-red-700"
          @click="emit('cancel')"
        >
          Cancel
        </button>
      </div>
      <div v-if="session.best_variant" class="mt-2 text-sm text-green-600 dark:text-green-400">
        Best score: {{ session.best_variant.final_score.toFixed(3) }}
      </div>
    </div>

    <!-- Variant list -->
    <div v-if="variants.length > 0" class="space-y-2">
      <div
        v-for="variant in variants"
        :key="variant.id"
        class="rounded-md border p-3 text-sm dark:border-neutral-700"
      >
        <div class="mb-1 flex items-center justify-between">
          <span class="font-mono text-xs text-neutral-500">{{ variant.id.slice(0, 8) }}</span>
          <span class="font-medium">Score: {{ variant.final_score.toFixed(3) }}</span>
        </div>
        <p class="mb-2 text-neutral-600 dark:text-neutral-400">
          {{ variant.prompt_text.slice(0, 200) }}{{ variant.prompt_text.length > 200 ? '...' : '' }}
        </p>

        <!-- Human review form -->
        <div v-if="reviewingVariantId === variant.id" class="mt-2 flex items-end gap-2">
          <input
            v-model.number="reviewScore"
            type="number"
            min="0"
            max="10"
            class="w-16 rounded border px-2 py-1 text-sm dark:border-neutral-600 dark:bg-neutral-800"
          />
          <input
            v-model="reviewComment"
            placeholder="Comment..."
            class="flex-1 rounded border px-2 py-1 text-sm dark:border-neutral-600 dark:bg-neutral-800"
          />
          <button
            class="rounded bg-green-600 px-3 py-1 text-sm text-white"
            @click="submitScore(variant.id)"
          >
            Submit
          </button>
        </div>
        <button
          v-else
          class="mt-1 text-xs text-blue-600 hover:underline dark:text-blue-400"
          @click="reviewingVariantId = variant.id"
        >
          Review
        </button>
      </div>
    </div>
  </div>
</template>
```

- [ ] **Step 2: Create InsightsPanel**

```vue
<!-- autobot-frontend/src/components/autoresearch/InsightsPanel.vue -->

<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->

<script setup lang="ts">
import { ref } from 'vue'
import type { ExperimentInsight } from '@/composables/useAutoResearch'

defineProps<{
  insights: ExperimentInsight[]
}>()

const emit = defineEmits<{
  search: [query: string]
}>()

const searchQuery = ref('')

function handleSearch() {
  if (searchQuery.value.trim()) {
    emit('search', searchQuery.value.trim())
  }
}

function confidenceColor(confidence: number): string {
  if (confidence >= 0.8) return 'text-green-600 dark:text-green-400'
  if (confidence >= 0.5) return 'text-amber-600 dark:text-amber-400'
  return 'text-red-600 dark:text-red-400'
}
</script>

<template>
  <div>
    <h3 class="mb-3 text-lg font-semibold">Experiment Insights</h3>

    <!-- Search -->
    <div class="mb-4 flex gap-2">
      <input
        v-model="searchQuery"
        placeholder="Search insights..."
        class="flex-1 rounded-md border px-3 py-1.5 text-sm dark:border-neutral-600 dark:bg-neutral-800"
        @keyup.enter="handleSearch"
      />
      <button
        class="rounded-md bg-blue-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-blue-700"
        @click="handleSearch"
      >
        Search
      </button>
    </div>

    <!-- Insights list -->
    <div v-if="insights.length === 0" class="py-4 text-center text-sm text-neutral-500">
      No insights yet. Run experiments and trigger synthesis.
    </div>

    <div v-else class="space-y-2">
      <div
        v-for="insight in insights"
        :key="insight.id"
        class="rounded-md border p-3 dark:border-neutral-700"
      >
        <div class="mb-1 flex items-center justify-between">
          <span :class="confidenceColor(insight.confidence)" class="text-xs font-medium">
            {{ (insight.confidence * 100).toFixed(0) }}% confidence
          </span>
          <span class="text-xs text-neutral-500">
            {{ insight.related_hyperparams.join(', ') }}
          </span>
        </div>
        <p class="text-sm text-neutral-700 dark:text-neutral-300">
          {{ insight.statement }}
        </p>
        <div class="mt-1 text-xs text-neutral-400">
          Based on {{ insight.supporting_experiments.length }} experiment(s)
        </div>
      </div>
    </div>
  </div>
</template>
```

- [ ] **Step 3: Commit**

```bash
git add autobot-frontend/src/components/autoresearch/PromptOptimizerPanel.vue autobot-frontend/src/components/autoresearch/InsightsPanel.vue
git commit -m "feat(frontend): add PromptOptimizerPanel and InsightsPanel components (#2600)"
```

---

### Task 17: ExperimentDashboard View + Route

**Files:**
- Create: `autobot-frontend/src/views/ExperimentDashboard.vue`
- Modify: `autobot-frontend/src/router/index.ts`

- [ ] **Step 1: Create the dashboard view**

```vue
<!-- autobot-frontend/src/views/ExperimentDashboard.vue -->

<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->

<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { useAutoResearch } from '@/composables/useAutoResearch'
import ExperimentTimeline from '@/components/autoresearch/ExperimentTimeline.vue'
import PromptOptimizerPanel from '@/components/autoresearch/PromptOptimizerPanel.vue'
import InsightsPanel from '@/components/autoresearch/InsightsPanel.vue'

const {
  experiments,
  stats,
  loading,
  optimizerStatus,
  variants,
  pendingApprovals,
  insights,
  fetchExperiments,
  fetchStats,
  fetchPendingApprovals,
  fetchInsights,
  startOptimization,
  cancelOptimization,
  fetchVariants,
  scoreVariant,
  approveExperiment,
  rejectExperiment,
  searchInsights,
  startPolling,
  stopPolling,
} = useAutoResearch()

onMounted(async () => {
  await Promise.all([
    fetchExperiments(),
    fetchStats(),
    fetchPendingApprovals(),
    fetchInsights(),
  ])
  startPolling(15000)
})

onUnmounted(() => {
  stopPolling()
})

async function handleStartOptimization(agentName: string, maxRounds: number) {
  await startOptimization(agentName, maxRounds)
}

async function handleScoreVariant(variantId: string, score: number, comment: string) {
  if (optimizerStatus.value) {
    await scoreVariant(variantId, optimizerStatus.value.id, score, comment)
  }
}

async function handleApprove(sessionId: string, experimentId: string) {
  await approveExperiment(sessionId, experimentId)
}

async function handleReject(sessionId: string, experimentId: string) {
  await rejectExperiment(sessionId, experimentId)
}
</script>

<template>
  <div class="mx-auto max-w-7xl space-y-6 p-6">
    <h1 class="text-2xl font-bold">Experiment Dashboard</h1>

    <!-- Stats Header -->
    <div v-if="stats" class="grid grid-cols-2 gap-4 sm:grid-cols-4">
      <div class="rounded-lg border p-4 dark:border-neutral-700">
        <div class="text-2xl font-bold">{{ stats.total_experiments }}</div>
        <div class="text-sm text-neutral-500">Total Experiments</div>
      </div>
      <div class="rounded-lg border p-4 dark:border-neutral-700">
        <div class="text-2xl font-bold text-emerald-600">{{ stats.kept }}</div>
        <div class="text-sm text-neutral-500">Kept</div>
      </div>
      <div class="rounded-lg border p-4 dark:border-neutral-700">
        <div class="text-2xl font-bold text-orange-600">{{ stats.discarded }}</div>
        <div class="text-sm text-neutral-500">Discarded</div>
      </div>
      <div class="rounded-lg border p-4 dark:border-neutral-700">
        <div class="text-2xl font-bold font-mono">
          {{ stats.best_val_bpb?.toFixed(4) ?? '—' }}
        </div>
        <div class="text-sm text-neutral-500">Best val_bpb</div>
      </div>
    </div>

    <!-- Loading indicator -->
    <div v-if="loading" class="py-4 text-center text-neutral-500">
      Loading experiments...
    </div>

    <!-- Main content grid -->
    <div class="grid gap-6 lg:grid-cols-3">
      <!-- Timeline (2/3 width) -->
      <div class="lg:col-span-2">
        <h2 class="mb-3 text-lg font-semibold">Experiment Timeline</h2>
        <ExperimentTimeline
          :experiments="experiments"
          :pending-approvals="pendingApprovals"
          @approve="handleApprove"
          @reject="handleReject"
        />
      </div>

      <!-- Right sidebar (1/3 width) -->
      <div class="space-y-6">
        <PromptOptimizerPanel
          :session="optimizerStatus"
          :variants="variants"
          @start="handleStartOptimization"
          @cancel="cancelOptimization"
          @score-variant="handleScoreVariant"
        />

        <InsightsPanel
          :insights="insights"
          @search="searchInsights"
        />
      </div>
    </div>
  </div>
</template>
```

- [ ] **Step 2: Add route to router/index.ts**

Find the routes array in `autobot-frontend/src/router/index.ts` and add:

```typescript
{
  path: '/experiments',
  name: 'experiments',
  component: () => import('@/views/ExperimentDashboard.vue'),
  meta: {
    title: 'Experiments',
    icon: 'BeakerIcon',
    description: 'AutoResearch experiment dashboard',
    requiresAuth: true,
  },
},
```

- [ ] **Step 3: Verify frontend builds**

Run: `cd autobot-frontend && npx vite build 2>&1 | tail -5`
Expected: Build succeeds

- [ ] **Step 4: Commit**

```bash
git add autobot-frontend/src/views/ExperimentDashboard.vue autobot-frontend/src/router/index.ts
git commit -m "feat(frontend): add ExperimentDashboard view with route registration (#2600)"
```

---

### Task 18: AutoResearchWorkflowAdapter Component

**Files:**
- Create: `autobot-frontend/src/components/autoresearch/AutoResearchWorkflowAdapter.vue`

- [ ] **Step 1: Create the adapter component**

```vue
<!-- autobot-frontend/src/components/autoresearch/AutoResearchWorkflowAdapter.vue -->

<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->

<script setup lang="ts">
import { computed } from 'vue'
import type { Experiment } from '@/composables/useAutoResearch'

const props = defineProps<{
  experiment: Experiment
}>()

const stateLabel: Record<string, string> = {
  pending: 'Pending',
  running: 'Running',
  completed: 'Completed',
  failed: 'Failed',
  kept: 'Kept',
  discarded: 'Discarded',
}

const stateBadgeClass = computed(() => {
  const classes: Record<string, string> = {
    pending: 'bg-neutral-100 text-neutral-600',
    running: 'bg-blue-100 text-blue-700',
    completed: 'bg-green-100 text-green-700',
    failed: 'bg-red-100 text-red-700',
    kept: 'bg-emerald-100 text-emerald-700',
    discarded: 'bg-orange-100 text-orange-700',
  }
  return classes[props.experiment.state] ?? 'bg-neutral-100 text-neutral-600'
})
</script>

<template>
  <div class="flex items-center gap-3 rounded-md border p-3 text-sm dark:border-neutral-700">
    <span
      :class="stateBadgeClass"
      class="rounded-full px-2 py-0.5 text-xs font-medium"
    >
      {{ stateLabel[experiment.state] ?? experiment.state }}
    </span>

    <span class="flex-1 truncate text-neutral-700 dark:text-neutral-300">
      {{ experiment.hypothesis || 'AutoResearch experiment' }}
    </span>

    <span
      v-if="experiment.result?.val_bpb != null"
      class="font-mono text-xs text-neutral-500"
    >
      {{ experiment.result.val_bpb.toFixed(4) }}
    </span>

    <router-link
      to="/experiments"
      class="text-xs text-blue-600 hover:underline dark:text-blue-400"
    >
      Details
    </router-link>
  </div>
</template>
```

- [ ] **Step 2: Commit**

```bash
git add autobot-frontend/src/components/autoresearch/AutoResearchWorkflowAdapter.vue
git commit -m "feat(frontend): add AutoResearchWorkflowAdapter for workflow history view (#2600)"
```

---

### Task 19: Frontend Tests

**Files:**
- Create: `autobot-frontend/src/composables/__tests__/useAutoResearch.spec.ts`
- Create: `autobot-frontend/src/components/autoresearch/__tests__/ApprovalCard.spec.ts`

- [ ] **Step 1: Write composable test**

```typescript
// autobot-frontend/src/composables/__tests__/useAutoResearch.spec.ts

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useAutoResearch } from '../useAutoResearch'

const mockGet = vi.fn()
const mockPost = vi.fn()

vi.mock('../useApi', () => ({
  useApi: () => ({
    get: mockGet,
    post: mockPost,
  }),
}))

describe('useAutoResearch', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // Re-apply mocks (mockReset: true wipes vi.mock factories)
    mockGet.mockReset()
    mockPost.mockReset()
  })

  it('fetchExperiments populates experiments ref', async () => {
    mockGet.mockResolvedValue({
      experiments: [{ id: 'e1', state: 'completed', hypothesis: 'test' }],
    })

    const { experiments, fetchExperiments } = useAutoResearch()
    await fetchExperiments()

    expect(experiments.value).toHaveLength(1)
    expect(experiments.value[0].id).toBe('e1')
  })

  it('fetchStats populates stats ref', async () => {
    mockGet.mockResolvedValue({
      total_experiments: 10,
      kept: 3,
      best_val_bpb: 4.5,
    })

    const { stats, fetchStats } = useAutoResearch()
    await fetchStats()

    expect(stats.value).not.toBeNull()
    expect(stats.value!.total_experiments).toBe(10)
  })

  it('approveExperiment sends correct request', async () => {
    mockPost.mockResolvedValue({})
    mockGet.mockResolvedValue({ approvals: [] })

    const { approveExperiment } = useAutoResearch()
    await approveExperiment('s1', 'e1')

    expect(mockPost).toHaveBeenCalledWith(
      '/api/autoresearch/approvals/s1/e1',
      { decision: 'approved' },
    )
  })
})
```

- [ ] **Step 2: Write ApprovalCard test**

```typescript
// autobot-frontend/src/components/autoresearch/__tests__/ApprovalCard.spec.ts

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ApprovalCard from '../ApprovalCard.vue'

describe('ApprovalCard', () => {
  const defaultProps = {
    approval: {
      sessionId: 's1',
      experimentId: 'e1',
      metrics: {
        baseline_val_bpb: 5.0,
        result_val_bpb: 4.5,
        improvement_pct: 10.0,
      },
    },
  }

  it('renders approval details', () => {
    const wrapper = mount(ApprovalCard, { props: defaultProps })
    expect(wrapper.text()).toContain('Approval Required')
    expect(wrapper.text()).toContain('5.0000')
    expect(wrapper.text()).toContain('4.5000')
    expect(wrapper.text()).toContain('10.00%')
  })

  it('emits approve event on button click', async () => {
    const wrapper = mount(ApprovalCard, { props: defaultProps })
    await wrapper.find('button:first-of-type').trigger('click')
    expect(wrapper.emitted('approve')).toBeTruthy()
    expect(wrapper.emitted('approve')![0]).toEqual(['s1', 'e1'])
  })

  it('emits reject event on button click', async () => {
    const wrapper = mount(ApprovalCard, { props: defaultProps })
    const buttons = wrapper.findAll('button')
    await buttons[1].trigger('click')
    expect(wrapper.emitted('reject')).toBeTruthy()
  })
})
```

- [ ] **Step 3: Run frontend tests**

Run: `cd autobot-frontend && npx vitest run src/composables/__tests__/useAutoResearch.spec.ts src/components/autoresearch/__tests__/ApprovalCard.spec.ts`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add autobot-frontend/src/composables/__tests__/useAutoResearch.spec.ts autobot-frontend/src/components/autoresearch/__tests__/ApprovalCard.spec.ts
git commit -m "test(frontend): add tests for useAutoResearch composable and ApprovalCard (#2600)"
```

---

### Task 20: Final Verification

- [ ] **Step 1: Run all backend autoresearch tests**

Run: `cd autobot-backend && python -m pytest services/autoresearch/ tests/test_autoresearch_m3.py tests/test_autoresearch.py -v`
Expected: All PASS

- [ ] **Step 2: Run frontend build**

Run: `cd autobot-frontend && npx vite build`
Expected: Build succeeds

- [ ] **Step 3: Run frontend tests**

Run: `cd autobot-frontend && npx vitest run`
Expected: All PASS (or only pre-existing failures)

- [ ] **Step 4: Verify no import errors**

Run: `cd autobot-backend && python -c "from services.autoresearch import PromptOptimizer, KnowledgeSynthesizer, ValBpbScorer, LLMJudgeScorer, HumanReviewScorer, ExperimentInsight; print('All M3 imports OK')"`
Expected: `All M3 imports OK`

- [ ] **Step 5: Final commit if any cleanup needed**

```bash
git status
# If any unstaged changes, add and commit
```
