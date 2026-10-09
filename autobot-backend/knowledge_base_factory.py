# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Knowledge Base Factory — a facade over the canonical app-free singleton (#18122).

This module used to own a THIRD independent `KnowledgeBase` store. There were three:

    knowledge/_composed.py      _knowledge_base_instance   module global + asyncio.Lock
    knowledge_factory.py        _knowledge_base_instance   module global, same NAME
    knowledge_base_factory.py   KnowledgeBaseInitializer._instance

Two of those module names differ by one word, and two of the globals had the identical
name in different modules. #13026 was the direct consequence: a caller reached the wrong
`get_knowledge_base` and every request raised `TypeError` on a `config_manager` kwarg
the other one does not accept.

`autobot_shared.store_authority` forbids this shape — one store is the system of record
and every other copy is a rebuildable projection. Two live stores meant a fact written
through one was invisible through the other, each with its own ChromaDB client,
embedding cache and ownership manager.

So every name here is kept and wired, and none of them holds state any more: they all
resolve `knowledge_factory`'s app-free singleton. Nothing is deleted, because the names
are the module's contract and `get_knowledge_base` has live callers; what is removed is
the second store behind them.

Measured before rewriting: of the seven exports, exactly ONE is consumed —
`get_knowledge_base`, at five call sites, every one of them zero-argument
(`ai_hardware_accelerator.py:822`, `async_chat_workflow.py:224`,
`services/codebase_indexing_service.py:875,949`,
`services/research/orchestrator.py:329`). So the `force_reinit` and `timeout`
parameters were never passed by anyone, and the rest of the surface was unwired. The
signatures are kept anyway — an unused parameter is not a reason to break a caller that
may appear, and `timeout` still bounds the wait.

The race-condition guarantee the original docstring was written for is preserved, not
dropped: `knowledge_factory.get_knowledge_base_async` holds an `asyncio.Lock` across the
create-and-initialize window and double-checks the global after acquiring it.

Usage:
    from knowledge_base_factory import get_knowledge_base

    kb = await get_knowledge_base()
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, Dict

from autobot_shared.logging_manager import get_logger
from constants.threshold_constants import TimingConstants
from knowledge_factory import get_knowledge_base_async, peek_knowledge_base

if TYPE_CHECKING:
    from knowledge_base import KnowledgeBase

logger = get_logger(__name__)


