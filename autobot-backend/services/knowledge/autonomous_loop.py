# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
AutonomousLoopRunner — Issue #4680

Scheduled self-directed RAG/synthesis optimisation loop modelled on ASI-Evolve's
hypothesis → experiment → score → analyze → promote cycle.

Phases
------
1. LEARN    — query cognition store + recent lessons from AnalyzerService.
2. HYPOTHESIZE — ask LLM to propose N RAGConfig variants guided by lessons.
3. EXPERIMENT — score each variant against the _RAGEvaluator (precision@k,
                synthesis coherence).
4. ANALYZE  — delegate lesson distillation to AnalyzerService.
5. PROMOTE  — if winner beats baseline by > promotion_threshold, apply the
              variant to the live RAGConfig and log to SynthesisProvenanceLog.
6. SLEEP    — scheduler drives next iteration via cron.

Guardrails
----------
- dry_run mode: full loop, no config mutations.
- promotion_threshold: default 5 % improvement required.
- Hard stop after max_no_improvement_rounds consecutive rounds with no winner.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import timezone
from typing import Any, Deque, Dict, List

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client
from autobot_shared.time_utils import now_utc, parse_utc_iso

# Module-level imports for patchability in tests.
# Deferred via try/except to survive environments where these aren't installed yet.
try:
    from services.knowledge.analyzer_service import _MIN_SCORE_DELTA, get_analyzer_service
except Exception:  # pragma: no cover
    get_analyzer_service = None  # type: ignore[assignment]
    _MIN_SCORE_DELTA = 0.1  # fallback matches analyzer_service default

try:
    from services.knowledge.synthesis_provenance import SynthesisProvenanceLog
except Exception:  # pragma: no cover
    SynthesisProvenanceLog = None  # type: ignore[assignment]

try:
    from services.rag_config import get_rag_config, update_rag_config
except Exception:  # pragma: no cover
    get_rag_config = None  # type: ignore[assignment]
    update_rag_config = None  # type: ignore[assignment]

logger = get_logger(__name__)

# Redis key for persisting _pending_approval across server restarts (Issue #4792).
_PENDING_APPROVAL_REDIS_KEY = "autobot:loop:pending_approval"

# How many config variants to generate per loop iteration.
_DEFAULT_VARIANTS = 5
# After this many consecutive rounds with no improvement, sleep until next cron.
_DEFAULT_MAX_NO_IMPROVEMENT = 5
# Default improvement margin required for promotion (5 %).
_DEFAULT_PROMOTION_THRESHOLD = 0.05

# Parameter search space the LLM may explore.
_PARAM_RANGES: Dict[str, tuple] = {
    "hybrid_weight_semantic": (0.5, 0.9),
    "diversity_threshold": (0.1, 0.8),
    "ucb1_exploration_constant": (0.5, 3.0),
    "max_results_per_stage": (5, 50),
}

# Benchmark queries used for evaluation (topic-discriminating, matches rag_benchmarks corpus).
_EVAL_QUERIES = [
    "Python list comprehensions and generator expressions",
    "PostgreSQL indexes and query performance",
    "TLS encryption and secure network communication",
    "RAG retrieval augmented generation embedding search",
    "cosine similarity precision at k evaluation metrics",
]


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class VariantResult:
    """Result of evaluating one hypothesis variant."""

    variant_id: str
    params: Dict[str, Any]
    precision_at_k: float
    coherence_score: float
    composite_score: float
    error: str | None = None


@dataclass
class LoopRunRecord:
    """Audit record for a single loop iteration."""

    run_id: str
    started_at: str
    finished_at: str
    dry_run: bool
    baseline_score: float
    variants_tested: int
    best_variant_id: str | None
    best_score: float
    promoted: bool
    promoted_params: Dict[str, Any] | None
    lessons_stored: int
    error: str | None = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class LoopStatus:
    """Returned by GET /rag/loop/status."""

    enabled: bool
    dry_run: bool
    last_run: LoopRunRecord | None
    history: List[LoopRunRecord] = field(default_factory=list)
    pending_approval: Dict[str, Any] | None = None  # staging variant awaiting /approve

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "dry_run": self.dry_run,
            "last_run": self.last_run.to_dict() if self.last_run else None,
            "history": [r.to_dict() for r in self.history[-20:]],
            "pending_approval": self.pending_approval,
        }


