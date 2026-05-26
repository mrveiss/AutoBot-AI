# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Heartbeat Scheduler Service (#1407)

Manages scheduled and event-driven agent wakeups. Each enabled agent gets
an asyncio task that fires on its configured interval. Pending wakeup
requests are consumed (highest-priority first) before each tick executes.

Session state is persisted to agent_runtime_state so agents resume without
cold-starting across heartbeat runs.
"""

import asyncio
import uuid
from typing import Any, Dict, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import now_utc
from events.bus import publish_event
from events.event_types import HEARTBEAT_RUN_COMPLETED, HEARTBEAT_RUN_STARTED
from models.agent import Agent
from models.heartbeat import (
    AgentRuntimeState,
    AgentWakeupRequest,
    HeartbeatRun,
    HeartbeatRunEvent,
    HeartbeatRunStatus,
    WakeupTrigger,
)
from services.run_jwt import get_run_jwt_scopes, mint_run_jwt, revoke_run_jwt_async
from services.task_claim import renew_claim
from services import task_workspace

logger = get_logger(__name__)

_MIN_INTERVAL_SECONDS = 10
_DEFAULT_MAX_DURATION_SECONDS = 600


class HeartbeatScheduler:
    """
    Manages per-agent heartbeat loops and event-driven wakeups (#1407).

    Lifecycle:
      start()  -> spawns per-agent asyncio tasks for enabled agents
      stop()   -> cancels all running tasks
      wakeup() -> queues an event-driven wakeup request for an agent
    """

    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory
        self._tasks: Dict[str, asyncio.Task] = {}
        self._running = False

    async def start(self) -> None:
        """Load all enabled agents from DB and start their heartbeat loops."""
        if self._running:
            return
        self._running = True
        async with self._session_factory() as session:
            rows = await session.execute(select(AgentRuntimeState).where(AgentRuntimeState.heartbeat_enabled.is_(True)))
            states = rows.scalars().all()
        for state in states:
            self._spawn_task(state.agent_id, state.heartbeat_interval_seconds)
        logger.info("HeartbeatScheduler started: %s agents", len(self._tasks))

    async def stop(self) -> None:
        """Cancel all active heartbeat tasks."""
        self._running = False
        for agent_id, task in list(self._tasks.items()):
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            logger.info("Heartbeat task cancelled for agent %s", agent_id)
        self._tasks.clear()

    async def enable_agent(self, agent_id: str, interval_seconds: int) -> None:
        """Enable heartbeat for an agent and (re)start its loop (#1407)."""
        interval_seconds = max(interval_seconds, _MIN_INTERVAL_SECONDS)
        if agent_id in self._tasks:
            self._tasks[agent_id].cancel()
        if self._running:
            self._spawn_task(agent_id, interval_seconds)
        logger.info("Heartbeat enabled for agent %s (interval=%ss)", agent_id, interval_seconds)

    async def disable_agent(self, agent_id: str) -> None:
        """Disable heartbeat for an agent and cancel its loop (#1407)."""
        task = self._tasks.pop(agent_id, None)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        logger.info("Heartbeat disabled for agent %s", agent_id)

    async def wakeup(
        self,
        agent_id: str,
        context: Dict[str, Any] | None = None,
        priority: int = 0,
        reason: str | None = None,
    ) -> str:
        """Queue an event-driven wakeup request. Returns the request UUID (#1407).

        Deduplicates by (agent_id, task_id) for un-consumed requests (#6472).
        When a matching un-consumed row exists: merges contexts (incoming wins
        on conflict), takes max priority, increments merged_count, and returns
        the existing request id.  If task_id is absent from context no
        coalescing is attempted.
        """
        task_id: str | None = (context or {}).get("task_id")

        async with self._session_factory() as session:
            if task_id is not None:
                existing_result = await session.execute(
                    select(AgentWakeupRequest)
                    .where(
                        AgentWakeupRequest.agent_id == agent_id,
                        AgentWakeupRequest.consumed_at.is_(None),
                        AgentWakeupRequest.context["task_id"].astext == task_id,
                    )
                    .with_for_update()
                    .limit(1)
                )
                existing = existing_result.scalar_one_or_none()
                if existing is not None:
                    existing.context = {**(existing.context or {}), **(context or {})}
                    existing.priority = max(existing.priority, priority)
                    existing.merged_count = existing.merged_count + 1
                    await session.commit()
                    req_id = str(existing.id)
                    logger.debug(
                        "Wakeup coalesced for agent=%s task_id=%s (merged_count=%d)",
                        agent_id,
                        task_id,
                        existing.merged_count,
                    )
                    return req_id

            state = await _get_or_create_state(session, agent_id)
            req = AgentWakeupRequest(
                id=uuid.uuid4(),
                agent_id=agent_id,
                runtime_state_id=state.id,
                priority=priority,
                context=context,
                reason=reason,
            )
            session.add(req)
            await session.commit()
            req_id = str(req.id)

        logger.info("Wakeup request %s queued for agent %s", req_id, agent_id)
        if agent_id not in self._tasks and self._running:
            asyncio.create_task(
                self._run_once(agent_id, WakeupTrigger.EVENT),
                name=f"hb-adhoc-{agent_id}",
            )
        return req_id

    def _spawn_task(self, agent_id: str, interval_seconds: int) -> None:
        """Create and register an asyncio heartbeat task for agent_id (#1407)."""
        task = asyncio.create_task(
            self._heartbeat_loop(agent_id, interval_seconds),
            name=f"hb-{agent_id}",
        )
        self._tasks[agent_id] = task

    async def _heartbeat_loop(self, agent_id: str, interval_seconds: int) -> None:
        """Periodically fire heartbeat runs for agent_id (#1407)."""
        logger.info("Heartbeat loop started: agent=%s interval=%ss", agent_id, interval_seconds)
        while True:
            try:
                await asyncio.sleep(interval_seconds)
                await self._run_once(agent_id, WakeupTrigger.INTERVAL)
            except asyncio.CancelledError:
                logger.info("Heartbeat loop cancelled for agent %s", agent_id)
                return
            except Exception:
                logger.exception("Heartbeat loop error for agent %s (continuing)", agent_id)

    async def _run_once(self, agent_id: str, trigger: WakeupTrigger) -> None:
        """Execute one heartbeat run for agent_id (#1407)."""
        # Skip paused agents — budget hard-stop (GH#6470)
        if await self._is_agent_paused(agent_id):
            logger.info("Skipping heartbeat for budget-paused agent %s", agent_id)
            return
        run_id, state_id, timeout, run_jwt, workspace_dir = await self._start_run(agent_id, trigger)
        final_status, error_msg, usage = await self._invoke_agent(
            agent_id, state_id, run_id, timeout, run_jwt, workspace_dir
        )
        await self._finalize_run(agent_id, run_id, state_id, final_status, error_msg, usage, run_jwt)

    async def _is_agent_paused(self, agent_id: str) -> bool:
        """Return True if AgentRuntimeState.status is 'paused' (GH#6470)."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(AgentRuntimeState.status).where(AgentRuntimeState.agent_id == agent_id)
            )
            status = result.scalar_one_or_none()
            return status == "paused"

    async def _start_run(
        self, agent_id: str, trigger: WakeupTrigger
    ) -> Tuple[uuid.UUID, uuid.UUID, int, str, str | None]:
        """Create HeartbeatRun row; consume any pending wakeup request; mint run JWT (#1407, SEC-2).

        Returns (run_id, state_id, timeout, run_jwt, workspace_dir) where
        workspace_dir is the absolute path to the allocated worktree or None
        when no task is active (GH#6471).
        """
        async with self._session_factory() as session:
            state = await _get_or_create_state(session, agent_id)
            wakeup_req = await _consume_top_wakeup(session, agent_id)
            if wakeup_req is not None:
                trigger = WakeupTrigger.EVENT
            run = HeartbeatRun(
                id=uuid.uuid4(),
                agent_id=agent_id,
                runtime_state_id=state.id,
                status=HeartbeatRunStatus.RUNNING.value,
                trigger=trigger.value,
                wakeup_context=wakeup_req.context if wakeup_req else None,
                started_at=now_utc(),
            )
            session.add(run)
            await session.flush()
            run_id, state_id = run.id, state.id
            timeout = state.max_run_duration_seconds or _DEFAULT_MAX_DURATION_SECONDS
            await _append_event(session, run_id, "run_started", "Heartbeat run started")

            # Resolve agent_type for least-privilege scope selection (MVA-204)
            agent_result = await session.execute(select(Agent).where(Agent.agent_id == agent_id))
            agent_row = agent_result.scalar_one_or_none()
            agent_type = agent_row.agent_type if agent_row else "worker"

            # Allocate per-task worktree workspace (GH#6471)
            workspace_dir: str | None = None
            if state.current_task_id:
                try:
                    task_id_for_ws = state.current_task_id
                    ws_info = await asyncio.get_running_loop().run_in_executor(
                        None,
                        lambda: task_workspace.allocate(task_id_for_ws, agent_id),
                    )
                    workspace_dir = ws_info.worktree_path
                    state.workspace_dir = workspace_dir
                except Exception as exc:
                    # Clear stale workspace_dir so the adapter does not run
                    # in a deleted or invalid worktree (GH#6471 review finding).
                    state.workspace_dir = None
                    logger.warning(
                        "Workspace allocation failed for task=%s agent=%s: %s",
                        state.current_task_id,
                        agent_id,
                        exc,
                    )

            await session.commit()

        # Renew Redis task claim on each heartbeat tick (GH#6468)
        if state.current_task_id:
            await renew_claim(state.current_task_id, agent_id)

        # Mint run-scoped JWT with minimum required scopes (SEC-2 #6473, MVA-204)
        try:
            task_id = state.current_task_id or "default"
            tenant_id = "default"
            run_jwt = mint_run_jwt(
                str(run_id),
                task_id,
                agent_id,
                tenant_id,
                get_run_jwt_scopes(agent_type),
            )
        except Exception as exc:
            logger.error(f"Failed to mint run JWT for run {run_id}: {exc}")
            run_jwt = ""

        logger.info("Heartbeat run %s started for agent %s", run_id, agent_id)
        await publish_event(
            f"heartbeat:{agent_id}",
            HEARTBEAT_RUN_STARTED,
            {"run_id": str(run_id), "agent_id": agent_id, "trigger": trigger.value},
        )
        return run_id, state_id, timeout, run_jwt, workspace_dir

    async def _invoke_agent(
        self,
        agent_id: str,
        state_id: uuid.UUID,
        run_id: uuid.UUID,
        timeout: int,
        run_jwt: str,
        workspace_dir: str | None = None,
    ) -> Tuple[str, str | None, Dict[str, Any]]:
        """Run _execute_agent with timeout; return (status, error, usage) (#1407)."""
        try:
            result = await asyncio.wait_for(
                self._execute_agent(agent_id, state_id, run_id, run_jwt, workspace_dir),
                timeout=timeout,
            )
            return HeartbeatRunStatus.COMPLETED.value, None, result or {}
        except asyncio.TimeoutError:
            logger.warning("Heartbeat run %s timed out for agent %s", run_id, agent_id)
            return (
                HeartbeatRunStatus.TIMED_OUT.value,
                "Run exceeded max_run_duration_seconds",
                {},
            )
        except Exception as exc:
            logger.exception("Heartbeat run %s failed for %s: %s", run_id, agent_id, exc)
            return HeartbeatRunStatus.FAILED.value, str(exc), {}

    async def _finalize_run(
        self,
        agent_id: str,
        run_id: uuid.UUID,
        state_id: uuid.UUID,
        final_status: str,
        error_msg: str | None,
        usage: Dict[str, Any],
        run_jwt: str,
    ) -> None:
        """Persist run outcome and update agent runtime state; revoke run JWT (SEC-2)."""
        # Revoke the run JWT to prevent reuse (SEC-2 #6473)
        if run_jwt:
            try:
                await revoke_run_jwt_async(run_jwt)
            except Exception as exc:
                logger.warning(f"Failed to revoke run JWT for run {run_id}: {exc}")

        async with self._session_factory() as session:
            run_row = await session.get(HeartbeatRun, run_id)
            if run_row:
                run_row.status = final_status
                run_row.finished_at = now_utc()
                run_row.error_message = error_msg
                run_row.tokens_used = usage.get("tokens_used")
                run_row.cost_usd = usage.get("cost_usd")
                run_row.model = usage.get("model")
                run_row.provider = usage.get("provider")
            state_row = await session.get(AgentRuntimeState, state_id)
            if state_row:
                state_row.last_heartbeat_at = now_utc()
                if usage.get("session_params") is not None:
                    state_row.session_params = usage["session_params"]
            await _append_event(
                session,
                run_id,
                "run_finished",
                f"Run finished with status={final_status}",
            )
            await session.commit()
        await publish_event(
            f"heartbeat:{agent_id}",
            HEARTBEAT_RUN_COMPLETED,
            {
                "run_id": str(run_id),
                "agent_id": agent_id,
                "status": final_status,
                "error_message": error_msg,
                "tokens_used": usage.get("tokens_used"),
                "cost_usd": usage.get("cost_usd"),
            },
        )
        logger.info("Run %s finished: status=%s agent=%s", run_id, final_status, agent_id)

    async def _execute_agent(
        self,
        agent_id: str,
        state_id: uuid.UUID,
        run_id: uuid.UUID,
        run_jwt: str,
        workspace_dir: str | None = None,
    ) -> Dict[str, Any]:
        """
        Execute agent work for one heartbeat tick (#1407).

        Integration point for process adapter execution (see #1406).
        Passes run-scoped JWT via AUTOBOT_RUN_JWT env var (SEC-2 #6473).
        Passes workspace_dir via AUTOBOT_WORKSPACE_DIR env var (GH#6471) so the
        adapter subprocess has an isolated working tree.
        Returns dict with optional: tokens_used, cost_usd, model, provider, session_params.
        """
        logger.debug(
            "Agent %s tick (run %s) workspace=%s - no adapter bound",
            agent_id,
            run_id,
            workspace_dir,
        )
        # Adapter execution will pass run_jwt via AUTOBOT_RUN_JWT and
        # workspace_dir via AUTOBOT_WORKSPACE_DIR env vars.
        return {}


async def _get_or_create_state(session: AsyncSession, agent_id: str) -> AgentRuntimeState:
    """Return existing AgentRuntimeState or create one for agent_id (#1407)."""
    result = await session.execute(select(AgentRuntimeState).where(AgentRuntimeState.agent_id == agent_id))
    state = result.scalar_one_or_none()
    if state is None:
        state = AgentRuntimeState(id=uuid.uuid4(), agent_id=agent_id)
        session.add(state)
        await session.flush()
    return state


async def _consume_top_wakeup(session: AsyncSession, agent_id: str) -> AgentWakeupRequest | None:
    """
    Fetch and mark-consumed the highest-priority pending wakeup request (#1407).

    Returns the request or None if queue is empty.
    """
    result = await session.execute(
        select(AgentWakeupRequest)
        .where(
            AgentWakeupRequest.agent_id == agent_id,
            AgentWakeupRequest.consumed_at.is_(None),
        )
        .order_by(AgentWakeupRequest.priority.desc())
        .limit(1)
    )
    req = result.scalar_one_or_none()
    if req is not None:
        req.consumed_at = now_utc()
        await session.flush()
    return req


async def _append_event(
    session: AsyncSession,
    run_id: uuid.UUID,
    event_type: str,
    message: str | None = None,
    payload: Dict[str, Any] | None = None,
) -> None:
    """Append a HeartbeatRunEvent to a run (#1407)."""
    session.add(
        HeartbeatRunEvent(
            id=uuid.uuid4(),
            run_id=run_id,
            event_type=event_type,
            message=message,
            payload=payload,
            occurred_at=now_utc().isoformat(),
        )
    )
