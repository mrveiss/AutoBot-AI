# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Who may claim which member of ``llc:heartbeat:schedule`` (#19189).

One sorted set holds two kinds of member: a bare agent id (owned by
``LLCHeartbeatScheduler``) and ``routine:<uuid>`` (owned by ``RoutineScheduler``).
Both pollers read every due member and ``ZREM`` it before looking at what it is,
so whichever poller ticked first claimed the other's entry and then did nothing
with it: ``RoutineScheduler`` ignores a member without the ``routine:`` prefix,
and the heartbeat poller finds no agent row for ``routine:<uuid>``. The claimed
member is gone from the set and nothing re-adds it -- an enabled agent that
never fires again until the next restart, with no log line, which is exactly
the "set holds one routine and no CEO" observation. Each poller now filters the
due list to its own members *before* it claims anything.
"""

from typing import Any, Iterable, List

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

ROUTINE_MEMBER_PREFIX = "routine:"


def _is_routine_member(member: Any) -> bool:
    text = member.decode() if isinstance(member, bytes) else str(member)
    return text.startswith(ROUTINE_MEMBER_PREFIX)


def routine_due_members(due: Iterable[Any]) -> List[Any]:
    """The due members ``RoutineScheduler`` owns."""
    return [m for m in due if _is_routine_member(m)]


def agent_due_members(due: Iterable[Any]) -> List[Any]:
    """The due members ``LLCHeartbeatScheduler`` owns (everything that is not a routine)."""
    return [m for m in due if not _is_routine_member(m)]


async def drop_unschedulable_member(redis: Any, key: str, member: str, agent: Any) -> None:
    """Remove a due agent that cannot be woken, and say which of the two reasons it was.

    The removal was always silent, which made "dropped on purpose" and "lost" the same
    observation from the set. ``agent`` is the resolved row, or None when there is none.
    """
    await redis.zrem(key, member)
    reason = "no heartbeat-enabled agent row" if agent is None else "empty heartbeat cron"
    logger.warning("Heartbeat agent %s removed from the schedule: %s", member, reason)
