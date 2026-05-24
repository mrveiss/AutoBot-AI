# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Agent diary → KB writer — post-heartbeat hook (GH#8237).

After each heartbeat run reaches a terminal status (succeeded/failed),
``AgentDiaryKbWriter.write_from_run()`` is called to:

1. Format a diary entry from the run's context snapshot and outcome.
2. Persist the entry via ``AgentDiaryService`` (category ``AGENT_DIARY``).
3. Run ``TaskPatternLearner`` on any available outcome history and index
   the resulting patterns with ``{"type": "pattern"}`` metadata.

All operations are best-effort: failures are logged and swallowed so a KB
write error never blocks run teardown.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _format_diary_entry(
    run_id: str,
    agent_id: str,
    work_item_id: Optional[str],
    status: str,
    context_snapshot: Optional[Dict[str, Any]],
) -> str:
    """Build a human-readable diary entry from run context.

    Prefixed with ``[<work_item_id>]`` so future searches can filter by task.
    """
    snap = context_snapshot or {}
    prefix = f"[{work_item_id}] " if work_item_id else ""
    title = snap.get("title", "")
    description = snap.get("description", "")
    decisions = snap.get("decisions", [])
    work_products = snap.get("work_products", [])
    comments_count = snap.get("comments_count", 0)

    lines: List[str] = [
        f"{prefix}Heartbeat run {run_id} — agent {agent_id} — status: {status}",
    ]
    if title:
        lines.append(f"Task: {title}")
    if description:
        lines.append(f"Description: {description[:500]}")
    if decisions:
        lines.append("Decisions: " + "; ".join(str(d) for d in decisions[:10]))
    if work_products:
        lines.append("Work products: " + ", ".join(str(w) for w in work_products[:10]))
    if comments_count:
        lines.append(f"Comments created: {comments_count}")
    return "\n".join(lines)


class AgentDiaryKbWriter:
    """Post-heartbeat hook that writes diary entries and patterns to KB.

    Instantiate once and call ``write_from_run()`` after each terminal run.
    All KB operations are best-effort — exceptions are caught and logged.
    """

    async def write_from_run(
        self,
        run_id: str,
        agent_id: str,
        status: str,
        work_item_id: Optional[str] = None,
        context_snapshot: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Write diary entry and patterns for a completed heartbeat run.

        Args:
            run_id: Heartbeat run identifier (used as session_id for diary).
            agent_id: Agent that executed the run.
            status: Terminal status — ``"succeeded"`` or ``"failed"``.
            work_item_id: Optional work item the run was scoped to.
            context_snapshot: JSONB snapshot from ``LLCHeartbeatRun.context_snapshot``.
        """
        if status not in ("succeeded", "failed", "completed"):
            return
        try:
            await self._write_diary_entry(run_id, agent_id, status, work_item_id, context_snapshot)
        except Exception:
            logger.warning(
                "AgentDiaryKbWriter.write_from_run: diary entry failed for run_id=%s",
                run_id,
                exc_info=True,
            )
        try:
            await self._write_patterns(run_id, agent_id, status, context_snapshot)
        except Exception:
            logger.warning(
                "AgentDiaryKbWriter.write_from_run: pattern write failed for run_id=%s",
                run_id,
                exc_info=True,
            )

    # ------------------------------------------------------------------
    # Diary entry
    # ------------------------------------------------------------------

    async def _write_diary_entry(
        self,
        run_id: str,
        agent_id: str,
        status: str,
        work_item_id: Optional[str],
        context_snapshot: Optional[Dict[str, Any]],
    ) -> None:
        try:
            from memory.agent_diary import AgentDiaryService

            entry = _format_diary_entry(run_id, agent_id, work_item_id, status, context_snapshot)
            diary = AgentDiaryService()
            fact_id = await diary.write(
                agent_name=agent_id,
                session_id=run_id,
                entry=entry,
                topic="heartbeat",
            )
            # Augment the stored fact's metadata to carry LLC-specific fields.
            # AgentDiaryService.write() already stored the fact; we re-write
            # via the KB's upsert path with extended metadata if fact_id is valid.
            if fact_id:
                await self._upsert_with_llc_metadata(
                    agent_id=agent_id,
                    fact_id=fact_id,
                    entry=entry,
                    run_id=run_id,
                    work_item_id=work_item_id,
                )
        except Exception:
            logger.warning(
                "AgentDiaryKbWriter: diary entry failed for run_id=%s agent=%s",
                run_id,
                agent_id,
                exc_info=True,
            )

    async def _upsert_with_llc_metadata(
        self,
        agent_id: str,
        fact_id: str,
        entry: str,
        run_id: str,
        work_item_id: Optional[str],
    ) -> None:
        """Re-index the diary fact with LLC-specific metadata fields.

        The base ``AgentDiaryService.write()`` stores the fact but doesn't know
        about LLC run_id / work_item_id.  We upsert the same content with the
        extended metadata so downstream searches can filter by those fields.
        """
        try:
            from knowledge._composed import get_knowledge_base

            kb = await get_knowledge_base()
            metadata: Dict[str, Any] = {
                "category": "AGENT_DIARY",
                "source": agent_id,
                "agent_name": agent_id,
                "session_id": run_id,
                "topic": "heartbeat",
                "diary_timestamp": datetime.now(tz=timezone.utc).isoformat(),
                "run_id": run_id,
                "work_item_id": work_item_id or "",
                "date": datetime.now(tz=timezone.utc).date().isoformat(),
            }
            await kb.store_fact(content=entry, metadata=metadata)
        except Exception:
            logger.warning(
                "AgentDiaryKbWriter: metadata upsert failed for fact_id=%s", fact_id, exc_info=True
            )

    # ------------------------------------------------------------------
    # Pattern learning
    # ------------------------------------------------------------------

    async def _write_patterns(
        self,
        run_id: str,
        agent_id: str,
        status: str,
        context_snapshot: Optional[Dict[str, Any]],
    ) -> None:
        """Run TaskPatternLearner on available outcomes and index results."""
        try:
            snap = context_snapshot or {}
            task_type = snap.get("task_type", "llc_heartbeat")
            outcomes = snap.get("outcomes", [])

            if not outcomes:
                return

            from agents.task_pattern_learner import TaskPatternLearner

            learner = TaskPatternLearner()
            strategy = await learner.learn_from_outcomes(task_type, outcomes)
            if strategy is None:
                return

            pattern_entry = (
                f"[pattern] agent={agent_id} task_type={task_type} "
                f"approach={strategy.best_approach} "
                f"confidence={strategy.confidence:.2f} "
                f"avg_score={strategy.avg_score:.2f} "
                f"failures={'; '.join(strategy.failure_patterns[:5])}"
            )
            from knowledge._composed import get_knowledge_base

            kb = await get_knowledge_base()
            await kb.store_fact(
                content=pattern_entry,
                metadata={
                    "category": "AGENT_DIARY",
                    "source": agent_id,
                    "agent_name": agent_id,
                    "session_id": run_id,
                    "topic": "heartbeat",
                    "diary_timestamp": datetime.now(tz=timezone.utc).isoformat(),
                    "run_id": run_id,
                    "type": "pattern",
                    "task_type": task_type,
                },
            )
        except Exception:
            logger.warning(
                "AgentDiaryKbWriter: pattern write failed for run_id=%s", run_id, exc_info=True
            )


__all__ = ["AgentDiaryKbWriter"]
