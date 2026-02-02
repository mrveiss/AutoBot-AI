# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Schedule Executor Service (Issue #741 - Phase 7).

Background task that checks schedules every minute and triggers syncs
when due. Integrates with the code sync system to execute scheduled
code deployments across the fleet.
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional, Tuple

from croniter import croniter
from sqlalchemy import select

from models.database import CodeStatus, Node, UpdateSchedule
from services.code_distributor import get_code_distributor
from services.database import db_service

logger = logging.getLogger(__name__)

# Module-level state
_executor_running = False
_executor_task: Optional[asyncio.Task] = None


def validate_cron_expression(expression: str) -> bool:
    """
    Validate a cron expression syntax.

    Args:
        expression: Cron expression string (e.g., "0 2 * * *")

    Returns:
        True if valid, False otherwise
    """
    try:
        croniter(expression)
        return True
    except (ValueError, KeyError):
        return False


def calculate_next_run(expression: str, base: datetime = None) -> datetime:
    """
    Calculate the next run time from a cron expression.

    Args:
        expression: Cron expression string
        base: Base datetime to calculate from (default: now)

    Returns:
        Next scheduled datetime
    """
    base = base or datetime.utcnow()
    cron = croniter(expression, base)
    return cron.get_next(datetime)


def describe_cron_expression(expression: str) -> str:
    """
    Generate a human-readable description of a cron expression.

    Args:
        expression: Cron expression string

    Returns:
        Human-readable description
    """
    try:
        parts = expression.split()
        if len(parts) != 5:
            return expression

        minute, hour, day, month, weekday = parts

        # Common patterns
        if expression == "0 * * * *":
            return "Every hour"
        elif expression == "0 0 * * *":
            return "Every day at midnight"
        elif expression == "0 2 * * *":
            return "Every day at 2:00 AM"
        elif expression == "0 0 * * 0":
            return "Every Sunday at midnight"
        elif expression == "0 0 1 * *":
            return "First day of every month"

        # Build description for other patterns
        desc_parts = []

        if minute == "0" and hour != "*":
            if hour.isdigit():
                h = int(hour)
                period = "AM" if h < 12 else "PM"
                h = h if h <= 12 else h - 12
                h = 12 if h == 0 else h
                desc_parts.append(f"at {h}:00 {period}")
            else:
                desc_parts.append(f"at hour {hour}")
        elif minute != "*":
            desc_parts.append(f"at minute {minute}")

        if day == "*" and month == "*" and weekday == "*":
            desc_parts.insert(0, "Daily")
        elif weekday != "*":
            days = {
                "0": "Sunday",
                "1": "Monday",
                "2": "Tuesday",
                "3": "Wednesday",
                "4": "Thursday",
                "5": "Friday",
                "6": "Saturday",
                "7": "Sunday",
            }
            if weekday in days:
                desc_parts.insert(0, f"Every {days[weekday]}")
            else:
                desc_parts.insert(0, f"On weekday {weekday}")

        return " ".join(desc_parts) if desc_parts else expression

    except Exception:
        return expression


async def execute_schedule(schedule: UpdateSchedule) -> Tuple[bool, str]:
    """
    Execute a single schedule - trigger sync for target nodes.

    Args:
        schedule: The UpdateSchedule model to execute

    Returns:
        Tuple of (success, message)
    """
    logger.info("Executing schedule: %s (id=%d)", schedule.name, schedule.id)

    try:
        async with db_service.session() as db:
            # Determine target nodes based on schedule configuration
            if schedule.target_type == "all":
                result = await db.execute(
                    select(Node).where(Node.code_status == CodeStatus.OUTDATED.value)
                )
            elif schedule.target_type == "specific" and schedule.target_nodes:
                result = await db.execute(
                    select(Node).where(
                        Node.node_id.in_(schedule.target_nodes),
                        Node.code_status == CodeStatus.OUTDATED.value,
                    )
                )
            else:
                # Default to all outdated nodes
                result = await db.execute(
                    select(Node).where(Node.code_status == CodeStatus.OUTDATED.value)
                )

            nodes = result.scalars().all()

            if not nodes:
                logger.info("Schedule %s has no outdated nodes to sync", schedule.name)
                return True, "No outdated nodes to sync"

            # Get the code distributor
            distributor = get_code_distributor()

            # Sync each node
            success_count = 0
            failed_count = 0

            for node in nodes:
                try:
                    success, message = await distributor.trigger_node_sync(
                        node_id=node.node_id,
                        ip_address=node.ip_address,
                        ssh_user=node.ssh_user or "autobot",
                        ssh_port=node.ssh_port or 22,
                        restart=schedule.restart_after_sync,
                        strategy=schedule.restart_strategy,
                    )

                    if success:
                        success_count += 1
                    else:
                        failed_count += 1
                        logger.warning(
                            "Schedule %s: Node %s sync failed: %s",
                            schedule.name,
                            node.node_id,
                            message,
                        )

                    # Brief pause between nodes for rolling strategy
                    await asyncio.sleep(2)

                except Exception as e:
                    failed_count += 1
                    logger.error(
                        "Schedule %s: Node %s sync error: %s",
                        schedule.name,
                        node.node_id,
                        e,
                    )

            total = success_count + failed_count
            if failed_count == 0:
                return True, f"Successfully synced {success_count} node(s)"
            elif success_count == 0:
                return False, f"All {failed_count} node sync(s) failed"
            else:
                return (
                    True,
                    f"Synced {success_count}/{total} nodes ({failed_count} failed)",
                )

    except Exception as e:
        logger.error("Schedule %s execution failed: %s", schedule.name, e)
        return False, str(e)


async def check_and_execute_schedules() -> int:
    """
    Check all enabled schedules and execute any that are due.

    Returns:
        Number of schedules executed
    """
    now = datetime.utcnow()
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
    global _executor_running, _executor_task

    _executor_running = False

    if _executor_task is not None and not _executor_task.done():
        _executor_task.cancel()
        logger.info("Schedule executor stop requested")
