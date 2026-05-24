# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoResearch M2: AutoBot-Orchestrated Loop + Web Search

Issue #2599: Implements the main research orchestration loop.  AutoResearchAgent
drives an iterative cycle of:

  web_search → generate_hypothesis → run_experiment → evaluate → store

The loop runs up to *max_iterations* times and stops early when improvement
plateaus (no gain over the last *plateau_window* iterations) or the
caller requests cancellation.

An ApprovalGate is consulted before applying any improvement that exceeds the
*significant_improvement_threshold* — keeping a human in the loop for large
model changes.

Architecture:
  AutoResearchAgent.run_experiment_loop()
      │
      ├─ _web_search()         ─► arxiv / GitHub via httpx
      ├─ _generate_hypothesis()─► structured ResearchHypothesis
      ├─ _run_experiment()     ─► delegates to ExperimentRunner (M1)
      ├─ _evaluate_results()   ─► ImprovementMetrics
      └─ _should_continue()    ─► bool (plateau / cancellation guard)

ApprovalGate is a lightweight Redis-backed gate; it does NOT replace the
full ApprovalGateService (SQL-backed) — it is intentionally scoped to
autoresearch sessions only.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List

import httpx

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_mixin import AsyncRedisClientMixin
from constants.ttl_constants import TTL_7_DAYS, TTL_24_HOURS

from .config import AutoResearchConfig
from .models import Experiment, ExperimentResult, HyperParams
from .runner import ExperimentRunner
from .store import ExperimentStore

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Research checkpoint types (issue #3291)
_CHECKPOINT_QUERY_PLAN = "query_plan"
_CHECKPOINT_SOURCE_SELECTION = "source_selection"
_CHECKPOINT_DRAFT_CONCLUSIONS = "draft_conclusions"

_ARXIV_SEARCH_URL = "https://export.arxiv.org/api/query"
_GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"
_DEFAULT_HTTP_TIMEOUT = 15.0  # seconds per HTTP request
_PLATEAU_NO_IMPROVEMENT = 0.0  # improvement must be strictly positive to break plateau


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


class SessionStatus(str, Enum):
    """Lifecycle status of an ExperimentSession."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass
class SearchResult:
    """A single result returned by the web-search step."""

    title: str
    url: str
    summary: str
    source: str  # "arxiv" | "github"

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass
class ResearchHypothesis:
    """Structured hypothesis produced from search results."""

    statement: str
    rationale: str
    suggested_hyperparams: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass
class ImprovementMetrics:
    """Metrics describing improvement of one iteration over the baseline."""

    experiment_id: str
    baseline_val_bpb: float | None
    result_val_bpb: float | None
    improvement: float | None  # positive = better (lower bpb)
    improvement_pct: float | None
    state: str

    @property
    def improved(self) -> bool:
        return self.improvement is not None and self.improvement > _PLATEAU_NO_IMPROVEMENT

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass
class ExperimentSession:
    """Top-level record for a single run of AutoResearchAgent."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    topic: str = ""
    max_iterations: int = 5
    status: SessionStatus = SessionStatus.PENDING
    iterations_completed: int = 0
    results: List[ImprovementMetrics] = field(default_factory=list)
    hypotheses: List[ResearchHypothesis] = field(default_factory=list)
    search_results: List[List[SearchResult]] = field(default_factory=list)
    started_at: float | None = None
    completed_at: float | None = None
    error_message: str | None = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "topic": self.topic,
            "max_iterations": self.max_iterations,
            "status": self.status.value,
            "iterations_completed": self.iterations_completed,
            "results": [r.to_dict() for r in self.results],
            "hypotheses": [h.to_dict() for h in self.hypotheses],
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error_message": self.error_message,
        }


# ---------------------------------------------------------------------------
# Research checkpoint types and gate (issue #3291)
# ---------------------------------------------------------------------------


class ResearchCheckpointType(str, Enum):
    """Defined checkpoints within a research session where human input is solicited."""

    QUERY_PLAN = _CHECKPOINT_QUERY_PLAN
    SOURCE_SELECTION = _CHECKPOINT_SOURCE_SELECTION
    DRAFT_CONCLUSIONS = _CHECKPOINT_DRAFT_CONCLUSIONS


class CheckpointDecision(str, Enum):
    """A human's response at a research checkpoint."""

    APPROVED = "approved"
    REDIRECT = "redirect"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


@dataclass
class CheckpointResult:
    """The outcome of a checkpoint pause."""

    decision: CheckpointDecision
    redirect_instructions: str | None = None


