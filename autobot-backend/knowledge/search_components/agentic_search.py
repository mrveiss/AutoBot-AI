# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Agentic RAG Search — exposes knowledge retrieval as a first-class LLM tool.

Issue #1718: Adds three new capabilities on top of RAGService.advanced_search():

1. knowledge_search_tool()  — thin callable wrapper that the chat agent can
   invoke as a named tool, returning plain-text context from the knowledge base.

2. rewrite_query()          — asks the LLM to rephrase the user's query for
   better semantic retrieval before the first search pass.

3. iterative_search()       — runs up to AgenticSearchConfig.max_search_iterations
   search rounds, evaluating context sufficiency after each pass and refining
   the query when the context is still INSUFFICIENT.

AgenticSearchConfig is intentionally a thin dataclass; the three agentic feature
flags (enable_agentic_search, rewrite_enabled, max_search_iterations) are
mirrored onto RAGConfig so callers can toggle them through the existing
get_rag_config() / update_rag_config() surface.

LLM transport follows the pattern established by rlm/evaluator.py: httpx
against ssot_config.ollama_url with a configurable timeout.
"""

import threading
from dataclasses import dataclass, field
from typing import Any, List, Tuple

from autobot_shared.logging_manager import get_logger
from services.context_sufficiency import (
    SufficiencyVerdict,
    get_context_sufficiency_evaluator,
)

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_REWRITE_PROMPT = """\
You are a search query optimizer for a technical knowledge base.

Rewrite the ORIGINAL QUERY below so that it retrieves the most relevant \
documents from a vector store.  Use precise technical terminology, expand \
abbreviations, and remove conversational filler.

## ORIGINAL QUERY
{query}

## CONVERSATION CONTEXT (last 2 turns, may be empty)
{context}

