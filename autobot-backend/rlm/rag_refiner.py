# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Adaptive RAG Query Refiner — RLM-driven retrieval refinement.

Instead of relying on fixed synonym expansion, this module uses the LLM
to evaluate whether retrieval results actually answer the query and, if
not, to generate a better search query for the next round.

Issue #1382: Follow-up from #1373.
"""

import logging
from dataclasses import dataclass
from typing import List, Optional

import httpx
from rlm.types import RLMConfig

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------
# Evaluation prompt for retrieval quality
# -----------------------------------------------------------------------

_RETRIEVAL_EVAL_PROMPT = """\
You are a search-quality evaluator.

## Task
The user asked: "{query}"

The search engine returned these results:
{results_text}

## Instructions
1. Do these results contain enough information to answer the query?
2. If NOT, suggest a better search query that would find the missing info.

Reply with EXACTLY this format (no extra text):
RELEVANT: <yes or no>
SCORE: <0.0 to 1.0>
REFINED_QUERY: <better search query, or "none" if results are sufficient>
REASON: <one sentence explaining your assessment>
"""


@dataclass
class RefinementResult:
    """Outcome of one retrieval quality evaluation."""

    is_relevant: bool
    score: float
    refined_query: str
    reason: str


class AdaptiveRAGRefiner:
    """Evaluates retrieval results and generates refined queries.

    Integrates with AdvancedRAGOptimizer as a drop-in enhancement to
    the existing ``_expand_query`` heuristic.
    """

    def __init__(self, config: Optional[RLMConfig] = None):
        self.config = config or RLMConfig(
            max_reflections=2,
            quality_threshold=0.6,
        )

    async def evaluate_results(
        self,
        query: str,
        results: List[dict],
    ) -> RefinementResult:
        """Score retrieval results and optionally suggest a refined query.

        Args:
            query: Original user query.
            results: List of search result dicts (need ``content`` key).

        Returns:
            RefinementResult with relevance flag and optional refined query.
        """
        if not results:
            return RefinementResult(
                is_relevant=False,
                score=0.0,
                refined_query=query,
                reason="No results returned",
            )

        results_text = self._format_results(results)
        prompt = _RETRIEVAL_EVAL_PROMPT.format(query=query, results_text=results_text)

        try:
            raw = await self._call_llm(prompt)
            return self._parse(raw)
        except Exception as exc:
            logger.warning(
                "RAG refiner evaluation failed: %s — keeping original query",
                exc,
            )
            return RefinementResult(
                is_relevant=True,
                score=0.5,
                refined_query="none",
                reason=f"Evaluation error: {exc}",
            )

    async def adaptive_refine(
        self,
        query: str,
        search_fn,
        max_rounds: int = 0,
    ) -> tuple:
        """Iteratively refine a query until results are satisfactory.

        Args:
            query: Original user query.
            search_fn: Async callable(query) -> List[SearchResult].
            max_rounds: Override max refinement rounds (0 = use config).

        Returns:
            (final_results, refinement_history) tuple.
        """
        rounds = max_rounds or self.config.max_reflections
        history: List[dict] = []
        current_query = query

        for i in range(rounds + 1):
            results = await search_fn(current_query)

            result_dicts = [{"content": getattr(r, "content", str(r))} for r in results]
            evaluation = await self.evaluate_results(current_query, result_dicts)

            history.append(
                {
                    "round": i + 1,
                    "query": current_query,
                    "result_count": len(results),
                    "score": evaluation.score,
                    "is_relevant": evaluation.is_relevant,
                    "refined_query": evaluation.refined_query,
                    "reason": evaluation.reason,
                }
            )

            logger.info(
                "RAG refine round %d: score=%.2f relevant=%s query='%s'",
                i + 1,
                evaluation.score,
                evaluation.is_relevant,
                current_query[:60],
            )

            if evaluation.is_relevant:
                break

            if evaluation.refined_query and evaluation.refined_query.lower() != "none":
                current_query = evaluation.refined_query
            else:
                break

        return results, history

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _format_results(results: List[dict], max_items: int = 5) -> str:
        """Format results for the evaluation prompt."""
        lines = []
        for i, r in enumerate(results[:max_items], 1):
            content = r.get("content", "")[:300]
            lines.append(f"[{i}] {content}")
        return "\n".join(lines)

    async def _call_llm(self, prompt: str) -> str:
        """Send prompt to Ollama."""
        from autobot_shared.ssot_config import get_config

        ssot = get_config()
        url = f"{ssot.ollama_url}/api/generate"
        timeout = self.config.timeout_ms / 1000

        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                url,
                json={
                    "model": self.config.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": self.config.temperature,
                        "num_predict": self.config.max_eval_tokens,
                    },
                },
            )
            resp.raise_for_status()
            return resp.json().get("response", "")

    @staticmethod
    def _parse(raw: str) -> RefinementResult:
        """Parse the four-line evaluator output."""
        is_relevant = True
        score = 0.5
        refined_query = "none"
        reason = ""

        for line in raw.splitlines():
            stripped = line.strip()
            upper = stripped.upper()

            if upper.startswith("RELEVANT:"):
                val = stripped[len("RELEVANT:") :].strip().lower()
                is_relevant = val in ("yes", "true", "1")

            elif upper.startswith("SCORE:"):
                try:
                    score = max(
                        0.0,
                        min(1.0, float(stripped[len("SCORE:") :].strip())),
                    )
                except ValueError:
                    pass

            elif upper.startswith("REFINED_QUERY:"):
                refined_query = stripped[len("REFINED_QUERY:") :].strip()

            elif upper.startswith("REASON:"):
                reason = stripped[len("REASON:") :].strip()

        return RefinementResult(
            is_relevant=is_relevant,
            score=score,
            refined_query=refined_query,
            reason=reason,
        )