class ResearchCheckpointGate(AsyncRedisClientMixin):
    """
    Redis-backed gate that pauses a research session at defined checkpoints
    and waits for a human to approve, redirect, or cancel.

    Three checkpoint types (issue #3291):
      - query_plan: user reviews the query before sources are fetched
      - source_selection: user reviews selected sources before scraping
      - draft_conclusions: user reviews the hypothesis before the experiment runs

    State layout in Redis (TTL = 24 h):
      checkpoint:<session_id>:<cp_type>:context  JSON blob with checkpoint data
      checkpoint:<session_id>:<cp_type>:decision  "pending" | "approved" |
                                                   "redirect:<instructions>" |
                                                   "cancelled"
    """

    _CONTEXT_KEY = "autoresearch:checkpoint:{session_id}:{cp_type}:context"
    _DECISION_KEY = "autoresearch:checkpoint:{session_id}:{cp_type}:decision"
    _TTL = TTL_24_HOURS

    def __init__(self, config: "AutoResearchConfig" | None = None) -> None:
        from .config import AutoResearchConfig as _Cfg

        self.config = config or _Cfg()
        self._redis_database = self.config.redis_database

    def _keys(self, session_id: str, cp_type: str):
        ctx_key = self._CONTEXT_KEY.format(session_id=session_id, cp_type=cp_type)
        dec_key = self._DECISION_KEY.format(session_id=session_id, cp_type=cp_type)
        return ctx_key, dec_key

    async def request(
        self,
        session_id: str,
        cp_type: str,
        context: Dict[str, Any],
    ) -> str:
        """Persist checkpoint data and return the decision key for polling.

        Args:
            session_id: Owning session ID.
            cp_type: One of the ResearchCheckpointType values.
            context: Serialisable dict describing what the human should review.

        Returns:
            Redis decision key.
        """
        ctx_key, dec_key = self._keys(session_id, cp_type)
        redis = await self._get_redis()
        payload = json.dumps(
            {
                "session_id": session_id,
                "checkpoint_type": cp_type,
                "context": context,
                "requested_at": time.time(),
            }
        )
        await redis.set(ctx_key, payload, ex=self._TTL)
        await redis.set(dec_key, "pending", ex=self._TTL)
        logger.info(
            "ResearchCheckpointGate: checkpoint=%s requested for session %s",
            cp_type,
            session_id,
        )
        return dec_key

    async def get_decision(self, session_id: str, cp_type: str) -> str:
        """Return the current raw decision string from Redis."""
        _, dec_key = self._keys(session_id, cp_type)
        redis = await self._get_redis()
        raw = await redis.get(dec_key)
        if raw is None:
            return "unknown"
        return raw if isinstance(raw, str) else raw.decode("utf-8")

    async def wait_for_decision(
        self,
        session_id: str,
        cp_type: str,
        timeout: float,
        poll_interval: float = 5.0,
    ) -> CheckpointResult:
        """Poll until a decision is recorded or timeout fires.

        On timeout the checkpoint auto-proceeds (approved) to avoid blocking
        a session indefinitely.

        Args:
            session_id: Session ID.
            cp_type: Checkpoint type string.
            timeout: Seconds to wait before auto-proceed.
            poll_interval: Seconds between polls.

        Returns:
            CheckpointResult with the final decision and optional redirect text.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            raw = await self.get_decision(session_id, cp_type)
            if raw == "approved":
                return CheckpointResult(decision=CheckpointDecision.APPROVED)
            if raw == "cancelled":
                return CheckpointResult(decision=CheckpointDecision.CANCELLED)
            if raw.startswith("redirect:"):
                instructions = raw[len("redirect:") :]
                return CheckpointResult(
                    decision=CheckpointDecision.REDIRECT,
                    redirect_instructions=instructions or None,
                )
            await asyncio.sleep(poll_interval)

        logger.info(
            "ResearchCheckpointGate: checkpoint=%s session=%s timed out — auto-proceeding",
            cp_type,
            session_id,
        )
        return CheckpointResult(decision=CheckpointDecision.TIMEOUT)


# ---------------------------------------------------------------------------
# ApprovalGate
# ---------------------------------------------------------------------------


class ApprovalGate(AsyncRedisClientMixin):
    """
    Lightweight Redis-backed gate for autoresearch significant improvements.

    Significant improvements (above *threshold*) are held in a Redis key and
    require the human operator to explicitly approve them before the improvement
    is applied to the live baseline.

    Issue #2599: This is intentionally NOT a full DB-backed approval; it is a
    scoped, in-session gate.  Full workflow approvals continue to go through
    ApprovalGateService.
    """

    _PENDING_KEY_TEMPLATE = "autoresearch:approval:pending:{session_id}:{exp_id}"
    _STATUS_KEY_TEMPLATE = "autoresearch:approval:status:{session_id}:{exp_id}"
    _TTL_SECONDS = TTL_24_HOURS

    def __init__(self, config: AutoResearchConfig | None = None) -> None:
        self.config = config or AutoResearchConfig()
        self._redis_database = self.config.redis_database

    def check_approval_needed(self, improvement_pct: float | None, threshold: float) -> bool:
        """Return True when improvement_pct meets or exceeds threshold.

        Args:
            improvement_pct: Percentage improvement over baseline (positive = better).
            threshold: Minimum percentage to require approval.

        Returns:
            True if human approval is required before accepting the improvement.
        """
        if improvement_pct is None:
            return False
        return improvement_pct >= threshold

    async def request_approval(
        self,
        session_id: str,
        experiment_id: str,
        details: Dict[str, Any],
    ) -> str:
        """Persist a pending approval record to Redis and return its status key.

        The approval starts in "pending" state.  External callers (e.g. a UI or
        operator CLI) can write "approved" or "rejected" to the status key.

        Args:
            session_id: ID of the owning ExperimentSession.
            experiment_id: ID of the experiment requiring approval.
            details: Arbitrary context dict stored alongside the request.

        Returns:
            The Redis status key so callers can poll for a decision.
        """
        redis = await self._get_redis()
        pending_key = self._PENDING_KEY_TEMPLATE.format(session_id=session_id, exp_id=experiment_id)
        status_key = self._STATUS_KEY_TEMPLATE.format(session_id=session_id, exp_id=experiment_id)
        payload = json.dumps(
            {
                "session_id": session_id,
                "experiment_id": experiment_id,
                "details": details,
                "requested_at": time.time(),
            }
        )
        await redis.set(pending_key, payload, ex=self._TTL_SECONDS)
        await redis.set(status_key, "pending", ex=self._TTL_SECONDS)
        logger.info(
            "ApprovalGate: approval requested for experiment %s (session %s)",
            experiment_id,
            session_id,
        )
        return status_key

    async def get_approval_status(self, session_id: str, experiment_id: str) -> str:
        """Return current approval status: 'pending', 'approved', or 'rejected'."""
        redis = await self._get_redis()
        status_key = self._STATUS_KEY_TEMPLATE.format(session_id=session_id, exp_id=experiment_id)
        raw = await redis.get(status_key)
        if raw is None:
            return "unknown"
        return raw if isinstance(raw, str) else raw.decode("utf-8")

    async def wait_for_approval(
        self,
        session_id: str,
        experiment_id: str,
        poll_interval: float = 5.0,
        timeout: float = 300.0,
    ) -> str:
        """Poll until approval is granted/rejected or timeout is reached.

        Args:
            session_id: Session ID.
            experiment_id: Experiment ID.
            poll_interval: Seconds between polls.
            timeout: Maximum seconds to wait before returning 'timeout'.

        Returns:
            Final status string: 'approved', 'rejected', or 'timeout'.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status = await self.get_approval_status(session_id, experiment_id)
            if status in ("approved", "rejected"):
                logger.info(
                    "ApprovalGate: experiment %s received status=%s",
                    experiment_id,
                    status,
                )
                return status
            await asyncio.sleep(poll_interval)
        logger.warning(
            "ApprovalGate: timed out waiting for experiment %s approval",
            experiment_id,
        )
        return "timeout"


