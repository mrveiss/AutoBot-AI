# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Knowledge Base Factory - Breaks circular import between api/knowledge.py and app_factory.py"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

from autobot_shared.async_compat import fire_and_forget
from autobot_shared.env_utils import env_int_clamped
from autobot_shared.logging_manager import get_logger

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = get_logger(__name__)

# Module-level singleton for knowledge base instance (used when no app context available)
_knowledge_base_instance: "KnowledgeBase" | None = None  # noqa: F821
# #18122 / owner decision D6: this Lock is created at import and binds to the first event
# loop that contends on it, so it cannot be used from a second loop. That is a recorded
# exception, not an oversight: tasks/knowledge_tasks.py builds its KB inside a new loop
# (separate loop / worker process) and must not share this lock or this store.
_knowledge_base_lock = asyncio.Lock()

# Issue #3094/#3106: Retry cooldown — prevent hammering ChromaDB on repeated failures.
# After a failed init, wait KB_RETRY_COOLDOWN_SECONDS before attempting again.
KB_RETRY_COOLDOWN_SECONDS = env_int_clamped("AUTOBOT_KB_RETRY_COOLDOWN_SECONDS", 60, 1, 86400)
_last_kb_init_failure: float = 0.0


def _is_kb_initialized(kb) -> bool:
    """Check if knowledge base instance is properly initialized (Issue #315: extracted)."""
    if hasattr(kb, "initialized") and kb.initialized:
        return True
    if hasattr(kb, "_redis_initialized") and kb._redis_initialized:
        return True
    return False


def _log_kb_state(kb) -> None:
    """Log knowledge base state for debugging (Issue #315: extracted)."""
    logger.debug(
        f"Checking app.state.knowledge_base: initialized={getattr(kb, 'initialized', 'N/A')}, "
        f"_redis_initialized={getattr(kb, '_redis_initialized', 'N/A')}, "
        f"vector_store={kb.vector_store is not None if hasattr(kb, 'vector_store') else 'N/A'}, "
        f"llama_index_configured={getattr(kb, 'llama_index_configured', 'N/A')}"
    )


async def _try_initialize_existing_kb(kb, app: "FastAPI | None" = None):
    """Initialize an existing but uninitialized instance in place, under the lock (#18122).

    Readiness is re-checked inside the lock so concurrent callers run ``initialize()``
    once. Success goes through :func:`_accept_new_kb` (publish + adoption, D7); a
    ``False`` return or an exception stamps the retry cooldown and returns None.
    """
    global _last_kb_init_failure
    async with _knowledge_base_lock:
        if _is_kb_initialized(kb):
            return kb
        logger.info("Knowledge base exists but not initialized, initializing existing instance...")
        try:
            if await kb.initialize():
                return _accept_new_kb(kb, app)
            logger.error("❌ Existing KnowledgeBase initialization returned False")
        except Exception as init_error:
            logger.error("❌ Failed to initialize existing instance: %s", init_error, exc_info=True)
        _last_kb_init_failure = time.monotonic()
        return None


def _adopt_legacy_facts(kb) -> None:
    """Give a durable row to any fact that still exists only as a Redis hash (#15663).

    The migration creates ``knowledge_facts`` empty and cannot do otherwise — the
    migration gate has no Redis connection — so until this runs, a fact created
    before #15663 is still Redis-only and the durable system of record is a
    promise about future writes. Fire-and-forget: a slow scan must not delay the
    knowledge base, and a failure leaves the facts exactly where they already were.
    The ownerless-document visibility backfill (#16693) follows it.
    """
    if kb is not None and hasattr(kb, "adopt_legacy_facts"):
        fire_and_forget(_adopt_then_backfill(kb), name="kb-adopt-legacy-facts")


async def _adopt_then_backfill(kb) -> None:
    """Adopt Redis-only facts, then make ownerless ingested documents explicitly SYSTEM (#16693).

    In that order because the backfill walks the durable rows: a fact still only in
    Redis would be missed. The builtin updater restarts the backend after an update, so
    this is how the backfill ships; a later start retries only the updates that failed.
    """
    await kb.adopt_legacy_facts()
    await kb.backfill_document_visibility()