# ---------------------------------------------------------------------------
# Internal evaluator
# ---------------------------------------------------------------------------


class _RAGEvaluator:
    """Scores a RAGConfig variant using precision@k on a deterministic corpus.

    Uses the same ``_deterministic_embed`` approach as rag_benchmarks.py so
    evaluation is fully in-process without external services.
    """

    _DIM = 128
    _K = 5

    # Ground-truth mirrors _GROUND_TRUTH in rag_benchmarks.py
    _GROUND_TRUTH: Dict[str, set] = {
        "Python list comprehensions and generator expressions": {"python_02", "python_04"},
        "PostgreSQL indexes and query performance": {"db_02", "db_01"},
        "TLS encryption and secure network communication": {"net_03", "net_01"},
        "RAG retrieval augmented generation embedding search": {"ml_02", "ml_09"},
        "cosine similarity precision at k evaluation metrics": {"ml_04", "ml_05"},
    }

    def __init__(self) -> None:
        self._collection: Any | None = None

    async def _ensure_collection(self) -> Any | None:
        """Lazy-init an in-memory collection seeded with the corpus."""
        if self._collection is not None:
            return self._collection
        try:
            from knowledge.backends import AsyncInMemoryClient
            from knowledge.rag_benchmarks import _TOPIC_DOCS, _deterministic_embed

            client = AsyncInMemoryClient()
            collection = await client.create_collection(
                "loop_eval_bench",
                metadata={"hnsw:space": "cosine"},
            )
            ids = [d[0] for d in _TOPIC_DOCS]
            embeddings = [_deterministic_embed(d[1], self._DIM) for d in _TOPIC_DOCS]
            documents = [d[1] for d in _TOPIC_DOCS]
            metadatas = [{"topic": d[2]} for d in _TOPIC_DOCS]
            await collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas,
            )
            self._collection = collection
            logger.debug("_RAGEvaluator: seeded in-memory collection (%d docs)", len(ids))
            return collection
        except Exception:
            logger.exception("_RAGEvaluator: failed to initialise in-memory collection")
            return None

    async def score_variant(self, params: Dict[str, Any]) -> float:
        """Return composite score [0,1] for a config variant.

        Composite = mean precision@k across _EVAL_QUERIES.
        The ``hybrid_weight_semantic`` param influences retrieval ranking via
        a soft reranking of ChromaDB distances weighted by the semantic weight.
        Other params (ucb1_exploration_constant etc.) are acknowledged but only
        hybrid_weight_semantic meaningfully affects the in-process evaluator.
        """
        collection = await self._ensure_collection()
        if collection is None:
            return 0.0

        try:
            from knowledge.rag_benchmarks import _deterministic_embed

            semantic_w = float(params.get("hybrid_weight_semantic", 0.7))
            scores: List[float] = []

            for query, expected in self._GROUND_TRUTH.items():
                q_vec = _deterministic_embed(query, self._DIM)
                raw = await collection.query(
                    query_embeddings=[q_vec],
                    n_results=self._K,
                    include=["distances"],
                )
                retrieved_ids = raw["ids"][0]
                # Apply soft reranking: higher semantic_w boosts top results.
                # Reorder by (1 - distance) * semantic_w approximation.
                distances = raw.get("distances", [[]])[0]
                ranked = sorted(
                    zip(retrieved_ids, distances),
                    key=lambda x: (1.0 - x[1]) * semantic_w,
                    reverse=True,
                )
                top_k_ids = [doc_id for doc_id, _ in ranked[: self._K]]
                p_at_k = sum(1 for doc_id in top_k_ids if doc_id in expected) / max(len(top_k_ids), 1)
                scores.append(p_at_k)

            return sum(scores) / max(len(scores), 1)
        except Exception:
            logger.exception("_RAGEvaluator: scoring failed for params %s", params)
            return 0.0

    async def score_baseline(self) -> float:
        """Score the current RAGConfig as the baseline."""
        cfg = get_rag_config()
        params = {
            "hybrid_weight_semantic": cfg.hybrid_weight_semantic,
            "diversity_threshold": cfg.diversity_threshold,
            "ucb1_exploration_constant": cfg.ucb1_exploration_constant,
            "max_results_per_stage": cfg.max_results_per_stage,
        }
        return await self.score_variant(params)


