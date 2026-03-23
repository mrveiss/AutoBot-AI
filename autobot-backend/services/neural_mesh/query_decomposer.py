# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""MA-RAG QueryDecomposer for MULTI_HOP queries (#2134).

Breaks a complex question into 2-4 sequential retrieval sub-queries via an
LLM, executes each step against a mesh retriever, and accumulates evidence
across steps so later queries can leverage earlier results.
"""
import json
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


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

        Args:
            query: Raw user question.

        Returns:
            DecompositionPlan with 1-4 ordered steps.
        """
        prompt = (
            "Break this question into 2-4 sequential retrieval steps.\n"
            "Each step should be a self-contained search query.\n"
            "Later steps can reference results from earlier steps.\n\n"
            f"Question: {query}\n\n"
            'Respond as JSON: [{"step": 1, "query": "...", "depends_on": []}]'
        )
        raw = await self.llm(prompt)
        steps = self._parse_steps(raw, fallback_query=query)
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
            retrieval = await self.mesh_retriever.retrieve(
                query=augmented_query, top_k=5
            )
            evidence = self._extract_evidence(retrieval)
            results.append(StepResult(step=step, evidence=evidence))
        return results

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _parse_steps(
        self, llm_output: str, fallback_query: str
    ) -> list[DecompositionStep]:
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

    def _build_step_context(
        self, step: DecompositionStep, prior_results: list[StepResult]
    ) -> str:
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
        chunks = (
            retrieval_result.chunks
            if hasattr(retrieval_result, "chunks")
            else retrieval_result
        )
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