def _publish_knowledge_base(kb, app: "FastAPI | None" = None) -> None:
    """Record ``kb`` as the one store, projecting it onto app state when there is an app.

    #18122: the module singleton is the system of record; ``app.state.knowledge_base``
    is a rebuildable projection of it. Both creation paths land here, so an instance
    built with an app is visible to the app-less callers and the reverse. Before this,
    the lifespan path set only app state, which left ``peek_knowledge_base()`` reporting
    no instance and made ``get_knowledge_base_async()`` construct a second store.
    """
    global _knowledge_base_instance
    _knowledge_base_instance = kb
    if app is not None:
        app.state.knowledge_base = kb


def _accept_new_kb(kb, app: "FastAPI | None"):
    """Reset the cooldown, publish ``kb`` and start legacy-fact adoption (#18122, D7).

    The one place a freshly built instance becomes the store, so adoption and the
    document-visibility backfill start exactly once, on whichever path created first.
    """
    global _last_kb_init_failure
    _last_kb_init_failure = 0.0
    _publish_knowledge_base(kb, app)
    _adopt_legacy_facts(kb)
    logger.info("✅ Knowledge base created and initialized (unified KnowledgeBase with ChromaDB)")
    return kb


async def _create_new_knowledge_base(app: "FastAPI | None" = None):
    """Build and initialize a KnowledgeBase, publishing it on success (Issue #315).

    Call only through :func:`_create_under_lock`. Every failure stamps the retry
    cooldown (Issue #3094/#3106), whichever entry point asked.

    Returns:
        Initialized kb on success, None on failure
    """
    global _last_kb_init_failure
    try:
        from knowledge_base import KnowledgeBase

        logger.info("Creating KnowledgeBase with ChromaDB vector store...")
        kb = KnowledgeBase()
        logger.info("Initializing KnowledgeBase...")
        if await kb.initialize():
            return _accept_new_kb(kb, app)
        logger.error("❌ KnowledgeBase initialization returned False")
    except ImportError as import_error:
        logger.error("❌ CRITICAL: KnowledgeBase not available: %s", import_error, exc_info=True)
    except Exception as init_error:
        logger.error("❌ CRITICAL: KnowledgeBase initialization failed: %s", init_error, exc_info=True)
    _last_kb_init_failure = time.monotonic()
    return None


def _cooldown_remaining() -> float:
    """Seconds left of the post-failure retry cooldown; 0.0 when none is active."""
    if _last_kb_init_failure <= 0.0:
        return 0.0
    return max(0.0, KB_RETRY_COOLDOWN_SECONDS - (time.monotonic() - _last_kb_init_failure))


async def _create_under_lock(app: "FastAPI | None" = None, force_refresh: bool = False):
    """The one creation path for both public accessors (#18122).

    Under ``_knowledge_base_lock``: adopt an initialized singleton first (adoption
    initializes nothing, so a recent failure must not withhold it), then honour the
    retry cooldown on every path (owner decision D2), then create and publish.
    ``force_refresh`` skips both, as the admin /reinit always did.
    """
    async with _knowledge_base_lock:
        existing = peek_knowledge_base()
        if existing is not None and not force_refresh:
            logger.info("Adopting the existing knowledge base singleton")
            _publish_knowledge_base(existing, app)
            return existing
        remaining = 0.0 if force_refresh else _cooldown_remaining()
        if remaining > 0.0:
            logger.warning("KB init cooldown active — skipping retry (%ds remaining)", int(remaining))
            # Contract (owner D2): None, not an error here. knowledge/_composed.
            # get_knowledge_base raises RuntimeError on None, which is how the error
            # reaches the llc/memory/mcp callers.
            return None
        return await _create_new_knowledge_base(app)