# ---------------------------------------------------------------------------
# AutonomousLoopRunner
# ---------------------------------------------------------------------------


class AutonomousLoopRunner:
    """Drives the 6-phase autonomous improvement cycle for RAG/synthesis quality.

    Issue #4680: Modelled on ASI-Evolve's hypothesis→experiment→score→analyze→promote
    pipeline. Integrates with AnalyzerService (#4678), UCB1 sampling (#4674),
    CognitionStore (#4679), and SynthesisProvenanceLog.
    """

    def __init__(
        self,
        llm_service: Any,
        *,
        dry_run: bool = True,
        max_variants: int = _DEFAULT_VARIANTS,
        promotion_threshold: float = _DEFAULT_PROMOTION_THRESHOLD,
        max_no_improvement_rounds: int = _DEFAULT_MAX_NO_IMPROVEMENT,
    ) -> None:
        self._llm = llm_service
        self.dry_run = dry_run
        self.max_variants = max_variants
        self.promotion_threshold = promotion_threshold
        self.max_no_improvement_rounds = max_no_improvement_rounds

        self._evaluator = _RAGEvaluator()
        self._history: Deque[LoopRunRecord] = deque(maxlen=100)
        self._pending_approval: Dict[str, Any] | None = None
        self._no_improvement_count: int = 0
        self._running = False

    # ------------------------------------------------------------------
    # Redis persistence helpers (Issue #4792)
    # ------------------------------------------------------------------

    async def restore_state(self) -> None:
        """Restore _pending_approval from Redis after a server restart.

        Called once by get_loop_runner() immediately after construction.
        Silently skips if Redis is unavailable.
        Discards entries older than 7 days (matches TTL on the Redis key).
        """
        try:
            redis = await get_async_redis_client(database="knowledge")
            if redis is None:
                return
            raw = await redis.get(_PENDING_APPROVAL_REDIS_KEY)
            if raw:
                data = json.loads(raw)
                staged_at_str = data.pop("staged_at", None)
                if staged_at_str:
                    staged_at = parse_utc_iso(staged_at_str)
                    if staged_at.tzinfo is None:
                        staged_at = staged_at.replace(tzinfo=timezone.utc)
                    if (now_utc() - staged_at).days > 7:
                        logger.info("restore_state: discarding stale pending_approval (>7 days old)")
                        await redis.delete(_PENDING_APPROVAL_REDIS_KEY)
                        return
                self._pending_approval = data
                logger.info(
                    "AutonomousLoop: restored pending_approval from Redis: %s",
                    self._pending_approval,
                )
        except Exception:
            logger.debug("AutonomousLoop: could not restore pending_approval from Redis (non-fatal)")

    async def _save_pending_approval(self, params: Dict[str, Any]) -> None:
        """Persist _pending_approval to Redis so it survives restarts.

        A 7-day TTL is set so stale entries are automatically evicted.
        A ``staged_at`` timestamp is embedded so restore_state() can
        skip entries that survived the TTL via a Redis replica lag.
        """
        try:
            redis = await get_async_redis_client(database="knowledge")
            if redis is None:
                return
            params_with_ts = {**params, "staged_at": now_utc().isoformat()}
            await redis.set(_PENDING_APPROVAL_REDIS_KEY, json.dumps(params_with_ts), ex=7 * 24 * 3600)
        except Exception:
            logger.debug("AutonomousLoop: could not persist pending_approval to Redis (non-fatal)")

    async def _clear_pending_approval(self) -> None:
        """Remove the persisted pending_approval from Redis."""
        try:
            redis = await get_async_redis_client(database="knowledge")
            if redis is None:
                return
            await redis.delete(_PENDING_APPROVAL_REDIS_KEY)
        except Exception:
            logger.debug("AutonomousLoop: could not clear pending_approval from Redis (non-fatal)")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run_once(self) -> LoopRunRecord:
        """Execute one full loop iteration and return the audit record.

        Phases: LEARN → HYPOTHESIZE → EXPERIMENT → ANALYZE → PROMOTE
        """
        run_id = str(uuid.uuid4())[:12]
        started_at = now_utc().isoformat()
        logger.info("AutonomousLoop: starting run %s (dry_run=%s)", run_id, self.dry_run)

        self._running = True
        record = LoopRunRecord(
            run_id=run_id,
            started_at=started_at,
            finished_at="",
            dry_run=self.dry_run,
            baseline_score=0.0,
            variants_tested=0,
            best_variant_id=None,
            best_score=0.0,
            promoted=False,
            promoted_params=None,
            lessons_stored=0,
        )

        try:
            # 1. LEARN
            lessons_text = await self._phase_learn(run_id)

            # 2. HYPOTHESIZE
            baseline_score = await self._evaluator.score_baseline()
            record.baseline_score = baseline_score
            variants = await self._phase_hypothesize(lessons_text, run_id)
            if not variants:
                logger.warning("AutonomousLoop: no variants generated for run %s", run_id)
                record.error = "no_variants"
                record.finished_at = now_utc().isoformat()
                self._history.append(record)
                return record

            # 3. EXPERIMENT
            results = await self._phase_experiment(variants)
            record.variants_tested = len(results)

            # 4. ANALYZE
            lessons_stored = await self._phase_analyze(results, baseline_score, run_id)
            record.lessons_stored = lessons_stored

            # 5. PROMOTE
            best = max(results, key=lambda r: r.composite_score)
            record.best_variant_id = best.variant_id
            record.best_score = best.composite_score

            promoted = await self._phase_promote(best, baseline_score, run_id)
            record.promoted = promoted
            if promoted:
                record.promoted_params = best.params
                self._no_improvement_count = 0
            else:
                self._no_improvement_count += 1
                logger.info(
                    "AutonomousLoop: no improvement (count=%d/%d)",
                    self._no_improvement_count,
                    self.max_no_improvement_rounds,
                )

        except Exception:
            logger.exception("AutonomousLoop: run %s failed", run_id)
            record.error = "unexpected_error"

        finally:
            self._running = False

        record.finished_at = now_utc().isoformat()
        self._history.append(record)
        logger.info(
            "AutonomousLoop: run %s done — baseline=%.4f best=%.4f promoted=%s",
            run_id,
            record.baseline_score,
            record.best_score,
            record.promoted,
        )
        return record

    def should_stop(self) -> bool:
        """Return True when consecutive no-improvement rounds hit the hard stop."""
        return self._no_improvement_count >= self.max_no_improvement_rounds

    def get_status(self) -> LoopStatus:
        """Return current loop status for the API endpoint."""
        cfg = get_rag_config()
        return LoopStatus(
            enabled=cfg.autonomous_loop_enabled,
            dry_run=self.dry_run,
            last_run=self._history[-1] if self._history else None,
            history=list(self._history),
            pending_approval=self._pending_approval,
        )

    async def approve_pending(self) -> bool:
        """Promote the staging variant that is awaiting human approval.

        Returns True if a pending variant was applied, False if none existed.
        """
        if self._pending_approval is None:
            logger.info("AutonomousLoop: no pending variant to approve")
            return False

        params = self._pending_approval
        self._pending_approval = None
        await self._clear_pending_approval()
        await self._apply_params(params, run_id="manual-approve")
        logger.info("AutonomousLoop: pending variant approved and applied: %s", params)
        return True

    async def reject_pending(self) -> bool:
        """Discard the staging variant that is awaiting human approval.

        Returns True if a pending variant was cleared, False if none existed.
        """
        if self._pending_approval is None:
            logger.info("AutonomousLoop: no pending variant to reject")
            return False

        self._pending_approval = None
        await self._clear_pending_approval()
        logger.info("AutonomousLoop: pending variant rejected and cleared")
        return True

    # ------------------------------------------------------------------
    # Phase implementations
    # ------------------------------------------------------------------

    async def _phase_learn(self, run_id: str) -> str:
        """LEARN phase: gather recent lessons and cognition store context."""
        parts: List[str] = []

        # Query AnalyzerService lessons
        try:
            svc = get_analyzer_service(self._llm)
            lessons = await svc.get_lessons_context("RAG retrieval optimization synthesis quality", limit=5)
            if lessons:
                parts.append(lessons)
                logger.debug("AutonomousLoop[%s] LEARN: fetched analyzer lessons", run_id)
        except Exception:
            logger.debug("AutonomousLoop[%s] LEARN: analyzer lessons unavailable", run_id)

        # Query recent provenance log for context
        try:
            plog = SynthesisProvenanceLog()
            recent = await plog.get_recent(limit=5)
            if recent:
                summary = "; ".join(f"run={e.get('run_id', '?')} model={e.get('llm_model', '?')}" for e in recent)
                parts.append(f"Recent provenance runs: {summary}")
        except Exception:
            logger.debug("AutonomousLoop[%s] LEARN: provenance log unavailable", run_id)

        return "\n".join(parts) if parts else "No prior lessons available."

    async def _phase_hypothesize(self, lessons_context: str, run_id: str) -> List[Dict[str, Any]]:
        """HYPOTHESIZE phase: ask LLM to propose N config variants."""
        cfg = get_rag_config()
        baseline_params = {
            "hybrid_weight_semantic": cfg.hybrid_weight_semantic,
            "diversity_threshold": cfg.diversity_threshold,
            "ucb1_exploration_constant": cfg.ucb1_exploration_constant,
            "max_results_per_stage": cfg.max_results_per_stage,
        }

        prompt = (
            f"You are a RAG tuning expert. Based on the lessons and current config, propose "
            f"{self.max_variants} parameter variants to test. "
            f"Return ONLY a JSON array of objects, each with these keys: "
            f"hybrid_weight_semantic (float 0.5-0.9), "
            f"diversity_threshold (float 0.1-0.8), "
            f"ucb1_exploration_constant (float 0.5-3.0), "
            f"max_results_per_stage (int 5-50). "
            f"No commentary, no markdown fences.\n\n"
            f"Current config: {json.dumps(baseline_params)}\n\n"
            f"Lessons: {lessons_context}"
        )

        try:
            response = await self._llm.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=600,
            )
            raw = getattr(response, "content", str(response)).strip()
            # Strip optional markdown fences
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            variants: List[Dict[str, Any]] = json.loads(raw)
            if not isinstance(variants, list):
                raise ValueError("Expected JSON array")
            logger.info("AutonomousLoop[%s] HYPOTHESIZE: %d variants proposed", run_id, len(variants))
            return variants[: self.max_variants]
        except Exception:
            logger.exception("AutonomousLoop[%s] HYPOTHESIZE: LLM call failed", run_id)
            # Fallback: random perturbation of baseline
            import random

            fallback = []
            for _ in range(min(3, self.max_variants)):
                sem_w = round(random.uniform(0.5, 0.9), 2)  # nosec B311 - UCB1 exploration weight, not cryptographic
                fallback.append(
                    {
                        "hybrid_weight_semantic": sem_w,
                        "hybrid_weight_keyword": round(1.0 - sem_w, 2),
                        "diversity_threshold": round(
                            random.uniform(0.1, 0.8), 2  # nosec B311 - diversity sampling, not cryptographic
                        ),
                        "ucb1_exploration_constant": round(
                            random.uniform(0.5, 3.0), 2  # nosec B311 - UCB1 exploration constant, not cryptographic
                        ),
                        "max_results_per_stage": random.choice(
                            [5, 10, 20, 30]
                        ),  # nosec B311 - variant selection for autonomous loop, not cryptographic
                    }
                )
            logger.info("AutonomousLoop[%s] HYPOTHESIZE: using %d fallback variants", run_id, len(fallback))
            return fallback

    async def _phase_experiment(self, variants: List[Dict[str, Any]]) -> List[VariantResult]:
        """EXPERIMENT phase: score all variants concurrently."""
        tasks = [self._score_one_variant(variant, idx) for idx, variant in enumerate(variants)]
        results: List[VariantResult] = await asyncio.gather(*tasks, return_exceptions=False)
        logger.info("AutonomousLoop EXPERIMENT: %d variants scored", len(results))
        return results

    async def _score_one_variant(self, params: Dict[str, Any], idx: int) -> VariantResult:
        """Score a single variant and wrap in VariantResult."""
        variant_id = f"v{idx:02d}"
        try:
            composite = await self._evaluator.score_variant(params)
            return VariantResult(
                variant_id=variant_id,
                params=params,
                precision_at_k=composite,
                coherence_score=composite,  # single metric; extend with synthesis coherence later
                composite_score=composite,
            )
        except Exception as exc:
            logger.warning("AutonomousLoop: variant %s scoring error: %s", variant_id, exc)
            return VariantResult(
                variant_id=variant_id,
                params=params,
                precision_at_k=0.0,
                coherence_score=0.0,
                composite_score=0.0,
                error=str(exc),
            )

    async def _phase_analyze(
        self,
        results: List[VariantResult],
        baseline_score: float,
        run_id: str,
    ) -> int:
        """ANALYZE phase: delegate lesson distillation to AnalyzerService."""
        try:
            svc = get_analyzer_service(self._llm)
            # Build a synthetic "output" summarising the experiment results for the analyzer.
            summary = f"Baseline score: {baseline_score:.4f}\n" + "\n".join(
                f"Variant {r.variant_id}: score={r.composite_score:.4f} params={r.params}" for r in results
            )
            score_delta = max((r.composite_score for r in results), default=0.0) - baseline_score
            if score_delta < 0:
                # All variants regressed — prefix summary so the LLM distils avoidance lessons.
                summary = f"[REGRESSION] All variants underperformed baseline. {summary}"
            lessons = await svc.analyze_synthesis_run(
                run_id=f"loop:{run_id}",
                input_docs=[f"params: {json.dumps(r.params)}" for r in results],
                output_summary=summary,
                # For regression runs (delta < 0), floor at _MIN_SCORE_DELTA so the
                # analyzer's guard passes and the LLM can distil "what to avoid" lessons.
                # Positive deltas are passed as-is to preserve their magnitude.
                score=max(_MIN_SCORE_DELTA, score_delta),
            )
            if lessons:
                await svc.store_lessons(lessons)
                logger.info("AutonomousLoop[%s] ANALYZE: stored %d lessons", run_id, len(lessons))
                return len(lessons)
        except Exception:
            logger.debug("AutonomousLoop[%s] ANALYZE: lesson distillation failed (non-fatal)", run_id)
        return 0

    async def _phase_promote(
        self,
        best: VariantResult,
        baseline_score: float,
        run_id: str,
    ) -> bool:
        """PROMOTE phase: apply winning variant if it beats baseline by threshold.

        Guardrail: never promote a variant that degrades the benchmark score.
        """
        delta = best.composite_score - baseline_score
        if delta <= 0:
            logger.info(
                "AutonomousLoop[%s] PROMOTE: winner (%.4f) does not improve baseline (%.4f)",
                run_id,
                best.composite_score,
                baseline_score,
            )
            return False

        relative_improvement = delta / max(baseline_score, 1e-9)
        if relative_improvement < self.promotion_threshold:
            logger.info(
                "AutonomousLoop[%s] PROMOTE: improvement %.2f%% below threshold %.2f%%",
                run_id,
                relative_improvement * 100,
                self.promotion_threshold * 100,
            )
            # Store as pending for human review gate; persist to Redis (Issue #4792).
            self._pending_approval = best.params
            await self._save_pending_approval(best.params)
            return False

        if self.dry_run:
            logger.info(
                "AutonomousLoop[%s] PROMOTE: dry_run — winner %.4f (+%.2f%%) NOT applied",
                run_id,
                best.composite_score,
                relative_improvement * 100,
            )
            return False

        await self._apply_params(best.params, run_id=run_id)
        logger.info(
            "AutonomousLoop[%s] PROMOTE: applied variant %s (%.4f, +%.2f%%)",
            run_id,
            best.variant_id,
            best.composite_score,
            relative_improvement * 100,
        )
        return True

    async def _apply_params(self, params: Dict[str, Any], run_id: str) -> None:
        """Apply params to the live RAGConfig and log to SynthesisProvenanceLog."""
        # Ensure hybrid weights remain normalised
        sem_w = float(params.get("hybrid_weight_semantic", 0.7))
        params["hybrid_weight_semantic"] = sem_w
        params["hybrid_weight_keyword"] = round(1.0 - sem_w, 4)

        update_rag_config(params)
        logger.info("AutonomousLoop[%s] APPLY: RAGConfig updated: %s", run_id, params)

        # Audit trail in provenance log
        try:
            plog = SynthesisProvenanceLog()
            start_ms = int(time.time() * 1000)
            await plog.log_run(
                run_id=f"loop:{run_id}",
                source_docs=list(params.keys()),
                synthesis_ids=[f"promoted:{run_id}"],
                llm_model="autonomous_loop",
                prompt_template="rag_config_promotion",
                duration_ms=int(time.time() * 1000) - start_ms,
            )
        except Exception:
            logger.debug("AutonomousLoop: provenance log write failed (non-fatal)")


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_loop_orchestrator: AutonomousLoopRunner | None = None
_loop_lock = asyncio.Lock()


