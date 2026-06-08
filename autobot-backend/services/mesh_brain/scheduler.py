# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""MeshBrainScheduler — orchestrates autonomous mesh evolution jobs (#1994, #2120)."""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from autobot_shared.logging_manager import get_logger
from constants.threshold_constants import TimingConstants

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Job status
# ---------------------------------------------------------------------------

_INTERVALS: dict[str, int] = {
    "edge_sync": 300,
    "edge_discoverer": 86400,
    "mesh_pruner": 604800,
    "node_promoter": 86400,
}

_METHOD_MAP: dict[str, str] = {
    "edge_sync": "sync",
    "edge_discoverer": "discover",
    "mesh_pruner": "prune",
    "node_promoter": "evaluate",
}


@dataclass
class JobStatus:
    """Runtime state for a single scheduler job."""

    name: str
    schedule: str
    last_run: datetime | None = None
    last_result: str | None = None  # "success" | "failed" | "skipped"
    next_run: datetime | None = None
    is_running: bool = False


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------


class MeshBrainScheduler:
    """Orchestrates all autonomous mesh evolution jobs.

    Schedule:
    - edge_learner:    realtime (Redis stream consumer, always running)
    - edge_sync:       every 5 minutes
    - node_promoter:   daily at 3 AM UTC  (24-hour interval approximation)
    - edge_discoverer: daily at 2 AM UTC  (24-hour interval approximation)
    - mesh_pruner:     weekly Sunday at 4 AM UTC (7-day interval approximation)
    """

    SCHEDULE: dict[str, dict[str, str]] = {
        "edge_learner": {
            "cron": "realtime",
            "description": "Hebbian reinforcement from feedback",
        },
        "edge_sync": {
            "cron": "*/5 * * * *",
            "description": "PG to Redis edge sync",
        },
        "node_promoter": {
            "cron": "0 3 * * *",
            "description": "Anchor emergence",
        },
        "edge_discoverer": {
            "cron": "0 2 * * *",
            "description": "Relationship naming",
        },
        "mesh_pruner": {
            "cron": "0 4 * * 0",
            "description": "Entropy control",
        },
    }

    def __init__(
        self,
        edge_learner: Any = None,
        edge_sync: Any = None,
        edge_discoverer: Any = None,
        mesh_pruner: Any = None,
        node_promoter: Any = None,
        mesh_db: Any = None,
    ) -> None:
        self._components: dict[str, Any] = {
            "edge_learner": edge_learner,
            "edge_sync": edge_sync,
            "edge_discoverer": edge_discoverer,
            "mesh_pruner": mesh_pruner,
            "node_promoter": node_promoter,
        }
        self._mesh_db = mesh_db
        self._running: bool = False
        self._tasks: dict[str, asyncio.Task] = {}
        self._jobs: dict[str, JobStatus] = {
            name: JobStatus(name=name, schedule=cfg["cron"]) for name, cfg in self.SCHEDULE.items()
        }

    async def start(self) -> None:
        """Start all scheduled jobs."""
        self._running = True
        logger.info("MeshBrainScheduler starting")
        self._maybe_start_realtime_consumer()
        self._start_periodic_jobs()

    def _maybe_start_realtime_consumer(self) -> None:
        """Launch the edge_learner realtime consumer task if component is present."""
        if self._components.get("edge_learner"):
            self._tasks["edge_learner"] = asyncio.create_task(self._run_realtime_consumer())

    def _start_periodic_jobs(self) -> None:
        """Launch asyncio tasks for each periodic job whose component is present."""
        for name in _INTERVALS:
            if self._components.get(name):
                self._tasks[name] = asyncio.create_task(self._run_periodic(name))

    async def stop(self) -> None:
        """Cancel all running tasks gracefully."""
        self._running = False
        for name, task in list(self._tasks.items()):
            task.cancel()
        self._tasks.clear()
        logger.info("MeshBrainScheduler stopped")

    async def _run_realtime_consumer(self) -> None:
        """Run the edge_learner stream consumer in a loop until stopped."""
        learner = self._components["edge_learner"]
        while self._running:
            try:
                await learner.consume_feedback_stream()
            except Exception as exc:
                logger.error("edge_learner stream consumer failed: %s", exc)
            await asyncio.sleep(TimingConstants.STANDARD_DELAY)

    async def _run_periodic(self, name: str) -> None:
        """Run a job on its fixed interval until the scheduler is stopped."""
        interval = _INTERVALS[name]
        while self._running:
            await self._execute_job(name)
            await asyncio.sleep(interval)

    async def _execute_job(self, name: str) -> None:
        """Execute one job run with status tracking and error logging."""
        component = self._components.get(name)
        if not component:
            return

        job = self._jobs[name]
        job.is_running = True
        job.last_run = datetime.now(tz=timezone.utc)

        try:
            method_name = _METHOD_MAP.get(name, "run")
            await getattr(component, method_name)()
            job.last_result = "success"
            logger.debug("Mesh brain job %s completed successfully", name)
        except Exception as exc:
            job.last_result = "failed"
            logger.error("Mesh brain job %s failed: %s", name, exc)
            await self._log_job_failure(name, exc)
        finally:
            job.is_running = False

    async def _log_job_failure(self, name: str, exc: Exception) -> None:
        """Write job failure to mesh_evolution_log if mesh_db is available."""
        if self._mesh_db:
            await self._mesh_db.log_evolution("job_failed", None, None, {"error": str(exc)}, name)

    def get_status(self) -> dict:
        """Return a snapshot of all job statuses for the health API endpoint."""
        return {
            "running": self._running,
            "jobs": {
                name: _job_to_dict(job, self._components.get(name) is not None) for name, job in self._jobs.items()
            },
        }


def _job_to_dict(job: JobStatus, component_available: bool) -> dict:
    """Serialise a JobStatus to a plain dict for JSON responses."""
    return {
        "schedule": job.schedule,
        "last_run": job.last_run.isoformat() if job.last_run else None,
        "last_result": job.last_result,
        "is_running": job.is_running,
        "component_available": component_available,
    }