async def _ready_app_state_kb(app: "FastAPI"):
    """Return the app-state instance if it is the singleton and ready (Issue #315, #18122).

    ``app.state`` is a projection of the singleton, so it is served only while it IS the
    singleton. After an app-free ``reset_knowledge_base()`` (global None) an initialized
    projection is stale and falls through to the creation path, which republishes through
    the single writer. An uninitialized one is initialized in place only when it is the
    singleton or none exists yet (the bootstrap case); against a different live singleton
    it is dropped in favour of adopting that one.
    """
    kb = getattr(app.state, "knowledge_base", None)
    if kb is None:
        return None
    singleton = _knowledge_base_instance
    if singleton is not None and kb is not singleton:
        logger.info("App-state knowledge base is not the singleton; adopting the singleton")
        return None
    _log_kb_state(kb)
    if _is_kb_initialized(kb):
        if kb is not singleton:
            logger.info("App-state knowledge base outlived a reset; rebuilding from the singleton path")
            return None
        logger.info("Using existing initialized knowledge base from app state")
        return kb
    return await _try_initialize_existing_kb(kb, app)


async def get_or_create_knowledge_base(app: "FastAPI", force_refresh: bool = False):
    """Get or create a properly initialized knowledge base instance for the app.

    This is separated from app_factory to avoid circular imports with api/knowledge.py

    Issue #3094/#3106: after a failed init, re-attempts are suppressed for
    KB_RETRY_COOLDOWN_SECONDS; ``force_refresh`` bypasses it. #18122: creation goes
    through :func:`_create_under_lock`, shared with :func:`get_knowledge_base_async`.
    """
    try:
        if not force_refresh:
            ready = await _ready_app_state_kb(app)
            if ready is not None:
                return ready
        return await _create_under_lock(app, force_refresh)
    except Exception as e:
        logger.error("❌ Failed to get or create knowledge base: %s", e)
        return None


def peek_knowledge_base() -> "KnowledgeBase" | None:  # noqa: F821
    """Return the app-free singleton if it is already initialized, else None.

    Never constructs and never initializes -- the question is "is there one right now",
    which is what a synchronous caller and a status report can honestly ask. Use
    :func:`get_knowledge_base_async` when the answer should be "make one".

    Added for #18122 so `knowledge_base_factory` could become a facade over this store
    instead of keeping its own: a second module reaching into
    ``_knowledge_base_instance`` would make the private global a shared one in all but
    name, which is the fork this replaces.
    """
    if _knowledge_base_instance is None:
        return None
    return _knowledge_base_instance if _is_kb_initialized(_knowledge_base_instance) else None


async def get_knowledge_base_async() -> "KnowledgeBase" | None:  # noqa: F821
    """
    Get or create a knowledge base instance without requiring FastAPI app context (thread-safe).

    Uses a module-level singleton for cases where we don't have app access
    (e.g., ChatWorkflowManager initialization). Creation shares
    :func:`_create_under_lock` -- and so the retry cooldown -- with
    :func:`get_or_create_knowledge_base` (#18122).

    Returns:
        KnowledgeBase instance or None if initialization fails or is cooling down
    """
    try:
        existing = peek_knowledge_base()
        if existing is not None:
            logger.debug("Using existing knowledge base singleton")
            return existing
        return await _create_under_lock(None)
    except Exception as e:
        logger.error("❌ Failed to create knowledge base singleton: %s", e)
        return None


def reset_knowledge_base(app: "FastAPI | None" = None) -> None:
    """Clear the singleton through the publisher; the next access creates anew (#18122).

    Synchronous and lock-free like the old ``_composed`` reset (Issue #613): it only
    rebinds the global. Given an ``app`` it clears the ``app.state`` projection too, so
    ``get_or_create_knowledge_base(app)`` cannot keep serving the instance the app-free
    path just dropped. The retry cooldown is left as it was.
    """
    _publish_knowledge_base(None, app)
    logger.info("KnowledgeBase singleton instance reset")
