# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Response Quality Evaluator — core RLM primitive.

The evaluator asks the LLM to judge its own response against the
original user query, producing a quality score and critique.  When
the score falls below the configured threshold the graph loops back
to generate_response with the critique as a refinement hint.

Issue #1373: Initial RLM prototype.
"""

from autobot_shared.logging_manager import get_logger
from rlm.types import ReflectionResult, ReflectionVerdict, RLMConfig

logger = get_logger(__name__)

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

    def __init__(self, config: RLMConfig | None = None):
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
            # #6697: previous log claimed "accepting response" while returning
            # verdict=FAIL with empty exception text when exc.__str__ was
            # empty (e.g. ConnectionError()). Now log type+repr+traceback and
            # use INDETERMINATE so callers can tell evaluator-broke from a
            # genuine FAIL. Routing semantics unchanged (graph only branches
            # on REFINE; INDETERMINATE falls through to accept like ACCEPT).
            logger.warning(
                "RLM evaluator failed (%s: %r) — passing through with INDETERMINATE verdict",
                type(exc).__name__,
                exc,
                exc_info=True,
            )
            return ReflectionResult(
                verdict=ReflectionVerdict.INDETERMINATE,
                quality_score=0.7,
                critique=f"Evaluation error ({type(exc).__name__}): {exc!r}",
                iteration=iteration,
            )

    # ------------------------------------------------------------------
    # LLM transport
    # ------------------------------------------------------------------

    async def _call_llm(self, prompt: str) -> str:
        """Send *prompt* to Ollama and return the raw text response."""
        from autobot_shared.ssot_config import get_config
        from llm_shared.ollama_helpers import call_ollama_generate

        ssot = get_config()
        return await call_ollama_generate(
            prompt=prompt,
            model=self.config.model,
            base_url=ssot.ollama_url,
            temperature=self.config.temperature,
            max_tokens=self.config.max_eval_tokens,
            timeout_ms=self.config.timeout_ms,
        )

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
