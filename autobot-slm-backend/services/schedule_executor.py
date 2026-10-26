# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Schedule Executor Service (Issue #741 - Phase 7).

Background task that checks schedules every minute and triggers syncs
when due. Integrates with the code sync system to execute scheduled
code deployments across the fleet.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Tuple

from croniter import croniter
from fastapi import HTTPException
from sqlalchemy import select

from autobot_shared.cron_expression import log_stored_cron_findings
from models.database import CodeStatus, Node, UpdateSchedule
from services.database import db_service

logger = logging.getLogger(__name__)

# Module-level state
_executor_running = False
_executor_task: asyncio.Task | None = None


async def report_stored_schedules() -> int:
    """Startup scan: WARN once per stored schedule whose cron the shared validator rejects.

    Report-only (#18449): a stored 6-field cron still computes and fires through
    croniter exactly as before; the warning names the schedule and
    ``schedule.invalid_cron`` so the state is visible. Returns the count reported.
    """
    reported = 0
    try:
        async with db_service.session() as db:
            result = await db.execute(select(UpdateSchedule))
            for schedule in result.scalars().all():
                if not log_stored_cron_findings(logger, "Schedule", schedule.id, schedule.cron_expression):
                    reported += 1
    except Exception as e:
        logger.warning("Stored schedule scan failed: %s", e)
    return reported


def calculate_next_run(expression: str, base: datetime = None) -> datetime:
    """
    Calculate the next run time from a cron expression.

    Args:
        expression: Cron expression string
        base: Base datetime to calculate from (default: now)

    Returns:
        Next scheduled datetime
    """
    base = base or datetime.now(timezone.utc)
    cron = croniter(expression, base)
    return cron.get_next(datetime)


_WEEKDAY_NAMES = {
    "0": "Sunday",
    "1": "Monday",
    "2": "Tuesday",
    "3": "Wednesday",
    "4": "Thursday",
    "5": "Friday",
    "6": "Saturday",
    "7": "Sunday",
}

_COMMON_CRON_PATTERNS = {
    "0 * * * *": "Every hour",
    "0 0 * * *": "Every day at midnight",
    "0 2 * * *": "Every day at 2:00 AM",
    "0 0 * * 0": "Every Sunday at midnight",
    "0 0 1 * *": "First day of every month",
}


def _describe_cron_time_part(minute: str, hour: str) -> str:
    """Helper for describe_cron_expression. Ref: #1088."""
    if minute == "0" and hour != "*":
        if hour.isdigit():
            h = int(hour)
            period = "AM" if h < 12 else "PM"
            h = h if h <= 12 else h - 12
            h = 12 if h == 0 else h
            return f"at {h}:00 {period}"
        return f"at hour {hour}"
    if minute != "*":
        return f"at minute {minute}"
    return ""


def _describe_cron_day_part(day: str, month: str, weekday: str) -> str:
    """Helper for describe_cron_expression. Ref: #1088."""
    if day == "*" and month == "*" and weekday == "*":
        return "Daily"
    if weekday != "*":
        if weekday in _WEEKDAY_NAMES:
            return f"Every {_WEEKDAY_NAMES[weekday]}"
        return f"On weekday {weekday}"
    return ""


def describe_cron_expression(expression: str) -> str:
    """
    Generate a human-readable description of a cron expression.

    Args:
        expression: Cron expression string

    Returns:
        Human-readable description
    """
    try:
        if expression in _COMMON_CRON_PATTERNS:
            return _COMMON_CRON_PATTERNS[expression]

        parts = expression.split()
        if len(parts) != 5:
            return expression

        minute, hour, day, month, weekday = parts

        desc_parts = []

        time_part = _describe_cron_time_part(minute, hour)
        if time_part:
            desc_parts.append(time_part)

        day_part = _describe_cron_day_part(day, month, weekday)
        if day_part:
            desc_parts.insert(0, day_part)

        return " ".join(desc_parts) if desc_parts else expression

    except Exception:
        return expression


async def get_schedule_target_nodes(db, schedule: UpdateSchedule) -> list:
    """The outdated nodes a schedule updates (#665, #19367): the one selection for run-now and the timed run.

    Owner decision on #19367: a ``specific`` schedule touches only those of its selected nodes that are
    outdated, so one with no nodes selected touches none -- never the whole fleet. Any other target
    type (``all``, and ``tag``, which has no tag filter) updates every outdated node.
    """
    query = select(Node).where(Node.code_status == CodeStatus.OUTDATED.value)
    if schedule.target_type == "specific":
        query = query.where(Node.node_id.in_(schedule.target_nodes or []))
    result = await db.execute(query)
    return result.scalars().all()


