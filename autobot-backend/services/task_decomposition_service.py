# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Task Decomposition Service (#1406)

Splits a parent task into ordered subtasks, executes them in dependency
order, and feeds context_out from each step into context_in of successors.
Partial completion is preserved: if step N fails, steps 0..N-1 results
remain in the DB.
"""

import asyncio
import uuid
from typing import Any, Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from autobot_shared.logging_manager import get_logger
from constants.threshold_constants import TimingConstants
from models.process_run import ProcessRun, ProcessRunStatus, TaskDecomposition
from services.process_adapter_service import ProcessAdapterService

logger = get_logger(__name__)


class TaskDecompositionService:
    """
    Manages decomposed task execution with dependency resolution (#1406).

    Usage:
        decomp_ids = await svc.decompose_task(parent_task_id, subtasks)
        await svc.execute_decomposition(parent_task_id)
    """

    def __init__(
        self,
        session_factory: async_sessionmaker,
        process_svc: ProcessAdapterService,
    ) -> None:
        self._session_factory = session_factory
        self._process_svc = process_svc

    async def decompose_task(
        self,
        parent_task_id: str,
        subtasks: List[Dict[str, Any]],
    ) -> List[str]:
        """
        Create ordered TaskDecomposition rows for a parent task (#1406).

        Each subtask dict must have: agent_id, command, args (opt),
        timeout_seconds (opt), depends_on (opt list of subtask_order ints).
        Returns list of TaskDecomposition UUID strings.
        """
        ids: List[str] = []
        async with self._session_factory() as session:
            for order, sub in enumerate(subtasks):
                run_id = await self._create_stub_run(session, sub)
                td = TaskDecomposition(
                    id=uuid.uuid4(),
                    parent_task_id=parent_task_id,
                    subtask_order=order,
                    process_run_id=run_id,
                    depends_on=sub.get("depends_on"),
                    context_in=sub.get("context_in"),
                    status=ProcessRunStatus.QUEUED.value,
                )
                session.add(td)
                ids.append(str(td.id))
            await session.commit()
        logger.info("Decomposed task %s into %s subtasks", parent_task_id, len(subtasks))
        return ids

    async def execute_decomposition(self, parent_task_id: str) -> None:
        """
        Run all subtasks for parent_task_id in dependency order (#1406).

        Subtasks with no unresolved depends_on are eligible to run.
        Context from completed subtasks propagates to dependents.
        Stops if any subtask fails.
        """
        subtasks = await self._load_subtasks(parent_task_id)
        completed: Dict[int, Any] = {}
        for td in subtasks:
            if not await self._deps_satisfied(td, completed):
                logger.warning("Subtask order=%s blocked by unmet deps, aborting", td.subtask_order)
                await self._mark_td_status(td.id, ProcessRunStatus.CANCELLED.value)
                continue
            ctx_in = _merge_context(td.context_in, td.depends_on, completed)
            await self._update_context_in(td.id, ctx_in)
            run_id = str(td.process_run_id)
            run_row = await self._get_run(run_id)
            if run_row is None:
                logger.error("ProcessRun %s not found for subtask %s", run_id, td.id)
                await self._mark_td_status(td.id, ProcessRunStatus.FAILED.value)
                break
            proc_id = await self._process_svc.spawn_process(
                agent_id=run_row.agent_id,
                command=run_row.command,
                args=run_row.args or [],
                timeout_seconds=run_row.timeout_seconds,
                task_id=parent_task_id,
            )
            final_status = await self._wait_for_process(proc_id)
            context_out = {"process_id": proc_id, "status": final_status}
            await self._save_context_out(td.id, context_out, final_status)
            completed[td.subtask_order] = context_out
            if final_status != ProcessRunStatus.COMPLETED.value:
                logger.warning(
                    "Subtask %s (order=%s) failed with %s; halting decomposition",
                    td.id,
                    td.subtask_order,
                    final_status,
                )
                break

    async def get_decomposition_status(self, parent_task_id: str) -> List[Dict[str, Any]]:
        """Return status dicts for all subtasks of parent_task_id (#1406)."""
        subtasks = await self._load_subtasks(parent_task_id)
        return [
            {
                "id": str(td.id),
                "subtask_order": td.subtask_order,
                "status": td.status,
                "context_in": td.context_in,
                "context_out": td.context_out,
                "depends_on": td.depends_on,
                "process_run_id": str(td.process_run_id),
            }
            for td in subtasks
        ]

    # -- Internal helpers --------------------------------------------------

    async def _load_subtasks(self, parent_task_id: str) -> List[TaskDecomposition]:
        """Load TaskDecomposition rows ordered by subtask_order (#1406)."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(TaskDecomposition)
                .where(TaskDecomposition.parent_task_id == parent_task_id)
                .order_by(TaskDecomposition.subtask_order)
            )
            return list(result.scalars().all())

    async def _create_stub_run(self, session: AsyncSession, sub: Dict[str, Any]) -> uuid.UUID:
        """Insert a QUEUED ProcessRun stub for a subtask (#1406)."""
        run_id = uuid.uuid4()
        session.add(
            ProcessRun(
                id=run_id,
                agent_id=sub["agent_id"],
                command=sub["command"],
                args=sub.get("args", []),
                status=ProcessRunStatus.QUEUED.value,
                timeout_seconds=sub.get("timeout_seconds", 300),
            )
        )
        await session.flush()
        return run_id

    async def _deps_satisfied(
        self,
        td: TaskDecomposition,
        completed: Dict[int, Any],
    ) -> bool:
        """Return True if all depends_on orders are in completed (#1406)."""
        if not td.depends_on:
            return True
        return all(dep in completed for dep in td.depends_on)

    async def _mark_td_status(self, td_id: uuid.UUID, status: str) -> None:
        """Update TaskDecomposition.status in DB (#1406)."""
        async with self._session_factory() as session:
            row = await session.get(TaskDecomposition, td_id)
            if row:
                row.status = status
            await session.commit()

    async def _update_context_in(self, td_id: uuid.UUID, ctx_in: Dict[str, Any] | None) -> None:
        """Persist merged context_in before execution (#1406)."""
        async with self._session_factory() as session:
            row = await session.get(TaskDecomposition, td_id)
            if row:
                row.context_in = ctx_in
                row.status = ProcessRunStatus.RUNNING.value
            await session.commit()

    async def _save_context_out(self, td_id: uuid.UUID, context_out: Dict[str, Any], status: str) -> None:
        """Persist context_out after execution (#1406)."""
        async with self._session_factory() as session:
            row = await session.get(TaskDecomposition, td_id)
            if row:
                row.context_out = context_out
                row.status = status
            await session.commit()

    async def _get_run(self, process_id: str) -> ProcessRun | None:
        """Fetch a ProcessRun by UUID string (#1406)."""
        async with self._session_factory() as session:
            return await session.get(ProcessRun, uuid.UUID(process_id))

    async def _wait_for_process(self, process_id: str) -> str:
        """Poll until process reaches a terminal state; return status (#1406)."""
        while True:
            status_data = await self._process_svc.get_process_status(process_id)
            if status_data is None:
                return ProcessRunStatus.FAILED.value
            status = status_data["status"]
            if status in {
                ProcessRunStatus.COMPLETED.value,
                ProcessRunStatus.FAILED.value,
                ProcessRunStatus.TIMED_OUT.value,
                ProcessRunStatus.CANCELLED.value,
            }:
                return status
            await asyncio.sleep(TimingConstants.SHORT_DELAY)


# -- Module-level helpers --------------------------------------------------


def _merge_context(
    own_ctx: Dict[str, Any] | None,
    depends_on: List[int] | None,
    completed: Dict[int, Any],
) -> Dict[str, Any]:
    """
    Build merged context_in for a subtask (#1406).

    Combines the subtask's own context_in with context_out from dependencies.
    Own context_in keys take precedence over dependency outputs.
    """
    merged: Dict[str, Any] = {}
    if depends_on:
        for dep_order in depends_on:
            dep_ctx = completed.get(dep_order, {})
            if isinstance(dep_ctx, dict):
                merged.update(dep_ctx)
    if own_ctx:
        merged.update(own_ctx)
    return merged or None
