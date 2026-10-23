# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Single-flight refresh and failure backoff for signed-in LLM provider tokens (#19241).

**Single flight.** Providers that rotate refresh tokens accept each one once.
Two concurrent LLM calls refreshing the same (provider, subject) would both
POST the same refresh token; the second gets ``invalid_grant`` and the pair can
be lost. So a refresh runs under an in-process ``asyncio.Lock`` (one coroutine
per worker reaches the lease) and the cross-worker lease the connector refresh
already uses (``knowledge.connectors.credential_store.refresh_lease``, #13627,
a ``LeaderLease`` on the canonical Redis client). After acquiring, the stored
token is re-read: when another caller already refreshed, its token is used and
no POST is made. A worker that loses the lease waits for the holder's write.

**Backoff.** A (provider, subject) whose refresh failed is skipped for
``UNUSABLE_TTL_SECONDS`` (env ``AUTOBOT_LLM_OAUTH_UNUSABLE_TTL_SECONDS``,
floored at 60 s), so a failing provider is not re-POSTed on every call.
Resolution moves straight to the next source while it is cached. The cache is
per process; ``invalid_grant`` is also recorded on the stored token itself
(``NEEDS_REAUTH_KEY``), which every worker and /status read.
"""

from __future__ import annotations

import asyncio
import time
from typing import Awaitable, Callable, Optional

from autobot_shared.env_utils import env_int_clamped
from autobot_shared.logging_manager import get_logger

from .provider_token_response import ProviderAuthError

logger = get_logger(__name__)

UNUSABLE_TTL_SECONDS = env_int_clamped("AUTOBOT_LLM_OAUTH_UNUSABLE_TTL_SECONDS", 300, min_v=60)

_unusable_until: dict[tuple[str, str], float] = {}
_local_locks: dict[tuple[str, str], asyncio.Lock] = {}


class RefreshWaitTimeout(ProviderAuthError):
    """Another worker's refresh did not land in time. Not a refresh failure: no backoff."""


ReadFresh = Callable[[], Awaitable[Optional[str]]]
Refresh = Callable[[], Awaitable[str]]


def is_backed_off(provider_name: str, subject: str) -> bool:
    """True while a recent refresh failure for (provider, subject) is cached."""
    until = _unusable_until.get((provider_name, subject))
    if until is None:
        return False
    if time.monotonic() < until:
        return True
    _unusable_until.pop((provider_name, subject), None)
    return False


def mark_unusable(provider_name: str, subject: str) -> None:
    """Skip (provider, subject) for ``UNUSABLE_TTL_SECONDS``."""
    _unusable_until[(provider_name, subject)] = time.monotonic() + UNUSABLE_TTL_SECONDS


def lock_id(provider_name: str, subject: str) -> str:
    """The lease identity; ``refresh_lease`` hashes it before it becomes a Redis key."""
    return f"llm-provider-token:{provider_name}:{subject}"


def _lease(provider_name: str, subject: str):
    from knowledge.connectors.credential_store import refresh_lease  # noqa: PLC0415  # lazy: heavy module

    return refresh_lease(lock_id(provider_name, subject))


async def _lease_is_held(provider_name: str, subject: str) -> bool:
    """Another worker holds the lease (True) vs. there is no Redis to hold it in (False)."""
    from knowledge.connectors.credential_store import ConnectorCredentialStore  # noqa: PLC0415

    return await ConnectorCredentialStore._refresh_lock_available(lock_id(provider_name, subject))


async def _release(lease) -> None:
    from knowledge.connectors.credential_store import _release_quietly  # noqa: PLC0415

    await _release_quietly(lease)


async def _await_holder(provider_name: str, subject: str, read_fresh: ReadFresh) -> str:
    """Poll the stored token until the lease holder's refresh lands; never refresh ourselves."""
    from knowledge.connectors.credential_store import _refresh_poll_s, _refresh_wait_s  # noqa: PLC0415

    deadline = time.monotonic() + _refresh_wait_s()
    delay = _refresh_poll_s()
    while time.monotonic() < deadline:
        await asyncio.sleep(delay)
        delay = min(delay * 2, 2.0)
        token = await read_fresh()
        if token:
            return token
    raise RefreshWaitTimeout(f"timed out waiting for a concurrent {provider_name} token refresh")


async def _under_lease(provider_name: str, subject: str, read_fresh: ReadFresh, refresh: Refresh) -> str:
    lease = _lease(provider_name, subject)
    if await lease.update_leadership():
        try:
            return await read_fresh() or await refresh()  # double-checked: the holder may just have finished
        finally:
            await _release(lease)
    if await _lease_is_held(provider_name, subject):
        return await _await_holder(provider_name, subject, read_fresh)
    logger.warning("%s token refresh could not be serialized across workers (no Redis)", provider_name)
    return await read_fresh() or await refresh()


async def single_flight_refresh(provider_name: str, subject: str, read_fresh: ReadFresh, refresh: Refresh) -> str:
    """Return a fresh token for (provider, subject), refreshing at most once across callers.

    *read_fresh* re-reads the stored token and returns it only if it needs no
    refresh; *refresh* refreshes, persists and commits (it runs under the lease).
    """
    lock = _local_locks.setdefault((provider_name, subject), asyncio.Lock())
    async with lock:
        token = await read_fresh()  # a coroutine in this worker may have refreshed while we queued
        if token:
            return token
        return await _under_lease(provider_name, subject, read_fresh, refresh)


__all__ = [
    "RefreshWaitTimeout",
    "UNUSABLE_TTL_SECONDS",
    "is_backed_off",
    "lock_id",
    "mark_unusable",
    "single_flight_refresh",
]