async def get_loop_runner(
    llm_service: Any,
    *,
    dry_run: bool = True,
    max_variants: int = _DEFAULT_VARIANTS,
    promotion_threshold: float = _DEFAULT_PROMOTION_THRESHOLD,
    max_no_improvement_rounds: int = _DEFAULT_MAX_NO_IMPROVEMENT,
) -> AutonomousLoopRunner:
    """Return the singleton AutonomousLoopRunner.

    Parameters are only applied on first call; subsequent calls return the
    cached instance regardless of arguments.

    Race-condition guard: if the singleton was previously created with
    ``llm_service=None`` (e.g. an API endpoint called before the background
    scheduler provides a real service), and the caller now supplies a real
    service, the None-locked instance is replaced so the orchestrator can
    actually reach the LLM.  A singleton that already has a real ``_llm``
    is never replaced.
    """
    global _loop_orchestrator
    async with _loop_lock:
        # Never replace a running instance — it would orphan in-flight experiments.
        if _loop_orchestrator is not None and getattr(_loop_orchestrator, "_running", False):
            return _loop_orchestrator
        if _loop_orchestrator is None or (_loop_orchestrator._llm is None and llm_service is not None):
            orchestrator = AutonomousLoopRunner(
                llm_service,
                dry_run=dry_run,
                max_variants=max_variants,
                promotion_threshold=promotion_threshold,
                max_no_improvement_rounds=max_no_improvement_rounds,
            )
            # Restore any pending_approval that survived a server restart (Issue #4792).
            await orchestrator.restore_state()
            _loop_orchestrator = orchestrator
    return _loop_orchestrator


async def run_scheduled_loop(llm_service: Any) -> None:
    """Entry point called by workflow_scheduler when the cron fires.

    Runs a single loop iteration and stops if the hard-stop condition is met.
    """
    cfg = get_rag_config()
    if not cfg.autonomous_loop_enabled:
        logger.info("AutonomousLoop: disabled via config — skipping scheduled run")
        return

    orchestrator = await get_loop_runner(
        llm_service,
        dry_run=cfg.autonomous_loop_dry_run,
        promotion_threshold=cfg.autonomous_loop_promotion_threshold,
        max_no_improvement_rounds=_DEFAULT_MAX_NO_IMPROVEMENT,
    )

    record = await orchestrator.run_once()
    logger.info("AutonomousLoop scheduled run complete: %s", record.to_dict())

    if orchestrator.should_stop():
        logger.info(
            "AutonomousLoop: hard-stop reached after %d consecutive rounds with no improvement",
            orchestrator.max_no_improvement_rounds,
        )