class KnowledgeBaseInitializer:
    """A read-through view of the canonical singleton (#18122).

    Was the owner of `_instance`, an independent third store. The class name is kept
    because it is exported, but it no longer holds anything: every method answers from
    `knowledge_factory`. There is deliberately no `_instance` attribute, so a read of it
    raises `AttributeError` rather than silently returning a stale copy — and
    `repo_tests/one_knowledge_base_store_18122_test.py` fails if any instance state
    reappears here.
    """

    @classmethod
    async def get_instance(cls, force_reinit: bool = False) -> "KnowledgeBase" | None:
        """Resolve the canonical singleton, initializing it if needed.

        `force_reinit` is accepted for signature compatibility and ignored: tearing down
        a process-wide store that other modules hold references to is not something a
        convenience accessor should do, and no caller has ever passed it. Use
        `knowledge_factory.get_or_create_knowledge_base(app, force_refresh=True)`, which
        owns `app.state`, when a genuine rebuild is wanted.
        """
        if force_reinit:
            logger.warning(
                "KnowledgeBaseInitializer.get_instance(force_reinit=True) ignored (#18122) — "
                "use knowledge_factory.get_or_create_knowledge_base(app, force_refresh=True)"
            )
        return await get_knowledge_base_async()

    @classmethod
    async def wait_for_initialization(cls, timeout: float = TimingConstants.SHORT_TIMEOUT) -> "KnowledgeBase" | None:
        """Wait up to ``timeout`` for the canonical singleton to become available.

        The original waited on an `asyncio.Event` this module set itself. With one store
        there is no local event to wait on, so this bounds the canonical resolve instead
        — same contract to a caller: an instance, or None on timeout.
        """
        try:
            return await asyncio.wait_for(get_knowledge_base_async(), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning("Knowledge base initialization timed out after %ss", timeout)
            return None

    @classmethod
    def is_initialized(cls) -> bool:
        """True when an initialized instance exists right now. Never constructs one."""
        return peek_knowledge_base() is not None

    @classmethod
    def get_initialization_status(cls) -> Dict[str, Any]:
        """Status of the canonical singleton.

        `failed` and `error` are no longer tracked here. They described THIS module's
        own failed-init bookkeeping, and reporting a local flag about a store it no
        longer owns would be a measurement of the wrong thing — the honest answer is
        that this facade does not know, so it does not claim.
        """
        instance = peek_knowledge_base()
        return {
            "initialized": instance is not None,
            "instance_exists": instance is not None,
            "owner": "knowledge_factory",
        }


async def get_knowledge_base(
    force_reinit: bool = False, timeout: float = TimingConstants.SHORT_TIMEOUT
) -> "KnowledgeBase" | None:
    """Get the knowledge base, initializing it if needed. None when unavailable.

    The one export of this module with live callers. All five pass no arguments.
    """
    try:
        return await asyncio.wait_for(KnowledgeBaseInitializer.get_instance(force_reinit), timeout=timeout)
    except asyncio.TimeoutError:
        logger.warning("Knowledge base resolve timed out after %ss", timeout)
        return None
    except Exception as e:
        logger.error("Failed to get knowledge base: %s", e)
        return None


def get_knowledge_base_sync() -> "KnowledgeBase" | None:
    """The existing instance only — never initializes. None when there is none."""
    instance = peek_knowledge_base()
    if instance is None:
        logger.warning("Knowledge base not initialized - use async get_knowledge_base() for initialization")
    return instance


@asynccontextmanager
async def knowledge_base_context(timeout: float = TimingConstants.SHORT_TIMEOUT):
    """Async context manager yielding the knowledge base; raises if unavailable."""
    kb = None
    try:
        kb = await get_knowledge_base(timeout=timeout)
        if kb is None:
            raise RuntimeError("Failed to initialize knowledge base")
        yield kb
    except Exception as e:
        logger.error("Knowledge base context error: %s", e)
        raise
    finally:
        # Nothing to release: the instance is process-wide and outlives this block.
        pass


async def initialize_knowledge_base_background():
    """Warm the canonical singleton without blocking the caller's result."""
    try:
        logger.info("Starting background knowledge base initialization...")
        await get_knowledge_base()
        logger.info("Background knowledge base initialization completed")
    except Exception as e:
        logger.error("Background knowledge base initialization failed: %s", e)


def start_background_initialization():
    """Start the warm-up as a task. Returns the task, or None if it could not start."""
    try:
        task = asyncio.create_task(initialize_knowledge_base_background())
        logger.info("Knowledge base background initialization task created")
        return task
    except Exception as e:
        logger.error("Failed to start background initialization: %s", e)
        return None


async def health_check() -> Dict[str, Any]:
    """Health of the canonical knowledge base. Never initializes it to answer."""
    status = KnowledgeBaseInitializer.get_initialization_status()
    kb = peek_knowledge_base()

    if kb is None:
        status["health"] = "not_initialized"
        return status

    try:
        status.update(
            {
                "redis_connection": await kb.ping_redis() if hasattr(kb, "ping_redis") else "unknown",
                "vector_store": "healthy" if kb.vector_store else "unavailable",
                "health": "healthy",
            }
        )
    except Exception as e:
        status.update({"health": "unhealthy", "health_error": str(e)})

    return status


__all__ = [
    "get_knowledge_base",
    "get_knowledge_base_sync",
    "knowledge_base_context",
    "initialize_knowledge_base_background",
    "start_background_initialization",
    "health_check",
    "KnowledgeBaseInitializer",
]
