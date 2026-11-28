# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One worker interprets each approved command's result, whichever worker ran it (#21202).

The earlier ``live_turn_interpreting`` flag lived in one worker's copy of the session: the worker that ran the
command could hold a stale value, skip its interpretation and leave nobody interpreting. Ownership now lives in
one Redis key per session, changed only by compare-and-set in Lua. Whoever swaps it to ``done`` interprets;
every other path skips.

* ``register_turn``: the polling chat turn writes ``turn:<token>``;
* ``take_for_turn``: the turn, having the result, swaps its token (or an absent key) for ``done``;
* ``release_turn``: the turn leaves, dropping its token only while it is still the owner;
* ``take_for_command``: the worker that ran the command swaps an absent key for ``done``; it waits a bounded time
  for a live turn to take the result, then swaps *that turn's token* for ``done`` itself. A turn that is slower
  than the deadline finds ``done`` and skips.
"""

from __future__ import annotations

import asyncio

from autobot_shared.env_utils import env_float, env_int
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_utils import delete_if_value

from .redis_usability import usable_redis
from .session_state import DECISION_TTL_SECONDS, ApprovalStateUnavailableError

logger = get_logger(__name__)

#: How long an ownership key lives. A turn that dies without releasing frees it after this long.
INTERPRETATION_TTL_SECONDS: int = env_int("AUTOBOT_APPROVAL_INTERPRETATION_TTL_SECONDS", default=DECISION_TTL_SECONDS)

#: How long the worker that ran a command waits for a live turn to take the interpretation before it takes it.
INTERPRETATION_HANDOFF_SECONDS: float = env_float("AUTOBOT_APPROVAL_INTERPRETATION_HANDOFF_SECONDS", default=15.0)

#: How often the waiting worker re-reads the key.
INTERPRETATION_RECHECK_SECONDS: float = env_float("AUTOBOT_APPROVAL_INTERPRETATION_RECHECK_SECONDS", default=0.25)

TAKEN = "taken"
DONE = "done"
TURN_PREFIX = "turn:"

#: Swap the key for ``done`` if it is absent or still holds ARGV[1] (the caller's expectation; '' = absent only).
#: Otherwise report what it holds: ``done``, or another owner's ``turn:<token>``.
TAKE_LUA = """
local v = redis.call('GET', KEYS[1])
if not v or (ARGV[1] ~= '' and v == ARGV[1]) then
  redis.call('SET', KEYS[1], 'done', 'EX', tonumber(ARGV[2]))
  return 'taken'
end
return v
"""

#: Register a turn: only while no one has taken the result. An absent key or an earlier turn's token is replaced;
#: ``done`` is never overwritten, so a turn that registers after the command finished cannot interpret it again.
REGISTER_TURN_LUA = """
local v = redis.call('GET', KEYS[1])
if v == 'done' then
  return 0
end
redis.call('SET', KEYS[1], ARGV[1], 'EX', tonumber(ARGV[2]))
return 1
"""


def interpretation_key(session_id: str, command_id: str | None) -> str:
    """One key per approval, so a ``done`` of one command never decides another's interpretation."""
    return f"agent_terminal:interpretation:{session_id}:{command_id or 'unidentified'}"


def _require(redis) -> None:
    if not usable_redis(redis):
        raise ApprovalStateUnavailableError("no usable Redis client")


async def _swap(redis, session_id: str, command_id: str | None, expected: str) -> str:
    """Compare-and-set the key to ``done``; the result is ``taken`` or what the key held instead."""
    held = await redis.eval(
        TAKE_LUA, 1, interpretation_key(session_id, command_id), expected, INTERPRETATION_TTL_SECONDS
    )
    return held.decode("utf-8") if isinstance(held, bytes) else held


async def register_turn(redis, session_id: str, command_id: str | None, token: str) -> bool:
    """The polling turn becomes the interpreter; ``False`` if the command's result was taken already."""
    _require(redis)
    key = interpretation_key(session_id, command_id)
    return bool(await redis.eval(REGISTER_TURN_LUA, 1, key, TURN_PREFIX + token, INTERPRETATION_TTL_SECONDS))


async def take_for_turn(redis, session_id: str, command_id: str | None, token: str) -> bool:
    """The turn has the result: ``True`` if it won the interpretation, ``False`` if the command's worker did."""
    _require(redis)
    return await _swap(redis, session_id, command_id, TURN_PREFIX + token) == TAKEN


async def release_turn(redis, session_id: str, command_id: str | None, token: str) -> None:
    """The turn is leaving: drop its token while it still owns the key, so the command's worker no longer waits for it.

    ``done`` and a newer turn's token are left alone (``delete_if_value`` compares the exact value).
    """
    _require(redis)
    await delete_if_value(redis, interpretation_key(session_id, command_id), TURN_PREFIX + token)


async def take_for_command(redis, session_id: str, command_id: str | None) -> bool:
    """The command has finished: ``True`` if this worker must interpret its result.

    A live turn gets ``INTERPRETATION_HANDOFF_SECONDS`` to take it; after that this worker swaps that turn's
    token for ``done``, so the turn's own later swap fails. No Redis call is cancelled mid-swap: the deadline
    is checked between swaps, so a swap that landed is never lost.
    """
    _require(redis)
    deadline = asyncio.get_running_loop().time() + INTERPRETATION_HANDOFF_SECONDS
    while True:
        state = await _swap(redis, session_id, command_id, "")
        if not state.startswith(TURN_PREFIX):
            return state == TAKEN
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            break
        await asyncio.sleep(min(INTERPRETATION_RECHECK_SECONDS, remaining))
    logger.warning("Turn on session %s did not take the interpretation in time; taking it over", session_id)
    return await _take_over(redis, session_id, command_id)


async def _take_over(redis, session_id: str, command_id: str | None) -> bool:
    """Swap the turn still holding the key for ``done``; ``False`` if the turn, or another owner, got there first."""
    state = await _swap(redis, session_id, command_id, "")
    if state.startswith(TURN_PREFIX):
        state = await _swap(redis, session_id, command_id, state)
    return state == TAKEN
