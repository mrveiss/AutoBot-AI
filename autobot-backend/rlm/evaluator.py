# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Response Quality Evaluator — core RLM primitive.

The evaluator asks the LLM to judge its own response against the
original user query, producing a quality score and critique.  When
the score falls below the configured threshold the graph loops back
to generate_response with the critique as a refinement hint.

Issue #1373: Initial RLM prototype.
"""

import logging
from typing import Optional

import httpx
from rlm.types import ReflectionResult, ReflectionVerdict, RLMConfig

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------
# Evaluation prompt
# -----------------------------------------------------------------------

_EVAL_PROMPT = """\
You are an impartial response-quality evaluator.

## Task
Given the USER QUERY and the ASSISTANT RESPONSE below, evaluate \
whether the response adequately answers the query.

## Scoring (0.0 – 1.0)
- 1.0 = comprehensive, accurate, well-structured
- 0.7 = acceptable but could be improved
- 0.4 = partially answers, significant gaps
- 0.0 = irrelevant or harmful

## USER QUERY
{query}

## ASSISTANT RESPONSE
{response}

## Instructions
Reply with EXACTLY this format (no extra text):
SCORE: <float>
CRITIQUE: <one paragraph explaining deficiencies, or "None" if score >= 0.7>
HINT: <one sentence suggesting what the next attempt should focus on, \
or "None" if score >= 0.7>
"""


class ResponseQualityEvaluator:
    """Evaluates LLM responses and decides whether to recurse.

    Uses a lightweight LLM call to score the response.  The evaluator
    is intentionally simple — it parses a fixed three-line format so
    that even small models can produce valid output.
    """

    def __init__(self, config: Optional[RLMConfig] = None):
        self.config = config or RLMConfig()

    async def evaluate(
        self,
        query: str,
        response: str,
        iteration: int = 1,
    ) -> ReflectionResult:
        """Score *response* against *query* and return a verdict.

        Args:
            query: The original user message.
            response: The LLM-generated answer to evaluate.
            iteration: Current reflection pass (1-based).

        Returns:
            ReflectionResult with verdict, score, and optional critique.
        """
        if not response or not response.strip():
            return ReflectionResult(
                verdict=ReflectionVerdict.REFINE,
                quality_score=0.0,
                critique="Empty response",
                refinement_hint="Generate a substantive answer.",
                iteration=iteration,
            )

        prompt = _EVAL_PROMPT.format(query=query, response=response)

        try:
            raw = await self._call_llm(prompt)
            return self._parse(raw, iteration)
        except Exception as exc:
            logger.warning("RLM evaluator failed: %s — accepting response", exc)
            return ReflectionResult(
                verdict=ReflectionVerdict.FAIL,
                quality_score=0.7,
                critique=f"Evaluation error: {exc}",
                iteration=iteration,
            )

    # ------------------------------------------------------------------
    # LLM transport
    # ------------------------------------------------------------------

    async def _call_llm(self, prompt: str) -> str:
        """Send *prompt* to Ollama and return the raw text response."""
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

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    def _parse(self, raw: str, iteration: int) -> ReflectionResult:
        """Parse the three-line evaluator output into a ReflectionResult."""
        score = self._extract_float(raw, "SCORE:")
        critique = self._extract_line(raw, "CRITIQUE:")
        hint = self._extract_line(raw, "HINT:")

        if critique.lower() == "none":
            critique = ""
        if hint.lower() == "none":
            hint = ""

        if score >= self.config.quality_threshold:
            verdict = ReflectionVerdict.ACCEPT
        else:
            verdict = ReflectionVerdict.REFINE

        return ReflectionResult(
            verdict=verdict,
            quality_score=score,
            critique=critique,
            refinement_hint=hint,
            iteration=iteration,
        )

    @staticmethod
    def _extract_float(text: str, prefix: str) -> float:
        """Pull the first float after *prefix* in *text*."""
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.upper().startswith(prefix.upper()):
                value_str = stripped[len(prefix) :].strip()
                try:
                    return max(0.0, min(1.0, float(value_str)))
                except ValueError:
                    pass
        return 0.5  # Safe default when parsing fails

    @staticmethod
    def _extract_line(text: str, prefix: str) -> str:
        """Pull the text after *prefix* on the first matching line."""
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.upper().startswith(prefix.upper()):
                return stripped[len(prefix) :].strip()
        return "None"
