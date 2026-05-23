# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""AutoBot agent adapter — wraps agents/base_agent.py for heartbeat dispatch (GH#8227).

``AutoBotAgentAdapter`` allows the LLC heartbeat scheduler to dispatch work to
any existing AutoBot agent without modifying that agent.  The adapter:

1. Validates the agent class at construction time (fail-fast import check).
2. On ``invoke``, instantiates the agent, builds an ``AgentRequest`` from the
   LLC context, and runs ``agent.process_request()`` in an asyncio Task.
3. Captures stdout/stderr via ``contextlib.redirect_stdout/stderr`` and
   writes the combined log to ``run_log_store`` when provided.
4. After the task completes, forwards any token-usage metadata to
   ``BudgetService.ingest_cost_event`` (best-effort; never raises on failure).
"""

from __future__ import annotations

import asyncio
import contextlib
import importlib
import io
import logging
import uuid
from typing import Any, Callable, Dict, Optional

from agents.base_agent import AgentRequest
from llc.models.enums import LLCRunStatus

from .base import AdapterRunStatus

logger = logging.getLogger(__name__)

# Sentinel for "no session provided" so budget ingestion is skipped cleanly.
_NO_SESSION = object()


def _import_agent_class(dotted_path: str) -> type:
    """Import and return an agent class by dotted module path.

    ``dotted_path`` must be ``<module>.<ClassName>``, e.g.:
    ``agents.summarization_agent.SummarizationAgent``

    Raises ``ImportError`` or ``AttributeError`` on failure so callers get a
    clear error at construction time rather than at dispatch time.
    """
    module_path, _, class_name = dotted_path.rpartition(".")
    if not module_path:
        raise ImportError(
            f"Invalid agent class path {dotted_path!r} — must be <module>.<ClassName>"
        )
    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    return cls


class AutoBotAgentAdapter:
    """LLC adapter that wraps any AutoBot agent for heartbeat dispatch.

    ``adapter_config`` schema::

        {
            "agent_class": "agents.summarization_agent.SummarizationAgent",
            "agent_kwargs": {}   # passed as **kwargs to the agent constructor
        }

    The adapter is **stateful**: it stores in-flight asyncio Tasks keyed by
    ``run_id`` so ``status()`` and ``cancel()`` can look them up.  Each
    adapter instance is intended to be long-lived (e.g. per-scheduler) so
    completed tasks accumulate; call ``cleanup_completed()`` periodically or
    after each status poll to release memory.
    """

    def __init__(
        self,
        agent_config: Dict[str, Any],
        *,
        budget_session_factory: Optional[Callable] = None,
        run_log_store: Optional[Any] = None,
    ) -> None:
        """Validate the agent class at construction time.

        Args:
            agent_config: Config dict with ``agent_class`` (required) and
                ``agent_kwargs`` (optional, default ``{}``).
            budget_session_factory: Zero-argument async callable that returns
                an ``AsyncSession`` for ``BudgetService``.  When ``None``,
                cost forwarding is skipped.
            run_log_store: Object with an ``async write(run_id, text)`` method.
                When ``None``, captured log output is discarded after logging.
        """
        agent_class_path = agent_config.get("agent_class", "")
        if not agent_class_path:
            raise ValueError("adapter_config must include 'agent_class'")

        # Fail-fast: import the class now so misconfigured agents fail at
        # registration time, not at first dispatch.
        self._agent_cls = _import_agent_class(agent_class_path)
        self._agent_kwargs: Dict[str, Any] = agent_config.get("agent_kwargs", {})

        self._budget_session_factory = budget_session_factory
        self._run_log_store = run_log_store

        # run_id → asyncio.Task  (populated by invoke, read by status/cancel)
        self._tasks: Dict[str, asyncio.Task] = {}
        # run_id → captured log text (populated after task completion)
        self._logs: Dict[str, str] = {}

    # ──────────────────────────────────────────────────────────────────────
    # LLCAdapter protocol implementation
    # ──────────────────────────────────────────────────────────────────────

    async def invoke(self, agent_config: Dict[str, Any], context: Dict[str, Any]) -> str:
        """Dispatch the agent on the given LLC context.

        Creates an asyncio Task and stores it under a fresh ``run_id``.
        Returns the ``run_id`` so the scheduler can poll ``status()`` later.
        """
        run_id = str(uuid.uuid4())
        task = asyncio.create_task(
            self._run_agent(run_id, context),
            name=f"llc-agent-{self._agent_cls.__name__}-{run_id[:8]}",
        )
        self._tasks[run_id] = task
        logger.info(
            "AutoBotAgentAdapter: dispatched %s run_id=%s",
            self._agent_cls.__name__,
            run_id,
        )
        return run_id

    async def status(self, agent_config: Dict[str, Any], run_id: str) -> AdapterRunStatus:
        """Return the current status of a dispatched run."""
        task = self._tasks.get(run_id)
        if task is None:
            return AdapterRunStatus(
                status=LLCRunStatus.FAILED,
                error=f"Unknown run_id {run_id!r}",
            )

        if not task.done():
            return AdapterRunStatus(status=LLCRunStatus.RUNNING)

        if task.cancelled():
            return AdapterRunStatus(status=LLCRunStatus.CANCELLED)

        exc = task.exception()
        if exc is not None:
            return AdapterRunStatus(
                status=LLCRunStatus.FAILED,
                error=str(exc),
            )

        result = task.result()
        # AgentResponse.status is "success" or "error"
        if isinstance(result, dict):
            status_val = result.get("status", "success")
        else:
            status_val = getattr(result, "status", "success")

        if status_val == "error":
            error_msg = (
                result.get("error") if isinstance(result, dict) else getattr(result, "error", None)
            )
            return AdapterRunStatus(
                status=LLCRunStatus.FAILED,
                exit_code=1,
                error=error_msg,
            )

        return AdapterRunStatus(status=LLCRunStatus.COMPLETED, exit_code=0)

    async def cancel(self, agent_config: Dict[str, Any], run_id: str) -> None:
        """Cancel a dispatched run."""
        task = self._tasks.get(run_id)
        if task is None or task.done():
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    # ──────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────────────

    async def _run_agent(self, run_id: str, context: Dict[str, Any]) -> Any:
        """Instantiate the agent, run it, capture output, forward costs."""
        agent = self._agent_cls(**self._agent_kwargs)
        request = _build_agent_request(run_id, context)

        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()

        with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
            response = await agent.process_request(request)

        combined_log = stdout_buf.getvalue() + stderr_buf.getvalue()
        self._logs[run_id] = combined_log

        if combined_log and self._run_log_store is not None:
            try:
                await self._run_log_store.write(run_id, combined_log)
            except Exception:
                logger.warning(
                    "AutoBotAgentAdapter: run_log_store.write failed for run_id=%s",
                    run_id,
                    exc_info=True,
                )

        await self._forward_cost(run_id, response, context)
        return response

    async def _forward_cost(
        self, run_id: str, response: Any, context: Dict[str, Any]
    ) -> None:
        """Forward token-usage from *response.metadata* to BudgetService.

        This is best-effort: any failure is logged but never re-raised so the
        caller always sees the agent result rather than a billing error.
        """
        if self._budget_session_factory is None:
            return

        metadata = getattr(response, "metadata", None) or {}
        tokens_in: int = metadata.get("prompt_tokens", 0) or metadata.get("input_tokens", 0)
        tokens_out: int = metadata.get("completion_tokens", 0) or metadata.get("output_tokens", 0)
        model: str = metadata.get("model", "")

        if not model or (tokens_in == 0 and tokens_out == 0):
            return

        agent_id: str = context.get("agent_id", "")
        if not agent_id:
            return

        try:
            from llc.services.budget import BudgetService

            async with self._budget_session_factory() as session:
                await BudgetService().ingest_cost_event(
                    session, agent_id, tokens_in, tokens_out, model
                )
        except Exception:
            logger.warning(
                "AutoBotAgentAdapter: cost forwarding failed for run_id=%s agent=%s",
                run_id,
                agent_id,
                exc_info=True,
            )

    def cleanup_completed(self) -> int:
        """Remove completed tasks from the in-memory map.

        Returns the number of entries removed.  Call periodically to prevent
        unbounded memory growth in long-lived scheduler processes.
        """
        done_ids = [rid for rid, t in self._tasks.items() if t.done()]
        for rid in done_ids:
            del self._tasks[rid]
        return len(done_ids)

    def get_log(self, run_id: str) -> Optional[str]:
        """Return captured stdout/stderr for a completed run, or ``None``."""
        return self._logs.get(run_id)


# ──────────────────────────────────────────────────────────────────────────────
# Context → AgentRequest conversion
# ──────────────────────────────────────────────────────────────────────────────

def _build_agent_request(run_id: str, context: Dict[str, Any]) -> AgentRequest:
    """Build an ``AgentRequest`` from an LLC dispatch context.

    Phase 3 stub: passes work-item text fields as the request payload.
    Phase 5 will replace this with a full RAG-assembled prompt.

    Context keys consumed:
    - ``title``              Work item title
    - ``description``        Work item description
    - ``acceptance_criteria``  Work item acceptance criteria
    - ``goal_ancestry``      List of ancestor goal titles (phase 3: raw text)
    - ``kb_context``         Agent KB excerpt (phase 3: raw text)
    - ``action``             Override the request action (default: ``"execute"``)
    """
    payload: Dict[str, Any] = {
        "title": context.get("title", ""),
        "description": context.get("description", ""),
        "acceptance_criteria": context.get("acceptance_criteria", ""),
        "goal_ancestry": context.get("goal_ancestry", []),
        "kb_context": context.get("kb_context", ""),
    }
    # Merge any extra keys the caller wants to pass through.
    for k, v in context.items():
        if k not in ("title", "description", "acceptance_criteria", "goal_ancestry", "kb_context", "agent_id", "action"):
            payload[k] = v

    return AgentRequest(
        request_id=run_id,
        agent_type="llc_dispatch",
        action=context.get("action", "execute"),
        payload=payload,
        context={
            "source": "llc_heartbeat",
            "run_id": run_id,
        },
    )
