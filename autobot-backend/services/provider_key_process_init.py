# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Provider-key hydration for every process that is not the backend lifespan (#18094).

The lifespan hydrates in Phase 1. Every other process that resolves a provider key -- a
Celery worker, a CLI or operator script that builds a KnowledgeBase or an LLM provider, the
knowledge-base MCP server, anything importing the backend outside uvicorn -- would otherwise
resolve with the vault unread and serve the environment for a key the vault holds. Two hooks
close that:

* :func:`hydrate_this_process` runs on first resolution in any process that has not hydrated --
  with or without a root key, since listing rows needs none -- and again, with exponential
  backoff, while the vault is unreachable (``provider_key_vault.resolve_provider_key`` calls it),
  so no entry point needs to remember. A DB that cannot be reached is an outage: keys are refused.
* ``celery_app`` also calls it from ``worker_process_init``, so a worker reads the vault before
  its first task rather than on it.

It runs on ``user_management.database.isolated_session_factory`` (unpooled, disposed) in a private
event loop on its own thread:
safe to call from sync code or from inside a running loop, and it never leaves connections
bound to a loop that is about to close. It never raises (``hydrate_at_startup`` classifies a
failure as an outage, which refuses keys).
"""

from __future__ import annotations

import asyncio
import threading
import time

from autobot_shared.env_utils import env_int
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

_lock = threading.Lock()

#: Bounded wait for one hydration; a timeout fails closed (keys refused) and releases the lock.
HYDRATION_TIMEOUT_S = env_int("AUTOBOT_PROVIDER_KEY_HYDRATION_TIMEOUT_S", 30)
#: First retry delay after an unreachable vault; doubles per failed retry up to 20x.
REHYDRATE_BACKOFF_S = env_int("AUTOBOT_PROVIDER_KEY_REHYDRATE_BACKOFF_S", 30)
_MAX_BACKOFF_FACTOR = 20

_next_retry_at = 0.0
_backoff_s = float(REHYDRATE_BACKOFF_S)


def hydrate_this_process() -> list[str]:
    """Hydrate when this process has not, or when an unreachable vault is due a retry; else no-op.

    Concurrent callers serialise on the lock and the later ones see the settled state.
    """
    from services import provider_key_vault as vault

    with _lock:
        if not _due(vault):
            return []
        hydrated = _run_bounded(vault)
        _schedule_retry(vault)
        return hydrated


def _due(vault) -> bool:
    if vault._vault_state == vault.VAULT_NOT_HYDRATED:
        return True
    return vault._vault_state == vault.VAULT_UNREACHABLE and time.monotonic() >= _next_retry_at


def _run_bounded(vault) -> list[str]:
    """One hydration on a daemon thread, waited for at most HYDRATION_TIMEOUT_S; fail closed otherwise."""
    result: list[list[str]] = []
    worker = threading.Thread(
        target=lambda: result.append(asyncio.run(_hydrate_on_private_engine())),
        name="provider-key-hydration",
        daemon=True,
    )
    worker.start()
    worker.join(HYDRATION_TIMEOUT_S)
    if result:
        return result[0]
    # Timed out, or the thread died outside hydrate_at_startup's classification. A late
    # finish still swaps its result in and sets the state itself.
    vault._vault_state = vault.VAULT_UNREACHABLE
    logger.error(
        "provider-key hydration %s; every vault-resolved provider key is refused",
        "timed out" if worker.is_alive() else "thread failed",
    )
    return []


def _schedule_retry(vault) -> None:
    """Back off exponentially while unreachable; reset once the vault answers."""
    global _next_retry_at, _backoff_s
    if vault._vault_state == vault.VAULT_UNREACHABLE:
        _next_retry_at = time.monotonic() + _backoff_s
        _backoff_s = min(_backoff_s * 2, REHYDRATE_BACKOFF_S * _MAX_BACKOFF_FACTOR)
    else:
        _next_retry_at, _backoff_s = 0.0, float(REHYDRATE_BACKOFF_S)


async def _hydrate_on_private_engine() -> list[str]:
    from services.provider_key_vault import hydrate_at_startup
    from user_management.database import isolated_session_factory

    result: list[str] | None = None
    try:
        async with isolated_session_factory() as factory:
            result = await hydrate_at_startup(lambda: factory)
    except Exception as exc:  # noqa: BLE001 - classified below, never raised
        if result is not None:  # hydration finished; only disposing the private engine failed
            logger.warning("provider-key hydration: private engine dispose failed (%s)", type(exc).__name__)
            return result
        return await hydrate_at_startup(_raise(exc))  # building the engine is the DB too: an outage
    return result


def _raise(exc: Exception):
    """A session-factory getter that re-raises *exc*, so hydrate_at_startup classifies it as an outage."""

    def _getter():
        raise exc

    return _getter
