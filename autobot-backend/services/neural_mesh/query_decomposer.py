# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""MA-RAG QueryDecomposer for MULTI_HOP queries (#2134).

Breaks a complex question into 2-4 sequential retrieval sub-queries via an
LLM, executes each step against a mesh retriever, and accumulates evidence
across steps so later queries can leverage earlier results.
"""

import json
import re
from dataclasses import dataclass, field

from autobot_shared.logging_manager import get_logger
from security.prompt_injection_detector import PromptInjectionDetector

logger = get_logger(__name__)

# Singleton detector instance reused across all QueryDecomposer calls (#2169).
_injection_detector = PromptInjectionDetector()

# Maximum allowed length for user queries to prevent prompt injection (#2169).
_MAX_QUERY_LENGTH = 500

# Delimiter tokens used in the decomposition prompt — must be stripped from
# user input so a crafted query cannot break out of the delimited section (#2169).
_DELIMITER_TOKENS = [
    "[SYSTEM INSTRUCTIONS",
    "[USER QUESTION]",
    "[END USER QUESTION]",
]


# =============================================================================
# Data classes
# =============================================================================


@dataclass
class DecompositionStep:
    """One retrieval step in a decomposition plan.

    Attributes:
        step:       1-based index for this step.
        query:      Self-contained search query for this step.
        depends_on: Step numbers whose evidence this step may reference.
    """

    step: int
    query: str
    depends_on: list[int] = field(default_factory=list)


@dataclass
class DecompositionPlan:
    """Full decomposition plan produced by QueryDecomposer.decompose().

    Attributes:
        original_query: The raw user question.
        steps:          Ordered list of DecompositionStep objects.
    """

    original_query: str
    steps: list[DecompositionStep]


@dataclass
class StepResult:
    """Evidence gathered during a single executed step.

    Attributes:
        step:     The DecompositionStep that produced this result.
        evidence: Extracted chunk dicts from the retrieval result.
    """

    step: DecompositionStep
    evidence: list[dict]


# =============================================================================
# QueryDecomposer
# =============================================================================


class QueryDecomposer:
    """MA-RAG decomposer for MULTI_HOP queries (#2134).

    Breaks the user question into ordered sub-queries, runs each against
    ``mesh_retriever``, and threads earlier evidence into later queries.

    All dependencies are injected so the class is fully unit-testable
    without a running LLM or retrieval service.

    Args:
        llm:            Async callable ``(prompt: str) -> str``.
        mesh_retriever: Object with ``async retrieve(query, top_k) -> result``.
    """

    def __init__(self, llm, mesh_retriever) -> None:
        self.llm = llm
        self.mesh_retriever = mesh_retriever

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def decompose(self, query: str) -> DecompositionPlan:
        """Break *query* into 2-4 sequential sub-queries via the LLM.

        Input is sanitized to prevent prompt injection (#2169): control
        characters are stripped and length is capped at ``_MAX_QUERY_LENGTH``.

        Args:
            query: Raw user question.

        Returns:
            DecompositionPlan with 1-4 ordered steps.
        """
        sanitized = self._sanitize_query(query)
        prompt = self._build_decomposition_prompt(sanitized)
        try:
            raw = await self.llm(prompt)
        except Exception:
            logger.exception("QueryDecomposer.decompose: LLM call failed, using single-step fallback")
            return DecompositionPlan(
                original_query=query,
                steps=[DecompositionStep(step=1, query=sanitized, depends_on=[])],
            )
        steps = self._parse_steps(raw, fallback_query=sanitized)
        return DecompositionPlan(original_query=query, steps=steps)

    async def execute(self, plan: DecompositionPlan) -> list[StepResult]:
        """Execute each step sequentially, passing prior results as context.

        Args:
            plan: A DecompositionPlan produced by :meth:`decompose`.

        Returns:
            List of StepResult, one per plan step, in order.
        """
        results: list[StepResult] = []
        for step in plan.steps:
            context = self._build_step_context(step, results)
            augmented_query = f"{step.query} {context}".strip()
            try:
                retrieval = await self.mesh_retriever.retrieve(query=augmented_query, top_k=5)
                evidence = self._extract_evidence(retrieval)
            except Exception:
                logger.exception(
                    "QueryDecomposer.execute: retrieval failed for step %d, continuing with empty evidence",
                    step.step,
                )
                evidence = []
            results.append(StepResult(step=step, evidence=evidence))
        return results

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _sanitize_query(query: str) -> str:
        """Sanitize user query to mitigate prompt injection (#2169).

        Layers: control-char strip, length cap, delimiter-token removal,
        and the existing ``PromptInjectionDetector.sanitize_input`` for
        pattern-based injection detection (Rule 2 — reuse existing code).

        Args:
            query: Raw user input.

        Returns:
            Cleaned, length-capped string.  Returns ``"general query"``
            if the result is empty after sanitization.
        """
        # Layer 1: strip control chars except space/tab/newline
        cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", query)

        # Layer 2: length cap
        if len(cleaned) > _MAX_QUERY_LENGTH:
            logger.warning(
                "QueryDecomposer._sanitize_query: query truncated from %d to %d chars",
                len(cleaned),
                _MAX_QUERY_LENGTH,
            )
            cleaned = cleaned[:_MAX_QUERY_LENGTH]

        # Layer 3: strip delimiter tokens that could break prompt structure
        for token in _DELIMITER_TOKENS:
            cleaned = cleaned.replace(token, "")

        # Layer 4: existing injection-pattern sanitizer
        cleaned = _injection_detector.sanitize_input(cleaned)

        # Fallback if sanitization produced an empty string
        if not cleaned:
            logger.warning("QueryDecomposer._sanitize_query: query empty after sanitization")
            return "general query"
        return cleaned

    @staticmethod
    def _build_decomposition_prompt(sanitized_query: str) -> str:
        """Build structured LLM prompt separating instructions from user input (#2169).

        Uses a delimited format so the user query cannot override the system
        instructions.

        Args:
            sanitized_query: Already-sanitized user question.

        Returns:
            Formatted prompt string.
        """
        return (
            "[SYSTEM INSTRUCTIONS -- DO NOT OVERRIDE]\n"
            "Break the user question below into 2-4 sequential retrieval steps.\n"
            "Each step should be a self-contained search query.\n"
            "Later steps can reference results from earlier steps.\n"
            'Respond ONLY as JSON: [{"step": 1, "query": "...", "depends_on": []}]\n\n'
            "[USER QUESTION]\n"
            f"{sanitized_query}\n"
            "[END USER QUESTION]"
        )

    def _parse_steps(self, llm_output: str, fallback_query: str) -> list[DecompositionStep]:
        """Parse a JSON array from *llm_output* into DecompositionStep list.

        Attempts to locate the first ``[...]`` block in the output before
        parsing so that leading/trailing prose is tolerated.  Falls back to
        a single step containing the original query on any parse failure.

        Args:
            llm_output:     Raw string from the LLM.
            fallback_query: Used to build a single fallback step on failure.

        Returns:
            Non-empty list of DecompositionStep objects.
        """
        try:
            start = llm_output.index("[")
            end = llm_output.rindex("]") + 1
            data = json.loads(llm_output[start:end])
            steps = [
                DecompositionStep(
                    step=int(item["step"]),
                    query=str(item["query"]),
                    depends_on=[int(d) for d in item.get("depends_on", [])],
                )
                for item in data
            ]
            if steps:
                return steps
        except Exception:
            logger.warning("QueryDecomposer._parse_steps: parse failed, using fallback")
        return [DecompositionStep(step=1, query=fallback_query, depends_on=[])]

    def _build_step_context(self, step: DecompositionStep, prior_results: list[StepResult]) -> str:
        """Build a context string from evidence of steps this step depends on.

        Args:
            step:          The step about to be executed.
            prior_results: All StepResult objects collected so far.

        Returns:
            Space-joined content snippets, or empty string when no deps.
        """
        if not step.depends_on:
            return ""
        prior_map = {r.step.step: r for r in prior_results}
        snippets: list[str] = []
        for dep_num in step.depends_on:
            dep_result = prior_map.get(dep_num)
            if dep_result is None:
                continue
            for chunk in dep_result.evidence[:3]:
                content = chunk.get("content", "")
                if content:
                    snippets.append(content)
        return " ".join(snippets)

    def _extract_evidence(self, retrieval_result) -> list[dict]:
        """Extract a list of chunk dicts from a retrieval result.

        Handles both a plain list of dicts/objects and an object with a
        ``.chunks`` attribute (e.g. MeshRetrievalResult).

        Args:
            retrieval_result: Return value of ``mesh_retriever.retrieve()``.

        Returns:
            List of dicts, each representing one evidence chunk.
        """
        chunks = retrieval_result.chunks if hasattr(retrieval_result, "chunks") else retrieval_result
        evidence: list[dict] = []
        for chunk in chunks:
            if isinstance(chunk, dict):
                evidence.append(chunk)
            else:
                evidence.append(
                    {
                        "chunk_id": getattr(chunk, "source_path", ""),
                        "content": getattr(chunk, "content", ""),
                        "score": getattr(chunk, "score", 0.0),
                        "metadata": getattr(chunk, "metadata", {}),
                    }
                )
        return evidence