## Instructions
Reply with ONLY the rewritten query — no explanation, no quotes, no prefix.
"""

_SUFFICIENCY_THRESHOLD = 0.5  # hybrid_score floor to consider a result useful


def _get_default_agentic_model() -> str:
    """Return the configured default LLM model, falling back to llama3.2:latest.

    Reads AUTOBOT_DEFAULT_LLM_MODEL via ssot_config so that the model used for
    query rewriting honours the centrally configured model rather than a
    hardcoded string (Issue #5958).
    """
    try:
        from autobot_shared.ssot_config import get_config

        return get_config().llm.default_model
    except Exception:
        return "llama3.2:latest"


@dataclass
class AgenticSearchConfig:
    """Configuration knobs for the agentic search layer.

    These values are initialised from RAGConfig when RAGService creates an
    AgenticSearchTool, so callers can drive them through the existing
    update_rag_config() surface.

    Attributes:
        enable_agentic_search:  Master switch.  When False, knowledge_search_tool
                                delegates directly to RAGService.advanced_search().
        rewrite_enabled:        Whether to ask the LLM to rewrite the query before
                                the first retrieval pass.
        max_search_iterations:  Hard ceiling on iterative refinement rounds.
        model:                  Ollama model used for query rewriting.
        temperature:            Sampling temperature for the rewrite LLM call.
        timeout_ms:             Per-call timeout in milliseconds.
        max_rewrite_tokens:     Token budget for the rewritten query response.
    """

    enable_agentic_search: bool = True
    rewrite_enabled: bool = True
    max_search_iterations: int = 3
    model: str = field(default_factory=lambda: _get_default_agentic_model())
    temperature: float = 0.2
    timeout_ms: int = 8000
    max_rewrite_tokens: int = 128


# ---------------------------------------------------------------------------
# Core implementation
# ---------------------------------------------------------------------------


class AgenticSearchTool:
    """Wraps RAGService.advanced_search() with query rewriting and iterative retrieval.

    Issue #1718: Designed to be registered as an LLM-callable tool in the
    chat workflow graph.  The chat agent can invoke knowledge_search() by name
    and receive a plain-text context block suitable for injection into a prompt.
    """

    def __init__(self, rag_service: Any, config: AgenticSearchConfig | None = None):
        """Initialise the agentic search tool.

        Args:
            rag_service:  RAGService instance (provides advanced_search()).
            config:       Optional AgenticSearchConfig; uses defaults when omitted.
        """
        self.rag_service = rag_service
        self.config = config or AgenticSearchConfig()

    # ------------------------------------------------------------------
    # Public tool entry point
    # ------------------------------------------------------------------

    async def knowledge_search(
        self,
        query: str,
        *,
        max_results: int = 5,
        context: str | None = None,
        categories: List[str] | None = None,
    ) -> str:
        """Search the knowledge base and return plain-text context.

        This is the callable exposed as an LLM tool.  It handles the full
        agentic pipeline: optional query rewriting → iterative retrieval →
        context assembly.

        Args:
            query:        Raw user or agent query.
            max_results:  Maximum results to retrieve per search pass.
            context:      Optional conversation context for query rewriting.
            categories:   Optional knowledge-base category filter list.

        Returns:
            Plain-text string of assembled context passages, or an empty
            string when no relevant content is found.
        """
        if not self.config.enable_agentic_search:
            return await self._simple_search(query, max_results, categories)

        effective_query = query
        if self.config.rewrite_enabled:
            effective_query = await self.rewrite_query(query, context or "")

        results, _ = await self.iterative_search(
            effective_query,
            max_results=max_results,
            categories=categories,
        )
        return self._format_results(results)

    # ------------------------------------------------------------------
    # Query rewriting
    # ------------------------------------------------------------------

    async def rewrite_query(self, original_query: str, context: str = "") -> str:
        """Rewrite *original_query* using an LLM for better semantic retrieval.

        Issue #1718: Calls the configured Ollama model with a structured prompt.
        Falls back to the original query on any transport or parsing error so
        that retrieval is never blocked by the rewriter.

        Args:
            original_query: The user's raw query string.
            context:        Optional recent conversation turns (plain text).

        Returns:
            Rewritten query string, or *original_query* on failure.
        """
        if not original_query or not original_query.strip():
            return original_query

        prompt = _REWRITE_PROMPT.format(
            query=original_query.strip(),
            context=context.strip() if context else "(none)",
        )

        try:
            rewritten = await self._call_llm(prompt)
            rewritten = rewritten.strip()
            if not rewritten:
                logger.warning("LLM returned empty rewrite; using original query")
                return original_query
            logger.debug("Query rewritten: %r -> %r", original_query[:80], rewritten[:80])
            return rewritten
        except Exception as exc:
            logger.warning("Query rewrite failed (%s); using original query", exc)
            return original_query

    # ------------------------------------------------------------------
    # Iterative retrieval
    # ------------------------------------------------------------------

    async def iterative_search(
        self,
        query: str,
        *,
        max_results: int = 5,
        categories: List[str] | None = None,
    ) -> Tuple[list, dict]:
        """Run up to max_search_iterations search rounds with sufficiency checking.

        Issue #1718: After each pass the context sufficiency evaluator decides
        whether the retrieved content is SUFFICIENT.  When it is not and there
        are iterations remaining, the query is rewritten with additional context
        from the current results before the next pass.

        Args:
            query:       Starting query (possibly already rewritten).
            max_results: Maximum results to retrieve per pass.
            categories:  Optional knowledge-base category filter.

        Returns:
            Tuple of (final_results_list, metrics_dict).  Metrics contains:
              - iterations_run (int)
              - queries_used (list[str])
              - final_sufficient (bool)
        """
        evaluator = get_context_sufficiency_evaluator()
        current_query = query
        best_results: list = []
        queries_used: List[str] = [query]
        max_iter = max(1, self.config.max_search_iterations)

        for iteration in range(1, max_iter + 1):
            results, _ = await self.rag_service.advanced_search(
                current_query,
                max_results=max_results,
                categories=categories,
            )

            logger.debug(
                "Agentic search iteration %d/%d: query=%r results=%d",
                iteration,
                max_iter,
                current_query[:80],
                len(results),
            )

            if results:
                best_results = results

            context_text = self._format_results(results)
            check = await evaluator.evaluate(query, context_text)

            if check.verdict != SufficiencyVerdict.INSUFFICIENT:
                logger.info(
                    "Agentic search satisfied in %d iteration(s): verdict=%s",
                    iteration,
                    check.verdict.name,
                )
                return best_results, {
                    "iterations_run": iteration,
                    "queries_used": queries_used,
                    "final_sufficient": True,
                }

            if iteration < max_iter:
                current_query = await self._refine_query(query, current_query, context_text)
                queries_used.append(current_query)

        logger.info(
            "Agentic search exhausted %d iteration(s); returning best results (%d)",
            max_iter,
            len(best_results),
        )
        return best_results, {
            "iterations_run": max_iter,
            "queries_used": queries_used,
            "final_sufficient": False,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _simple_search(
        self,
        query: str,
        max_results: int,
        categories: List[str] | None,
    ) -> str:
        """Direct pass-through to RAGService when agentic search is disabled."""
        results, _ = await self.rag_service.advanced_search(
            query,
            max_results=max_results,
            categories=categories,
        )
        return self._format_results(results)

    async def _refine_query(
        self,
        original_query: str,
        previous_query: str,
        partial_context: str,
    ) -> str:
        """Produce a refined query incorporating partial context clues.

        Issue #1718: Called between iterations when retrieved context was
        INSUFFICIENT.  Asks the LLM to identify what is still missing and
        phrase a more targeted follow-up query.

        Args:
            original_query:  The user's original, unchanged query.
            previous_query:  The query used in the just-completed iteration.
            partial_context: Assembled context text from the last results.

        Returns:
            A new query string, or *previous_query* on LLM failure.
        """
        _REFINE_PROMPT = (
            "The following knowledge-base search was INSUFFICIENT.\n\n"
            "ORIGINAL USER QUESTION:\n{original}\n\n"
            "LAST QUERY USED:\n{previous}\n\n"
            "PARTIAL CONTEXT RETRIEVED (may be incomplete or empty):\n{context}\n\n"
            "Write ONE improved search query that targets the information still missing.\n"
            "Reply with ONLY the query — no explanation."
        )
        prompt = _REFINE_PROMPT.format(
            original=original_query.strip(),
            previous=previous_query.strip(),
            context=(partial_context[:800] if partial_context else "(none)"),
        )
        try:
            refined = await self._call_llm(prompt)
            refined = refined.strip()
            if not refined:
                return previous_query
            logger.debug("Refined query: %r -> %r", previous_query[:80], refined[:80])
            return refined
        except Exception as exc:
            logger.warning("Query refinement failed (%s); reusing previous query", exc)
            return previous_query

    async def _call_llm(self, prompt: str) -> str:
        """Send *prompt* to Ollama and return the raw response text.

        Delegates to the shared ``call_ollama_generate`` transport
        (Issue #5102).
        """
        from autobot_shared.ssot_config import get_config
        from llm_shared.ollama_helpers import call_ollama_generate

        ssot = get_config()
        return await call_ollama_generate(
            prompt=prompt,
            model=self.config.model,
            base_url=ssot.ollama_url,
            temperature=self.config.temperature,
            max_tokens=self.config.max_rewrite_tokens,
            timeout_ms=self.config.timeout_ms,
        )

    @staticmethod
    def _format_results(results: list) -> str:
        """Format SearchResult list into a plain-text context block.

        Each result is separated by a blank line.  The source path (when
        available in metadata) is included so the LLM can cite sources.
        """
        if not results:
            return ""

        parts: List[str] = []
        for i, r in enumerate(results, start=1):
            source = ""
            if hasattr(r, "source_path") and r.source_path:
                source = f" [{r.source_path}]"
            elif hasattr(r, "metadata") and isinstance(r.metadata, dict):
                source = f" [{r.metadata.get('source', r.metadata.get('source_path', ''))}]"
            content = r.content if hasattr(r, "content") else str(r)
            parts.append(f"[{i}]{source}\n{content}")

        return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Module-level singleton (thread-safe)
# ---------------------------------------------------------------------------

_agentic_tool: AgenticSearchTool | None = None
_agentic_tool_lock = threading.Lock()


def get_agentic_search_tool(
    rag_service: Any,
    config: AgenticSearchConfig | None = None,
) -> AgenticSearchTool:
    """Return (or create) the shared AgenticSearchTool singleton.

    Issue #1718: Mirrors the singleton pattern from query_processor.py and
    retrieval_learner.py.  A new instance is created when *rag_service* is
    provided for the first time; subsequent calls with a different instance
    replace the singleton so service re-initialisation is reflected.

    Args:
        rag_service: RAGService instance.
        config:      Optional AgenticSearchConfig override.

    Returns:
        AgenticSearchTool singleton.
    """
    global _agentic_tool

    if _agentic_tool is None or (_agentic_tool.rag_service is not rag_service):
        with _agentic_tool_lock:
            if _agentic_tool is None or (_agentic_tool.rag_service is not rag_service):
                _agentic_tool = AgenticSearchTool(rag_service, config)
                logger.info(
                    "AgenticSearchTool initialised (agentic=%s)",
                    config or AgenticSearchConfig(),
                )
    return _agentic_tool


async def knowledge_search_tool(
    query: str,
    rag_service: Any,
    *,
    max_results: int = 5,
    context: str | None = None,
    categories: List[str] | None = None,
    config: AgenticSearchConfig | None = None,
) -> str:
    """Module-level callable for registering as an LLM tool in the chat graph.

    Issue #1718: This function is the single entry point that chat_workflow/graph.py
    calls when the agent invokes the "knowledge_search" tool.  It delegates to
    the AgenticSearchTool singleton so there is no per-call initialisation cost.

    Args:
        query:       The query string to search for.
        rag_service: RAGService instance (passed from graph configurable).
        max_results: Maximum results per search pass.
        context:     Optional conversation context for query rewriting.
        categories:  Optional knowledge-base category filter.
        config:      Optional AgenticSearchConfig override.

    Returns:
        Plain-text context string from the knowledge base.
    """
    tool = get_agentic_search_tool(rag_service, config)
    return await tool.knowledge_search(
        query,
        max_results=max_results,
        context=context,
        categories=categories,
    )