def _format_sync_result(success_count: int, failed_count: int) -> Tuple[bool, str]:
    """
    Format the final result tuple based on sync counts.

    Helper for execute_schedule (Issue #665).
    """
    total = success_count + failed_count
    if failed_count == 0:
        return True, f"Successfully synced {success_count} node(s)"
    elif success_count == 0:
        return False, f"All {failed_count} node sync(s) failed"
    else:
        return True, f"Synced {success_count}/{total} nodes ({failed_count} failed)"


async def _queue_job(db, schedule: UpdateSchedule, nodes: list):
    """The fleet job for ``nodes``, or None when a fleet sync is already running (#1979)."""
    from api.code_sync import queue_schedule_job

    try:
        return await queue_schedule_job(db, schedule, nodes)
    except HTTPException:
        logger.warning("Skipping schedule '%s' — fleet sync already running (#1979)", schedule.name)
        return None


async def execute_schedule(schedule: UpdateSchedule) -> Tuple[bool, str]:
    """Run a due schedule through the fleet-sync job that run-now and update-all use (#19352).

    One deploy path: ``update-all-nodes.yml`` deploys autobot_shared before the agent and restarts
    it in the live agent dir. Awaited inline so ``last_run_status`` reports the job's real outcome.
    """
    from api.code_sync import _run_fleet_sync_job

    logger.info("Executing schedule: %s (id=%d)", schedule.name, schedule.id)
    try:
        async with db_service.session() as db:
            nodes = await get_schedule_target_nodes(db, schedule)
            if not nodes:
                logger.info("Schedule %s has no outdated nodes to sync", schedule.name)
                return True, "No outdated nodes to sync"
            job = await _queue_job(db, schedule, nodes)
        if job is None:
            return False, "Fleet sync already in progress"
        await _run_fleet_sync_job(job)
        statuses = [n.status for n in job.nodes.values()]
        return _format_sync_result(statuses.count("success"), len(statuses) - statuses.count("success"))
    except Exception as e:
        logger.error("Schedule %s execution failed: %s", schedule.name, e)
        return False, "Schedule execution failed"


async def check_and_execute_schedules() -> int:
    """
    Check all enabled schedules and execute any that are due.

    Returns:
        Number of schedules executed
    """
    now = datetime.now(timezone.utc)
    executed_count = 0

    try:
        async with db_service.session() as db:
            # Find schedules that are enabled and due for execution
            result = await db.execute(
                select(UpdateSchedule).where(
                    UpdateSchedule.enabled == True,  # noqa: E712
                    UpdateSchedule.next_run <= now,
                )
            )
            due_schedules = result.scalars().all()

            for schedule in due_schedules:
                logger.info(
                    "Schedule '%s' is due (next_run: %s)",
                    schedule.name,
                    schedule.next_run,
                )

                # Execute the schedule
                success, message = await execute_schedule(schedule)

                # Update schedule state
                schedule.last_run = now
                schedule.next_run = calculate_next_run(schedule.cron_expression, now)
                schedule.last_run_status = "success" if success else "failed"
                schedule.last_run_message = message

                executed_count += 1

                logger.info(
                    "Schedule '%s' completed: %s - %s (next: %s)",
                    schedule.name,
                    schedule.last_run_status,
                    message,
                    schedule.next_run,
                )

            if due_schedules:
                await db.commit()

    except Exception as e:
        logger.error("Schedule check failed: %s", e)

    return executed_count


async def _schedule_executor_loop():
    """
    Main loop that checks schedules every minute.

    This runs as a background task and checks for due schedules
    at the start of each minute.
    """
    global _executor_running

    logger.info("Schedule executor started")
    _executor_running = True
    await report_stored_schedules()

    while _executor_running:
        try:
            executed = await check_and_execute_schedules()
            if executed > 0:
                logger.info("Executed %d schedule(s) this cycle", executed)
        except Exception as e:
            logger.error("Schedule executor cycle failed: %s", e)

        # Sleep for 60 seconds (check once per minute)
        await asyncio.sleep(60)

    logger.info("Schedule executor stopped")


def start_schedule_executor():
    """
    Start the schedule executor background task.

    Should be called during application startup.
    """
    global _executor_task

    if _executor_task is not None and not _executor_task.done():
        logger.warning("Schedule executor already running")
        return

    _executor_task = asyncio.create_task(_schedule_executor_loop())
    logger.info("Schedule executor background task created")


def stop_schedule_executor():
    """
    Stop the schedule executor background task.

    Should be called during application shutdown.
    """
    global _executor_running

    _executor_running = False

    if _executor_task is not None and not _executor_task.done():
        _executor_task.cancel()
        logger.info("Schedule executor stop requested")
