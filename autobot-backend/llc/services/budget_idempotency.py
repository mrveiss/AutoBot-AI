# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Charge a cost event at most once per (agent, idempotency key) (#21332).

One implementation for every caller of ``BudgetService.ingest_cost_event`` -- the HTTP route, the
native adapter and the scheduler -- built on the shared replay store in ``autobot_shared.idempotency``
(the same SET NX claim, fencing token and TTL the ``Idempotency-Key`` middleware uses; nothing here
re-implements it). Keys are namespaced by company and agent, so the same key on another agent charges.

Policies, each decided on purpose:

* **Concurrent duplicate while the first is in flight**: :class:`IngestInFlight` (the route answers 409).
  Waiting would hold a worker on an unbounded request; charging would be the double charge this prevents.
* **Redis unavailable or erroring**: fail OPEN -- charge without dedupe and log a warning. A budget must
  never be silently skipped; the cost of an outage is the duplicate protection, not the charge.
* **A hard stop (``BudgetExhausted``)** is a completed result: the spend was committed first (#20202), so
  the repeat re-raises the same refusal instead of charging again.
* **Any other failure** releases the claim: nothing was committed, and the retry must be able to run.
* **Commit before record**: the charge is committed before the replay record is written, so a stored
  result never points at a charge a later rollback erased.

The ``Idempotency-Key`` HTTP middleware also sees the header on the ingest route as a fast path (it caches
only 2xx); this layer is the authority because it also covers the adapter and the scheduler.

THE DATABASE IS THE AUTHORITY, REDIS IS THE FAST PATH (#21972)
--------------------------------------------------------------
``company_os_cost_events`` carries a unique (company_id, agent_id, idempotency_key) index, and the charge writes
that row in its own transaction BEFORE it touches spend. Only the transaction that inserts the row may change
spend; a loser hits the constraint (``CostEventAlreadyRecorded``), its charge never starts, and it replays the
winner's stored cost. This closes what the Redis claim alone could not:

* a claim that expires mid-charge (a second caller claims the same key; both reach the database, one wins);
* (a) a crash, or a failed ``_record``, after ``session.commit()`` -- the retry finds the row;
* (b) an ambiguous commit (raised or cancelled after the database committed) -- the retry finds the row.

Left as is: a replay answered from the database returns the first cost, not a repeat of a stored hard stop
(only the Redis record keeps the 402); a retry that lands inside window (a) still gets ``IngestInFlight`` until
the claim lapses, but can no longer double-charge.
"""

from __future__ import annotations

import asyncio
import json
from decimal import Decimal
from typing import Any, Awaitable, Callable, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.env_utils import env_float_clamped, env_int_clamped
from autobot_shared.idempotency import KeyClaim, ReplayedResponse, claim, complete, release_key, storage_key
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client
from llc.exceptions import BudgetExhausted

logger = get_logger(__name__)

#: Fixed "path" half of the storage key: namespaces budget-ingest keys apart from the HTTP middleware's.
_SCOPE = "budget.ingest_cost_event"
_OK, _EXHAUSTED = 200, 402

#: How often a caller with no HTTP client to retry for it (the native adapter) re-tries an in-flight ingest, and
#: the base delay between tries (doubles each attempt). Env-backed per the repository's constant rule.
INGEST_RETRY_ATTEMPTS = env_int_clamped("AUTOBOT_BUDGET_INGEST_RETRY_ATTEMPTS", 5, min_v=1, max_v=20)
INGEST_RETRY_DELAY_SECONDS = env_float_clamped("AUTOBOT_BUDGET_INGEST_RETRY_DELAY_SECONDS", 0.5, min_v=0.0, max_v=30.0)


class IngestInFlight(Exception):
    """The same (agent, key) is being charged by another caller right now."""


async def _redis_or_none() -> Optional[Any]:
    try:
        return await get_async_redis_client()
    except Exception:
        logger.warning("idempotency store unavailable: charging without dedupe", exc_info=True)
        return None


def _replay(agent_id: str, replayed: ReplayedResponse) -> Decimal:
    data = json.loads(replayed.body)
    if replayed.status_code == _EXHAUSTED:
        raise BudgetExhausted(agent_id=agent_id, spent=data["spent"], limit=data["limit"])
    return Decimal(data["cost"])


async def _record(redis: Any, key: str, token: str, status: int, payload: dict) -> None:
    try:
        await complete(redis, key, token, ReplayedResponse(status, json.dumps(payload).encode("utf-8")))
    except Exception:
        logger.warning("idempotency result not stored for %s; a retry may charge again", _SCOPE, exc_info=True)


async def _release(redis: Any, key: str, token: str) -> None:
    try:
        await release_key(redis, key, token)
    except Exception:
        logger.warning("idempotency claim not released; it lapses on its own TTL", exc_info=True)


async def _claim(redis: Any, key: str) -> Optional[KeyClaim]:
    try:
        return await claim(redis, key)
    except Exception:
        logger.warning("idempotency claim failed: charging without dedupe", exc_info=True)
        return None


async def charge_once(
    session: AsyncSession,
    agent_id: str,
    company_id: str,
    idempotency_key: str,
    charge: Callable[[], Awaitable[Decimal]],
) -> Decimal:
    """Run *charge* unless this (agent, key) already ran it; then return the first result."""
    redis = await _redis_or_none()
    if redis is None:
        logger.warning("idempotency store unavailable: charging without dedupe")
        return await charge()
    key = storage_key(f"{company_id}:{agent_id}", "POST", _SCOPE, idempotency_key)
    outcome = await _claim(redis, key)
    if outcome is None:
        return await charge()
    if outcome.replay is not None:
        return _replay(agent_id, outcome.replay)
    if outcome.in_flight or outcome.token is None:
        raise IngestInFlight(f"cost event {idempotency_key!r} for agent {agent_id} is still being charged")
    return await _run_claimed(redis, key, outcome.token, session, agent_id, charge)


async def _run_claimed(
    redis: Any, key: str, token: str, session: AsyncSession, agent_id: str, charge: Callable[[], Awaitable[Decimal]]
) -> Decimal:
    try:
        cost = await charge()
        await session.commit()
    except BudgetExhausted as exc:
        await _record(redis, key, token, _EXHAUSTED, {"spent": exc.spent, "limit": exc.limit})
        raise
    except BaseException:
        await _release(redis, key, token)
        raise
    await _record(redis, key, token, _OK, {"cost": str(cost)})
    return cost


async def retry_while_in_flight(ingest: Callable[[], Awaitable[Any]], run_id: str) -> None:
    """Run *ingest*, retrying with bounded backoff while another caller holds the same key (#21332).

    Safe because the database row (#21972) makes a repeat charge impossible. When the last attempt is still in
    flight the charge is NOT dropped silently: it is logged at error level with the run id.
    """
    for attempt in range(INGEST_RETRY_ATTEMPTS):
        try:
            await ingest()
            return
        except IngestInFlight:
            if attempt + 1 < INGEST_RETRY_ATTEMPTS:
                await asyncio.sleep(INGEST_RETRY_DELAY_SECONDS * (2**attempt))
    logger.error(
        "cost ingest for run %s still in flight after %d attempts; charge not confirmed", run_id, INGEST_RETRY_ATTEMPTS
    )