# ---------------------------------------------------------------------------
# Web search helpers
# ---------------------------------------------------------------------------


async def _search_arxiv(client: httpx.AsyncClient, query: str, max_results: int) -> List[SearchResult]:
    """Query the arXiv Atom API and return structured results.

    Args:
        client: Shared httpx.AsyncClient.
        query: Free-text search query.
        max_results: Maximum number of entries to return.

    Returns:
        List of SearchResult from arXiv, empty on any error.
    """
    params = {
        "search_query": f"all:{query}",
        "start": 0,
        "max_results": max_results,
        "sortBy": "relevance",
        "sortOrder": "descending",
    }
    try:
        response = await client.get(_ARXIV_SEARCH_URL, params=params, timeout=_DEFAULT_HTTP_TIMEOUT)
        response.raise_for_status()
        return _parse_arxiv_atom(response.text)
    except httpx.HTTPError as exc:
        logger.warning("arXiv search failed for query %r: %s", query, exc)
        return []


def _parse_arxiv_atom(xml_text: str) -> List[SearchResult]:
    """Extract title/id/summary from an arXiv Atom response without external XML libs."""
    import re

    results: List[SearchResult] = []
    entries = re.findall(r"<entry>(.*?)</entry>", xml_text, re.DOTALL)
    for entry in entries:
        title_match = re.search(r"<title>(.*?)</title>", entry, re.DOTALL)
        id_match = re.search(r"<id>(.*?)</id>", entry, re.DOTALL)
        summary_match = re.search(r"<summary>(.*?)</summary>", entry, re.DOTALL)
        if not (title_match and id_match):
            continue
        results.append(
            SearchResult(
                title=title_match.group(1).strip(),
                url=id_match.group(1).strip(),
                summary=(summary_match.group(1).strip() if summary_match else ""),
                source="arxiv",
            )
        )
    return results


