# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
RLM Benchmark — single-pass vs recursive self-reflection comparison.

Runs a set of diverse queries through both the standard single-pass path
and the RLM-enhanced path, recording quality scores, latency, and token
cost so we can measure whether recursive refinement actually helps.

Issue #1381: Follow-up from #1373.

Usage (CLI):
    cd autobot-backend
    python -m rlm.benchmark --queries 5 --output results.json

Usage (programmatic):
    from rlm.benchmark import run_benchmark
    results = await run_benchmark()
"""

import asyncio
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

import httpx
from rlm.evaluator import ResponseQualityEvaluator
from rlm.types import RLMConfig

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------
# Query corpus
# -----------------------------------------------------------------------

BENCHMARK_QUERIES: List[Dict[str, Any]] = [
    {
        "query": "What is AutoBot?",
        "category": "simple",
        "expected_complexity": 0.3,
    },
    {
        "query": "How do I deploy a new service role to an SLM node?",
        "category": "procedural",
        "expected_complexity": 0.7,
    },
    {
        "query": (
            "Explain the tradeoffs between using Redis pub/sub vs "
            "WebSocket channels for real-time agent communication "
            "in a distributed multi-node setup."
        ),
        "category": "reasoning",
        "expected_complexity": 0.9,
    },
    {
        "query": (
            "My backend returns 502 after restart. The health "
            "endpoint works but WebSocket connections fail. "
            "What could cause this?"
        ),
        "category": "troubleshooting",
        "expected_complexity": 0.85,
    },
    {
        "query": (
            "Compare LangGraph StateGraph with a hand-rolled "
            "async generator pipeline for chat workflow "
            "orchestration. Which scales better?"
        ),
        "category": "analysis",
        "expected_complexity": 0.9,
    },
]


# -----------------------------------------------------------------------
# Result types
# -----------------------------------------------------------------------


@dataclass
class SinglePassResult:
    """Metrics from one single-pass LLM call."""

    query: str
    category: str
    response: str
    quality_score: float
    latency_ms: float
    response_tokens: int


@dataclass
class RLMResult:
    """Metrics from the RLM-enhanced (recursive) path."""

    query: str
    category: str
    final_response: str
    final_quality_score: float
    total_latency_ms: float
    total_response_tokens: int
    reflections: int
    scores_per_pass: List[float] = field(default_factory=list)


@dataclass
class BenchmarkSummary:
    """Aggregate comparison across all queries."""

    queries_run: int = 0
    avg_single_score: float = 0.0
    avg_rlm_score: float = 0.0
    score_delta: float = 0.0
    avg_single_latency_ms: float = 0.0
    avg_rlm_latency_ms: float = 0.0
    latency_overhead_pct: float = 0.0
    avg_single_tokens: float = 0.0
    avg_rlm_tokens: float = 0.0
    token_overhead_pct: float = 0.0
    rlm_improved_count: int = 0


# -----------------------------------------------------------------------
# LLM helper
# -----------------------------------------------------------------------


async def _generate(
    prompt: str,
    model: str = "llama3.2:latest",
    temperature: float = 0.5,
    max_tokens: int = 1024,
    timeout_s: float = 30.0,
) -> str:
    """Call Ollama generate and return the raw text."""
    from autobot_shared.ssot_config import get_config

    ssot = get_config()
    url = f"{ssot.ollama_url}/api/generate"

    async with httpx.AsyncClient(timeout=timeout_s) as client:
        resp = await client.post(
            url,
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens,
                },
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("response", "")


# -----------------------------------------------------------------------
# Benchmark runners
# -----------------------------------------------------------------------


async def _run_single_pass(query: str, category: str, model: str) -> SinglePassResult:
    """Run a single-pass LLM call and evaluate the response."""
    evaluator = ResponseQualityEvaluator()

    t0 = time.monotonic()
    response = await _generate(query, model=model)
    latency = (time.monotonic() - t0) * 1000

    result = await evaluator.evaluate(query=query, response=response)
    tokens = len(response.split())  # rough word-count proxy

    return SinglePassResult(
        query=query,
        category=category,
        response=response,
        quality_score=result.quality_score,
        latency_ms=latency,
        response_tokens=tokens,
    )


async def _run_rlm_pass(
    query: str,
    category: str,
    model: str,
    rlm_config: Optional[RLMConfig] = None,
) -> RLMResult:
    """Run the RLM loop: generate -> evaluate -> refine -> repeat."""
    cfg = rlm_config or RLMConfig()
    evaluator = ResponseQualityEvaluator(config=cfg)
    scores: List[float] = []
    total_tokens = 0
    prompt = query
    response = ""

    t0 = time.monotonic()

    for i in range(cfg.max_reflections + 1):
        response = await _generate(prompt, model=model)
        total_tokens += len(response.split())

        result = await evaluator.evaluate(
            query=query, response=response, iteration=i + 1
        )
        scores.append(result.quality_score)

        if result.quality_score >= cfg.quality_threshold:
            break

        if i < cfg.max_reflections:
            hint = result.refinement_hint or result.critique
            prompt = (
                f"{query}\n\n"
                f"[Self-reflection feedback — please improve your "
                f"answer: {hint}]"
            )

    total_latency = (time.monotonic() - t0) * 1000

    return RLMResult(
        query=query,
        category=category,
        final_response=response,
        final_quality_score=scores[-1] if scores else 0.0,
        total_latency_ms=total_latency,
        total_response_tokens=total_tokens,
        reflections=len(scores) - 1,
        scores_per_pass=scores,
    )


# -----------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------


async def run_benchmark(
    queries: Optional[List[Dict[str, Any]]] = None,
    model: str = "llama3.2:latest",
    rlm_config: Optional[RLMConfig] = None,
    max_queries: int = 0,
) -> Dict[str, Any]:
    """Run the full benchmark and return structured results.

    Args:
        queries: Override the default query corpus.
        model: Ollama model to use.
        rlm_config: RLM configuration (defaults to RLMConfig()).
        max_queries: Limit the number of queries (0 = all).

    Returns:
        Dict with ``single_pass``, ``rlm``, and ``summary`` keys.
    """
    corpus = queries or BENCHMARK_QUERIES
    if max_queries > 0:
        corpus = corpus[:max_queries]

    cfg = rlm_config or RLMConfig()
    single_results: List[SinglePassResult] = []
    rlm_results: List[RLMResult] = []

    for entry in corpus:
        q = entry["query"]
        cat = entry["category"]
        logger.info("Benchmarking: [%s] %s", cat, q[:60])

        sp = await _run_single_pass(q, cat, model)
        single_results.append(sp)

        rlm_r = await _run_rlm_pass(q, cat, model, cfg)
        rlm_results.append(rlm_r)

        logger.info(
            "  single=%.2f (%dms)  rlm=%.2f (%dms, %d reflections)",
            sp.quality_score,
            sp.latency_ms,
            rlm_r.final_quality_score,
            rlm_r.total_latency_ms,
            rlm_r.reflections,
        )

    summary = _compute_summary(single_results, rlm_results)

    return {
        "single_pass": [asdict(r) for r in single_results],
        "rlm": [asdict(r) for r in rlm_results],
        "summary": asdict(summary),
    }


def _compute_summary(
    single: List[SinglePassResult],
    rlm: List[RLMResult],
) -> BenchmarkSummary:
    """Compute aggregate stats from individual results."""
    n = len(single)
    if n == 0:
        return BenchmarkSummary()

    avg_ss = sum(r.quality_score for r in single) / n
    avg_rs = sum(r.final_quality_score for r in rlm) / n
    avg_sl = sum(r.latency_ms for r in single) / n
    avg_rl = sum(r.total_latency_ms for r in rlm) / n
    avg_st = sum(r.response_tokens for r in single) / n
    avg_rt = sum(r.total_response_tokens for r in rlm) / n
    improved = sum(
        1 for s, r in zip(single, rlm) if r.final_quality_score > s.quality_score
    )

    return BenchmarkSummary(
        queries_run=n,
        avg_single_score=round(avg_ss, 3),
        avg_rlm_score=round(avg_rs, 3),
        score_delta=round(avg_rs - avg_ss, 3),
        avg_single_latency_ms=round(avg_sl, 1),
        avg_rlm_latency_ms=round(avg_rl, 1),
        latency_overhead_pct=round(
            ((avg_rl - avg_sl) / avg_sl * 100) if avg_sl > 0 else 0, 1
        ),
        avg_single_tokens=round(avg_st, 1),
        avg_rlm_tokens=round(avg_rt, 1),
        token_overhead_pct=round(
            ((avg_rt - avg_st) / avg_st * 100) if avg_st > 0 else 0, 1
        ),
        rlm_improved_count=improved,
    )


# -----------------------------------------------------------------------
# CLI entry point
# -----------------------------------------------------------------------


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="RLM Benchmark")
    parser.add_argument(
        "--queries",
        type=int,
        default=0,
        help="Max queries (0=all)",
    )
    parser.add_argument(
        "--model",
        default="llama3.2:latest",
        help="Ollama model",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Output JSON file path",
    )

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    async def _main():
        results = await run_benchmark(max_queries=args.queries, model=args.model)
        output = json.dumps(results, indent=2)
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(output)
            logger.info("Results written to %s", args.output)
        else:
            logger.info(output)

    asyncio.run(_main())
