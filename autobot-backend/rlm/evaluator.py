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
from llm_shared.validated_llm import Completer, complete_validated
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
Return a JSON object with `score` (0.0-1.0), `critique` (one paragraph on the
deficiencies, empty when the score is high) and `hint` (one sentence on what
the next attempt should focus on, empty when the score is high).
"""


#: JSON Schema the evaluator reply must satisfy (#17307).
#: ``_extract_float`` used to return ``0.5`` when the SCORE line was missing,
#: and that number was compared against ``quality_threshold`` -- the same "a
#: parse miss decides by arithmetic" defect #17306 found in the pre-action
#: verifier. An unreadable reply now retries against this schema and then
#: fails into the INDETERMINATE path, which already exists to mean "the
#: evaluator broke" rather than "the response scored 0.5".
_EVAL_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "score": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "critique": {"type": "string"},
        "hint": {"type": "string"},
    },
    "required": ["score"],
}


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
            payload = await complete_validated(
                "",
                prompt,
                _EVAL_SCHEMA,
                completer=self._completer(),
                label="rlm.evaluator",
            )
            data = payload if isinstance(payload, dict) else payload.model_dump()
            return self._result_from_payload(data, iteration)
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

    def _completer(self) -> Completer:
        """Return the completer the validated loop calls (#17307).

        The transport is unchanged -- a direct local Ollama call, not
        ``llm_service``, because this evaluator is deliberately local and
        cheap. The loop only adds the retry and the schema check around it.
        """

        async def _complete(system_prompt: str, user_prompt: str) -> str:
            combined = f"{system_prompt}\n\n{user_prompt}" if system_prompt else user_prompt
            return await self._call_llm(combined)

        return _complete

    def _result_from_payload(self, payload: dict, iteration: int) -> ReflectionResult:
        """Turn a schema-valid evaluator reply into a ReflectionResult.

        ``score`` is required by the schema, so the threshold compare below
        always acts on a number the evaluator actually produced.
        """
        score = max(0.0, min(1.0, float(payload["score"])))
        critique = str(payload.get("critique") or "").strip()
        hint = str(payload.get("hint") or "").strip()
        if critique.lower() == "none":
            critique = ""
        if hint.lower() == "none":
            hint = ""

        verdict = ReflectionVerdict.ACCEPT if score >= self.config.quality_threshold else ReflectionVerdict.REFINE
        return ReflectionResult(
            verdict=verdict,
            quality_score=score,
            critique=critique,
            refinement_hint=hint,
            iteration=iteration,
        )