async def _search_github(client: httpx.AsyncClient, query: str, max_results: int) -> List[SearchResult]:
    """Query the GitHub repository search API and return structured results.

    Args:
        client: Shared httpx.AsyncClient.
        query: Free-text search query.
        max_results: Maximum number of repositories to return.

    Returns:
        List of SearchResult from GitHub, empty on any error.
    """
    params = {
        "q": f"{query} language:python",
        "sort": "stars",
        "order": "desc",
        "per_page": max_results,
    }
    headers = {"Accept": "application/vnd.github+json"}
    try:
        response = await client.get(
            _GITHUB_SEARCH_URL,
            params=params,
            headers=headers,
            timeout=_DEFAULT_HTTP_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        return _parse_github_results(data)
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("GitHub search failed for query %r: %s", query, exc)
        return []


def _parse_github_results(data: Dict[str, Any]) -> List[SearchResult]:
    """Extract repo name/url/description from GitHub search JSON."""
    results: List[SearchResult] = []
    for item in data.get("items", []):
        results.append(
            SearchResult(
                title=item.get("full_name", ""),
                url=item.get("html_url", ""),
                summary=item.get("description") or "",
                source="github",
            )
        )
    return results


# ---------------------------------------------------------------------------
# AutoResearchAgent
# ---------------------------------------------------------------------------


class AutoResearchAgent(AsyncRedisClientMixin):
    """
    Orchestrator for the AutoResearch M2 loop.

    The agent iteratively:
      1. Searches arXiv and GitHub for the current topic
      2. Generates a structured hypothesis from the search results + prior results
      3. Runs a training experiment via ExperimentRunner
      4. Evaluates improvement vs the current baseline
      5. Requests approval when improvement is significant
      6. Stops when improvement plateaus or max_iterations is reached

    All sessions and per-iteration state are persisted to Redis via
    ExperimentStore (M1 infrastructure).

    Issue #2599.
    """

    def __init__(
        self,
        config: AutoResearchConfig | None = None,
        store: ExperimentStore | None = None,
        runner: ExperimentRunner | None = None,
        approval_gate: ApprovalGate | None = None,
        checkpoint_gate: ResearchCheckpointGate | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.config = config or AutoResearchConfig()
        self._redis_database = self.config.redis_database
        self.store = store or ExperimentStore(self.config)
        self.runner = runner or ExperimentRunner(config=self.config, store=self.store)
        self.approval_gate = approval_gate or ApprovalGate(self.config)
        self.checkpoint_gate = checkpoint_gate or ResearchCheckpointGate(self.config)
        self._http_client = http_client
        self._cancel_event: asyncio.Event = asyncio.Event()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run_experiment_loop(
        self,
        topic: str,
        max_iterations: int = 5,
        search_results_per_source: int = 3,
        approval_threshold_pct: float = 5.0,
        plateau_window: int = 3,
    ) -> ExperimentSession:
        """Drive the full research loop for *topic*.

        Args:
            topic: Research topic; used as a search query.
            max_iterations: Maximum number of search→hypothesis→experiment cycles.
            search_results_per_source: How many results to fetch per source per iter.
            approval_threshold_pct: Improvement % above which human approval is needed.
            plateau_window: Stop early after this many consecutive non-improving iters.

        Returns:
            Completed ExperimentSession with all iteration results.
        """
        session = ExperimentSession(
            topic=topic,
            max_iterations=max_iterations,
            status=SessionStatus.RUNNING,
            started_at=time.time(),
        )
        # Only clear the cancel event when it was not already set before entry
        # — a caller that called cancel() before run_experiment_loop() intends
        # for the session to start as cancelled (pre-cancellation pattern).
        already_cancelled = self._cancel_event.is_set()
        if not already_cancelled:
            self._cancel_event.clear()

        logger.info("AutoResearchAgent: starting session %s for topic %r", session.id, topic)
        await self._save_session(session)

        try:
            async with self._build_http_client() as client:
                for iteration in range(1, max_iterations + 1):
                    if self._cancel_event.is_set():
                        logger.info(
                            "AutoResearchAgent: session %s cancelled before iteration %d",
                            session.id,
                            iteration,
                        )
                        session.status = SessionStatus.CANCELLED
                        break

                    logger.info(
                        "AutoResearchAgent: session %s — iteration %d/%d",
                        session.id,
                        iteration,
                        max_iterations,
                    )
                    await self._run_single_iteration(
                        session=session,
                        client=client,
                        iteration=iteration,
                        search_results_per_source=search_results_per_source,
                        approval_threshold_pct=approval_threshold_pct,
                    )
                    session.iterations_completed = iteration
                    await self._save_session(session)

                    if not self._should_continue(session, plateau_window):
                        logger.info(
                            "AutoResearchAgent: session %s stopping early at iteration %d " "(plateau detected)",
                            session.id,
                            iteration,
                        )
                        break

            if session.status == SessionStatus.RUNNING:
                session.status = SessionStatus.COMPLETED
        except Exception as exc:
            session.status = SessionStatus.FAILED
            session.error_message = str(exc)
            logger.exception(
                "AutoResearchAgent: session %s failed with unhandled exception",
                session.id,
            )
        finally:
            session.completed_at = time.time()
            await self._save_session(session)

        logger.info(
            "AutoResearchAgent: session %s finished — status=%s, iterations=%d",
            session.id,
            session.status.value,
            session.iterations_completed,
        )
        return session

    def cancel(self) -> None:
        """Signal the running loop to stop after the current iteration."""
        self._cancel_event.set()

    # ------------------------------------------------------------------
    # Private: per-iteration pipeline
    # ------------------------------------------------------------------

    async def _run_single_iteration(
        self,
        session: ExperimentSession,
        client: httpx.AsyncClient,
        iteration: int,
        search_results_per_source: int,
        approval_threshold_pct: float,
    ) -> None:
        """Execute one full search→hypothesis→experiment→evaluate cycle.

        Mutates *session* in place by appending to results/hypotheses/search_results.

        When checkpoints are enabled (issue #3291), the loop pauses at three
        points and waits for human input:
          1. After the query plan is formed — before sources are fetched.
          2. After sources are selected — before scraping/content enrichment.
          3. After the hypothesis is drafted — before the experiment runs.
        """
        query = session.topic

        # 1a. Checkpoint: query plan — let the user review / redirect the query
        if self.config.checkpoints_enabled:
            result = await self._pause_at_checkpoint(
                session=session,
                cp_type=ResearchCheckpointType.QUERY_PLAN,
                context={
                    "query": query,
                    "iteration": iteration,
                    "description": "Review the search query before fetching sources.",
                },
            )
            if result.decision == CheckpointDecision.CANCELLED:
                session.status = SessionStatus.CANCELLED
                return
            if result.decision == CheckpointDecision.REDIRECT and result.redirect_instructions:
                query = result.redirect_instructions
                logger.info("_run_single_iteration: query redirected by user to: %r", query)

        # 1b. Web search
        search_hits = await self._web_search(
            client=client,
            query=query,
            max_results_per_source=search_results_per_source,
        )
        session.search_results.append(search_hits)

        # 2. Checkpoint: source selection — let the user approve the fetched sources
        if self.config.checkpoints_enabled:
            source_summary = [{"title": r.title, "url": r.url, "source": r.source} for r in search_hits[:10]]
            result = await self._pause_at_checkpoint(
                session=session,
                cp_type=ResearchCheckpointType.SOURCE_SELECTION,
                context={
                    "query": query,
                    "iteration": iteration,
                    "sources": source_summary,
                    "description": "Review selected sources before hypothesis generation.",
                },
            )
            if result.decision == CheckpointDecision.CANCELLED:
                session.status = SessionStatus.CANCELLED
                return
            # Redirect at source selection: apply as a filter hint on the hypothesis
            source_redirect = result.redirect_instructions if result.decision == CheckpointDecision.REDIRECT else None
        else:
            source_redirect = None

        # 3. Generate hypothesis
        hypothesis = self._generate_hypothesis(
            search_results=search_hits,
            prior_results=session.results,
            iteration=iteration,
        )
        if source_redirect:
            hypothesis = ResearchHypothesis(
                statement=f"[User redirect: {source_redirect}] {hypothesis.statement}",
                rationale=hypothesis.rationale,
                suggested_hyperparams=hypothesis.suggested_hyperparams,
                tags=hypothesis.tags,
            )
        session.hypotheses.append(hypothesis)

        # 4. Checkpoint: draft conclusions — let the user review the hypothesis
        if self.config.checkpoints_enabled:
            result = await self._pause_at_checkpoint(
                session=session,
                cp_type=ResearchCheckpointType.DRAFT_CONCLUSIONS,
                context={
                    "iteration": iteration,
                    "hypothesis": hypothesis.to_dict(),
                    "description": "Review the hypothesis before running the experiment.",
                },
            )
            if result.decision == CheckpointDecision.CANCELLED:
                session.status = SessionStatus.CANCELLED
                return
            if result.decision == CheckpointDecision.REDIRECT and result.redirect_instructions:
                hypothesis = ResearchHypothesis(
                    statement=(f"[User override: {result.redirect_instructions}] " f"{hypothesis.statement}"),
                    rationale=hypothesis.rationale,
                    suggested_hyperparams=hypothesis.suggested_hyperparams,
                    tags=hypothesis.tags,
                )
                # Update the hypothesis already appended to the session
                session.hypotheses[-1] = hypothesis

        # 5. Run experiment
        experiment = self._build_experiment(hypothesis, session)
        experiment = await self._run_experiment(experiment)

        # 6. Evaluate
        metrics = self._evaluate_results(experiment)
        session.results.append(metrics)

        # 7. Approval gate for significant improvements
        if metrics.improved and self.approval_gate.check_approval_needed(
            metrics.improvement_pct, approval_threshold_pct
        ):
            await self._handle_approval_gate(session, experiment, metrics)

    # ------------------------------------------------------------------
    # Private: web search
    # ------------------------------------------------------------------

    async def _web_search(
        self,
        client: httpx.AsyncClient,
        query: str,
        max_results_per_source: int = 3,
    ) -> List[SearchResult]:
        """Fetch results from arXiv and GitHub in parallel.

        Args:
            client: Shared httpx.AsyncClient.
            query: Search query derived from the session topic.
            max_results_per_source: Max results per individual source.

        Returns:
            Combined list of SearchResult objects.
        """
        arxiv_task = _search_arxiv(client, query, max_results_per_source)
        github_task = _search_github(client, query, max_results_per_source)
        arxiv_results, github_results = await asyncio.gather(arxiv_task, github_task)
        combined = arxiv_results + github_results
        logger.info(
            "_web_search: query=%r returned %d results (%d arxiv, %d github)",
            query,
            len(combined),
            len(arxiv_results),
            len(github_results),
        )
        return combined

    # ------------------------------------------------------------------
    # Private: hypothesis generation
    # ------------------------------------------------------------------

    def _generate_hypothesis(
        self,
        search_results: List[SearchResult],
        prior_results: List[ImprovementMetrics],
        iteration: int,
    ) -> ResearchHypothesis:
        """Synthesise a hypothesis from search results and prior experiment outcomes.

        The synthesis is rule-based (no LLM call) to keep the loop self-contained.
        A keyword-driven heuristic extracts themes from search summaries and maps
        them to hyperparameter adjustments known to help training quality.

        Args:
            search_results: Results from the current web_search step.
            prior_results: Improvement metrics from previous iterations.
            iteration: Current iteration number (1-based).

        Returns:
            ResearchHypothesis with a statement, rationale, and suggested hyperparams.
        """
        themes = _extract_themes(search_results)
        adjustments = _themes_to_hyperparams(themes, iteration)
        prior_context = _summarise_prior_results(prior_results)

        statement = (
            f"Iteration {iteration}: based on {len(search_results)} search results "
            f"covering themes [{', '.join(themes) or 'general'}], "
            f"adjust hyperparameters to improve val_bpb. {prior_context}"
        )
        rationale = (
            f"Search themes suggest: {', '.join(themes) or 'no specific theme detected'}. "
            f"Applied adjustments: {json.dumps(adjustments)}."
        )
        return ResearchHypothesis(
            statement=statement,
            rationale=rationale,
            suggested_hyperparams=adjustments,
            tags=themes[:5],
        )

    # ------------------------------------------------------------------
    # Private: experiment execution
    # ------------------------------------------------------------------

    def _build_experiment(self, hypothesis: ResearchHypothesis, session: ExperimentSession) -> Experiment:
        """Construct an Experiment from a hypothesis.

        Args:
            hypothesis: The research hypothesis to test.
            session: Parent session (used for tagging).

        Returns:
            Experiment ready to be passed to ExperimentRunner.
        """
        hp = HyperParams()
        known_fields = {f.name for f in dataclasses.fields(HyperParams) if f.name != "extra"}
        extra: Dict[str, Any] = {}
        for key, value in hypothesis.suggested_hyperparams.items():
            if key in known_fields:
                setattr(hp, key, value)
            else:
                extra[key] = value
        hp.extra = extra

        return Experiment(
            hypothesis=hypothesis.statement,
            description=hypothesis.rationale,
            hyperparams=hp,
            tags=hypothesis.tags + [f"session:{session.id}"],
        )

    async def _run_experiment(self, experiment: Experiment) -> Experiment:
        """Delegate to ExperimentRunner (M1) and return the completed experiment.

        Args:
            experiment: Experiment to execute.

        Returns:
            Experiment with result populated.
        """
        logger.info(
            "_run_experiment: launching experiment %s — hypothesis: %s",
            experiment.id,
            experiment.hypothesis[:80],
        )
        return await self.runner.run_experiment(experiment)

    # ------------------------------------------------------------------
    # Private: evaluation
    # ------------------------------------------------------------------

    def _evaluate_results(self, experiment: Experiment) -> ImprovementMetrics:
        """Extract improvement metrics from a completed experiment.

        Args:
            experiment: Completed (or failed) experiment.

        Returns:
            ImprovementMetrics comparing the experiment to baseline.
        """
        result: ExperimentResult | None = experiment.result
        return ImprovementMetrics(
            experiment_id=experiment.id,
            baseline_val_bpb=experiment.baseline_val_bpb,
            result_val_bpb=(result.val_bpb if result else None),
            improvement=experiment.improvement,
            improvement_pct=experiment.improvement_pct,
            state=experiment.state.value,
        )

    # ------------------------------------------------------------------
    # Private: plateau / stop guard
    # ------------------------------------------------------------------

    def _should_continue(self, session: ExperimentSession, plateau_window: int) -> bool:
        """Return True if the loop should continue, False to stop early.

        Stops early when the last *plateau_window* iterations all failed to
        improve over baseline — indicating the search space is exhausted.

        Args:
            session: Current session with results so far.
            plateau_window: Number of consecutive non-improving iterations to trigger stop.

        Returns:
            True if more iterations should run, False if plateau detected.
        """
        results = session.results
        if len(results) < plateau_window:
            return True
        recent = results[-plateau_window:]
        if all(not m.improved for m in recent):
            logger.info(
                "_should_continue: plateau detected — last %d iterations showed no improvement",
                plateau_window,
            )
            return False
        return True

    # ------------------------------------------------------------------
    # Private: approval gate handler
    # ------------------------------------------------------------------

    async def _handle_approval_gate(
        self,
        session: ExperimentSession,
        experiment: Experiment,
        metrics: ImprovementMetrics,
    ) -> None:
        """Request and await human approval for a significant improvement.

        Does NOT block the loop indefinitely — uses the configured timeout in
        ApprovalGate.wait_for_approval.  If timeout or rejection occurs, the
        baseline is NOT updated (which the ExperimentRunner already handles).

        Args:
            session: Parent session.
            experiment: Completed experiment with significant improvement.
            metrics: Improvement metrics for the approval request.
        """
        details: Dict[str, Any] = {
            "topic": session.topic,
            "iteration": session.iterations_completed,
            "metrics": metrics.to_dict(),
            "hypothesis": (session.hypotheses[-1].to_dict() if session.hypotheses else {}),
        }
        status_key = await self.approval_gate.request_approval(
            session_id=session.id,
            experiment_id=experiment.id,
            details=details,
        )
        logger.info(
            "_handle_approval_gate: significant improvement %.2f%% — awaiting approval at %s",
            metrics.improvement_pct,
            status_key,
        )

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
                config=self._get_notification_config(session.id),
            )
        except Exception:
            logger.exception(
                "Failed to send approval notification for experiment %s",
                experiment.id,
            )

        # Non-blocking poll with short timeout so we don't freeze the loop
        decision = await self.approval_gate.wait_for_approval(
            session_id=session.id,
            experiment_id=experiment.id,
            timeout=60.0,
        )
        if decision != "approved":
            logger.info(
                "_handle_approval_gate: experiment %s not approved (decision=%s) — skipping",
                experiment.id,
                decision,
            )

    # ------------------------------------------------------------------
    # Private: research checkpoint handler (issue #3291)
    # ------------------------------------------------------------------

    async def _pause_at_checkpoint(
        self,
        session: ExperimentSession,
        cp_type: ResearchCheckpointType,
        context: Dict[str, Any],
    ) -> CheckpointResult:
        """Pause at a named checkpoint and wait for human input.

        Publishes a WebSocket notification so the frontend can prompt the user.
        Returns the human's decision (approve / redirect / cancel / timeout).
        On timeout, auto-proceeds (treated as approved).

        Args:
            session: Current research session.
            cp_type: Which checkpoint to pause at.
            context: Serialisable dict describing the checkpoint to the user.

        Returns:
            CheckpointResult with the final decision.
        """
        dec_key = await self.checkpoint_gate.request(
            session_id=session.id,
            cp_type=cp_type.value,
            context=context,
        )
        logger.info(
            "_pause_at_checkpoint: session=%s checkpoint=%s — awaiting decision at %s",
            session.id,
            cp_type.value,
            dec_key,
        )

        try:
            from events.bus import PersistStrategy, publish_event

            await publish_event(
                "global",
                event_type="research_checkpoint_pending",
                payload={
                    "session_id": session.id,
                    "checkpoint_type": cp_type.value,
                    "decision_key": dec_key,
                    "context": context,
                    "timeout_seconds": self.config.checkpoint_timeout_seconds,
                },
                persist=PersistStrategy.NONE,
            )
        except Exception:
            logger.warning(
                "_pause_at_checkpoint: failed to publish checkpoint notification " "for session %s checkpoint %s",
                session.id,
                cp_type.value,
                exc_info=True,
            )

        return await self.checkpoint_gate.wait_for_decision(
            session_id=session.id,
            cp_type=cp_type.value,
            timeout=self.config.checkpoint_timeout_seconds,
        )

    def _get_notification_config(self, session_id: str):
        """Return a default notification config for autoresearch approval events.

        Args:
            session_id: The autoresearch session ID used as the workflow ID.

        Returns:
            NotificationConfig scoped to the autoresearch session.
        """
        from services.notification_service import NotificationConfig

        return NotificationConfig(
            workflow_id=f"autoresearch:{session_id}",
            channels={"approval_needed": ["in_app"]},
        )

    # ------------------------------------------------------------------
    # Private: session persistence
    # ------------------------------------------------------------------

    async def _save_session(self, session: ExperimentSession) -> None:
        """Persist an ExperimentSession to Redis.

        Args:
            session: Session to persist.
        """
        try:
            redis = await self._get_redis()
            key = f"autoresearch:session:{session.id}"
            await redis.set(key, json.dumps(session.to_dict()), ex=TTL_7_DAYS)
            await redis.zadd(
                "autoresearch:sessions:timeline",
                {session.id: session.started_at or time.time()},
            )
        except Exception:
            logger.exception("_save_session: failed to persist session %s", session.id)

    # ------------------------------------------------------------------
    # Private: HTTP client lifecycle
    # ------------------------------------------------------------------

    def _build_http_client(self) -> httpx.AsyncClient:
        """Return the injected client or create a temporary one for the loop."""
        if self._http_client is not None:
            # Caller owns lifecycle — wrap in a no-op context manager
            return _NullContextClient(self._http_client)
        return httpx.AsyncClient(timeout=_DEFAULT_HTTP_TIMEOUT)


# ---------------------------------------------------------------------------
# Internal context-manager shim for injected clients
# ---------------------------------------------------------------------------


class _NullContextClient:
    """Wraps an existing httpx.AsyncClient so it can be used as an async context manager
    without closing it — the injecting caller retains ownership."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def __aenter__(self) -> httpx.AsyncClient:
        return self._client

    async def __aexit__(self, *_) -> None:
        pass  # do not close — caller owns the client


# ---------------------------------------------------------------------------
# Hypothesis helpers (pure functions, testable in isolation)
# ---------------------------------------------------------------------------

_THEME_KEYWORDS: Dict[str, List[str]] = {
    "attention": ["attention", "transformer", "self-attention", "multi-head"],
    "regularisation": ["dropout", "regularization", "weight decay", "l2"],
    "learning_rate": ["learning rate", "lr schedule", "warmup", "cosine annealing"],
    "architecture": ["layer", "depth", "width", "embedding", "hidden"],
    "data": ["data augmentation", "tokenization", "dataset", "preprocessing"],
    "batch": ["batch size", "gradient accumulation", "micro-batch"],
}

_THEME_TO_HP_ADJUSTMENTS: Dict[str, Dict[str, Any]] = {
    "attention": {"n_head": 8, "n_embd": 512},
    "regularisation": {"dropout": 0.1, "weight_decay": 0.05},
    "learning_rate": {"learning_rate": 1e-4, "warmup_steps": 200},
    "architecture": {"n_layer": 8, "block_size": 512},
    "data": {"batch_size": 128},
    "batch": {"batch_size": 32},
}


def _extract_themes(search_results: List[SearchResult]) -> List[str]:
    """Identify high-level research themes from a list of search results.

    Args:
        search_results: Web search results for the current iteration.

    Returns:
        Deduplicated list of theme names found in titles/summaries.
    """
    found: List[str] = []
    combined_text = " ".join(f"{r.title} {r.summary}" for r in search_results).lower()
    for theme, keywords in _THEME_KEYWORDS.items():
        if any(kw in combined_text for kw in keywords):
            found.append(theme)
    return found


def _themes_to_hyperparams(themes: List[str], iteration: int) -> Dict[str, Any]:
    """Map detected themes to concrete hyperparameter adjustments.

    Uses modular iteration cycling so successive iterations with the same themes
    still explore a varied parameter space.

    Args:
        themes: Theme names from _extract_themes().
        iteration: Current iteration index (1-based, used for cycling).

    Returns:
        Dict of hyperparameter overrides to apply for the next experiment.
    """
    if not themes:
        # Fallback: cycle through all theme adjustments based on iteration
        all_themes = list(_THEME_TO_HP_ADJUSTMENTS.keys())
        selected_theme = all_themes[(iteration - 1) % len(all_themes)]
        return dict(_THEME_TO_HP_ADJUSTMENTS[selected_theme])

    # Pick the theme that appears earliest (most prominent in search results)
    # and rotate through themes across iterations to avoid repetition
    selected_theme = themes[(iteration - 1) % len(themes)]
    return dict(_THEME_TO_HP_ADJUSTMENTS.get(selected_theme, {}))


def _summarise_prior_results(prior_results: List[ImprovementMetrics]) -> str:
    """Build a short text summary of prior iteration results.

    Args:
        prior_results: List of ImprovementMetrics from previous iterations.

    Returns:
        Human-readable summary string, empty if no prior results.
    """
    if not prior_results:
        return ""
    last = prior_results[-1]
    if last.improved and last.improvement_pct is not None:
        return f"Last iteration improved by {last.improvement_pct:.2f}%."
    return "Last iteration did not improve over baseline."
