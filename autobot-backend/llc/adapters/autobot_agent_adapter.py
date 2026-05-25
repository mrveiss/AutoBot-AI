# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""AutoBot agent adapter — wraps agents/base_agent.py for heartbeat dispatch (GH#8227).

``AutoBotAgentAdapter`` allows the LLC heartbeat scheduler to dispatch work to
any existing AutoBot agent without modifying that agent.  The adapter:

1. Validates the agent class at construction time (fail-fast import check).
2. On ``invoke``, instantiates the agent, builds an ``AgentRequest`` from the
   LLC context, and runs ``agent.process_request()`` in an asyncio Task.
3. Captures log output via a per-task ``logging.Handler`` routed through a
   ``contextvars.ContextVar`` (async-safe; does not touch ``sys.stdout``).
   Writes the combined log to ``run_log_store`` when provided.
4. Persists final run status to Redis so cross-worker ``status()`` calls return
   the correct result in multi-worker (4-uvicorn) production deployments.
5. After the task completes, forwards any token-usage metadata to
   ``BudgetService.ingest_cost_event``.  ``BudgetExhausted`` is re-raised so
   the GH#8215 hard-stop propagates; all other cost errors are best-effort.
"""

from __future__ import annotations

import asyncio
import contextvars
import importlib
import io
import json
import logging
import uuid
from typing import Any, Callable, Dict, Optional

from agents.base_agent import AgentRequest
from autobot_shared.redis_client import get_async_redis_client
from llc.exceptions import BudgetExhausted, ProviderRateLimited
from llc.models.enums import LLCRunStatus

from .base import AdapterRunStatus

logger = logging.getLogger(__name__)

# Keywords that identify a provider rate-limit or quota error in an error string.
_RL_KEYWORDS: frozenset[str] = frozenset({
    "rate_limit_error",
    "rate limit",
    "too many requests",
    "quota",
    "overloaded",
    "capacity_error",
    "429",
    "529",
})

# ── Rate-limit detection helpers (GH#8502) ────────────────────────────────────


def _is_rate_limit_error_str(error_str: str | None) -> bool:
    """Return True if *error_str* contains a provider rate-limit signal."""
    if not error_str:
        return False
    lower = error_str.lower()
    return any(kw in lower for kw in _RL_KEYWORDS)


def _extract_retry_after(exc: BaseException) -> int:
    """Return retry-after seconds hint from *exc*, or 0 if unknown."""
    if hasattr(exc, "response") and hasattr(exc.response, "headers"):
        try:
            return int(exc.response.headers.get("retry-after", 0))
        except (ValueError, TypeError):
            pass
    return 0


def _is_rate_limit_exc(exc: BaseException) -> tuple[bool, int]:
    """Return (is_rate_limit, retry_after_seconds) for an exception.

    Checks HTTP status codes (429, 503, 529) on httpx-style response errors
    and falls back to keyword matching on the exception message string.
    """
    status = getattr(exc, "status_code", None)
    if status in (429, 503, 529):
        return True, _extract_retry_after(exc)
    resp = getattr(exc, "response", None)
    if resp is not None and getattr(resp, "status_code", None) in (429, 503, 529):
        return True, _extract_retry_after(exc)
    if _is_rate_limit_error_str(str(exc)):
        return True, 0
    return False, 0


# ── Per-task log capture (async-safe) ─────────────────────────────────────────
# asyncio.create_task() copies the current Context, so each task gets its own
# ContextVar value.  _run_agent sets this to a fresh StringIO for its task;
# _TaskCapturingHandler routes log records there without touching sys.stdout.

_task_log_buf: contextvars.ContextVar[Optional[io.StringIO]] = contextvars.ContextVar("_task_log_buf", default=None)


class _TaskCapturingHandler(logging.Handler):
    """Routes log records to the current asyncio task's capture buffer.

    Installed once on the root logger at first adapter use.  Between tasks,
    ``_task_log_buf.get()`` returns ``None`` so the handler is a no-op.
    """

    def emit(self, record: logging.LogRecord) -> None:
        buf = _task_log_buf.get()
        if buf is None:
            return
        try:
            msg = self.format(record)
            buf.write(msg)
            buf.write("\n")
        except Exception:  # noqa: BLE001
            self.handleError(record)


_capturing_handler: Optional[_TaskCapturingHandler] = None


def _get_capturing_handler() -> _TaskCapturingHandler:
    """Return the singleton capturing handler, installing it on first call."""
    global _capturing_handler
    if _capturing_handler is None:
        _capturing_handler = _TaskCapturingHandler()
        _capturing_handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
        logging.root.addHandler(_capturing_handler)
    return _capturing_handler


# ── Redis-backed cross-worker status ─────────────────────────────────────────
# In 4-uvicorn prod, invoke() may land on worker A while status() lands on
# worker B.  We persist terminal statuses to Redis so any worker can answer.

_REDIS_KEY_PREFIX = "llc:adapter:run:"
_REDIS_STATUS_TTL = 86400  # 24 h — enough for any scheduler polling window

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
        raise ImportError(f"Invalid agent class path {dotted_path!r} — must be <module>.<ClassName>")
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
    ``run_id`` so ``status()`` and ``cancel()`` can look them up.  Terminal
    statuses are also written to Redis so cross-worker ``status()`` calls
    succeed in multi-worker deployments.  Call ``cleanup_completed()``
    periodically to release memory for both the task map and log cache.
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
        # run_ids for which cancel() was called; used to report CANCELLED even
        # while a non-cooperative task is still running (no asyncio.shield).
        self._cancel_requested: set = set()

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
        """Return the current status of a dispatched run.

        Checks the local task map first (same worker), then falls back to
        Redis for cross-worker visibility in multi-worker deployments.
        """
        task = self._tasks.get(run_id)
        if task is not None:
            # Cancelled-but-lingering: report CANCELLED immediately so the
            # scheduler is not stuck waiting on a non-cooperative task.
            if not task.done() and run_id in self._cancel_requested:
                return AdapterRunStatus(status=LLCRunStatus.CANCELLED)
            return _task_to_status(task)

        # Cross-worker fallback: check Redis for a persisted terminal status.
        try:
            redis = await get_async_redis_client()
            if redis is not None:
                raw = await redis.get(f"{_REDIS_KEY_PREFIX}{run_id}")
                if raw:
                    data = json.loads(raw)
                    return AdapterRunStatus(
                        status=LLCRunStatus(data["status"]),
                        error=data.get("error"),
                        exit_code=data.get("exit_code"),
                    )
        except Exception:
            logger.warning(
                "AutoBotAgentAdapter: Redis status lookup failed for run_id=%s",
                run_id,
                exc_info=True,
            )

        return AdapterRunStatus(
            status=LLCRunStatus.FAILED,
            error=f"Unknown run_id {run_id!r}",
        )

    async def cancel(self, agent_config: Dict[str, Any], run_id: str) -> None:
        """Cancel a dispatched run.

        Marks the run as cancel-requested, sends the asyncio cancellation, and
        waits up to 5 s for cooperative shutdown.  ``asyncio.wait`` (not
        ``asyncio.shield`` + ``wait_for``) is used so the task is NOT shielded
        from the original ``task.cancel()`` call and does NOT linger after
        ``cancel()`` returns.  If the task ignores cancellation for 5 s,
        ``status()`` still reports CANCELLED (via ``_cancel_requested``) so the
        scheduler can move on; the task will be cleaned up when it eventually
        finishes.
        """
        task = self._tasks.get(run_id)
        if task is None or task.done():
            return
        self._cancel_requested.add(run_id)
        task.cancel()
        done, _ = await asyncio.wait({task}, timeout=5.0)
        if task not in done:
            logger.warning(
                "AutoBotAgentAdapter: cancel() timed out after 5 s for run_id=%s"
                " (task still running — will be discarded when it finishes)",
                run_id,
            )

    async def run_blocking(self, context: Dict[str, Any]) -> None:
        """Run the agent to completion, propagating ProviderRateLimited.

        Unlike ``invoke()``, this awaits ``_run_agent`` directly so exceptions
        (including ``ProviderRateLimited``) propagate to the caller.  Used by
        the heartbeat scheduler's ``_dispatch_adapter`` so rate-limit errors can
        trigger exponential-backoff recovery (GH#8502).
        """
        run_id = str(uuid.uuid4())
        await self._run_agent(run_id, context)

    # ──────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────────────

    async def _run_agent(self, run_id: str, context: Dict[str, Any]) -> Any:
        """Instantiate the agent, run it, capture log output, forward costs."""
        agent = self._agent_cls(**self._agent_kwargs)
        request = _build_agent_request(run_id, context)

        # Per-task log capture: set the contextvar in this task's context copy.
        # asyncio.create_task() already copied the context, so this assignment
        # is isolated to this task — other concurrent tasks are unaffected.
        _get_capturing_handler()
        log_buf = io.StringIO()
        token = _task_log_buf.set(log_buf)

        final_status: AdapterRunStatus = AdapterRunStatus(status=LLCRunStatus.FAILED, error="unexpected exit")
        try:
            response = await agent.process_request(request)
            await self._forward_cost(run_id, response, context)
            # Detect error responses that signal failure without raising so
            # the Redis-persisted status matches what _task_to_status() returns.
            _resp_status = (
                response.get("status", "success")
                if isinstance(response, dict)
                else getattr(response, "status", "success")
            )
            if _resp_status == "error":
                _err = response.get("error") if isinstance(response, dict) else getattr(response, "error", None)
                # GH#8502: propagate rate-limit response errors so the scheduler
                # can apply exponential backoff and auto-resume.
                if _is_rate_limit_error_str(_err):
                    raise ProviderRateLimited(provider="", retry_after_seconds=0)
                final_status = AdapterRunStatus(status=LLCRunStatus.FAILED, exit_code=1, error=_err)
            else:
                final_status = AdapterRunStatus(status=LLCRunStatus.COMPLETED, exit_code=0)
            return response
        except asyncio.CancelledError:
            final_status = AdapterRunStatus(status=LLCRunStatus.CANCELLED)
            raise
        except ProviderRateLimited:
            final_status = AdapterRunStatus(status=LLCRunStatus.FAILED, error="provider rate-limited")
            raise
        except Exception as exc:
            # GH#8502: convert provider-level rate-limit exceptions (e.g. httpx
            # RateLimitError with status 429) to ProviderRateLimited so the
            # scheduler's backoff logic activates instead of marking the run failed.
            is_rl, retry_after = _is_rate_limit_exc(exc)
            if is_rl:
                final_status = AdapterRunStatus(status=LLCRunStatus.FAILED, error=str(exc))
                raise ProviderRateLimited(provider="", retry_after_seconds=retry_after) from exc
            final_status = AdapterRunStatus(status=LLCRunStatus.FAILED, error=str(exc))
            raise
        finally:
            _task_log_buf.reset(token)
            combined_log = log_buf.getvalue()
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

            await self._persist_run_status(run_id, final_status)

    async def _forward_cost(self, run_id: str, response: Any, context: Dict[str, Any]) -> None:
        """Forward token-usage from *response.metadata* to BudgetService.

        ``BudgetExhausted`` is re-raised so the GH#8215 hard-stop propagates
        to ``_run_agent`` and the run is recorded as FAILED.  All other errors
        are best-effort: logged as warnings and never re-raised.
        """
        if self._budget_session_factory is None:
            return

        metadata = getattr(response, "metadata", None) or {}
        # Use explicit None-check so a legitimate 0 value is not discarded (GH#8491).
        _ti = metadata.get("prompt_tokens")
        tokens_in: int = int(_ti) if _ti is not None else int(metadata.get("input_tokens", 0))
        _to = metadata.get("completion_tokens")
        tokens_out: int = int(_to) if _to is not None else int(metadata.get("output_tokens", 0))
        model: str = metadata.get("model", "")

        if not model or (tokens_in == 0 and tokens_out == 0):
            return

        agent_id: str = context.get("agent_id", "")
        if not agent_id:
            return

        try:
            from llc.services.budget import BudgetService

            async with self._budget_session_factory() as session:
                await BudgetService().ingest_cost_event(session, agent_id, tokens_in, tokens_out, model)
        except BudgetExhausted:
            raise  # Hard-stop from GH#8215: propagate so run is marked FAILED
        except Exception:
            logger.warning(
                "AutoBotAgentAdapter: cost forwarding failed for run_id=%s agent=%s",
                run_id,
                agent_id,
                exc_info=True,
            )

    async def _persist_run_status(self, run_id: str, final_status: AdapterRunStatus) -> None:
        """Write terminal run status to Redis for cross-worker visibility."""
        try:
            redis = await get_async_redis_client()
            if redis is None:
                return
            payload = json.dumps(
                {
                    "status": final_status.status.value,
                    "error": final_status.error,
                    "exit_code": final_status.exit_code,
                }
            )
            await redis.setex(f"{_REDIS_KEY_PREFIX}{run_id}", _REDIS_STATUS_TTL, payload)
        except Exception:
            logger.warning(
                "AutoBotAgentAdapter: Redis status persist failed for run_id=%s",
                run_id,
                exc_info=True,
            )

    def cleanup_completed(self) -> int:
        """Remove completed tasks and their log entries from the in-memory maps.

        Returns the number of entries removed.  Call periodically to prevent
        unbounded memory growth in long-lived scheduler processes.
        """
        done_ids = [rid for rid, t in self._tasks.items() if t.done()]
        for rid in done_ids:
            del self._tasks[rid]
            self._logs.pop(rid, None)
            self._cancel_requested.discard(rid)
        return len(done_ids)

    def get_log(self, run_id: str) -> Optional[str]:
        """Return captured log output for a completed run, or ``None``."""
        return self._logs.get(run_id)


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def _task_to_status(task: asyncio.Task) -> AdapterRunStatus:
    """Convert a local asyncio.Task to an AdapterRunStatus."""
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
    if isinstance(result, dict):
        status_val = result.get("status", "success")
    else:
        status_val = getattr(result, "status", "success")

    if status_val == "error":
        error_msg = result.get("error") if isinstance(result, dict) else getattr(result, "error", None)
        return AdapterRunStatus(
            status=LLCRunStatus.FAILED,
            exit_code=1,
            error=error_msg,
        )

    return AdapterRunStatus(status=LLCRunStatus.COMPLETED, exit_code=0)


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
        if k not in (
            "title",
            "description",
            "acceptance_criteria",
            "goal_ancestry",
            "kb_context",
            "agent_id",
            "action",
        ):
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
