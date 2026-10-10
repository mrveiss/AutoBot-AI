#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Resource Factory - Centralized management of expensive shared resources
Provides singleton-like behavior with app.state integration for optimal performance
"""

from fastapi import Request

from autobot_shared.logging_manager import get_logger
from constants.network_constants import NetworkConstants

logger = get_logger(__name__)


class ResourceFactory:
    """Factory for managing expensive shared resources with caching"""

    @staticmethod
    async def get_knowledge_base(request: Request = None):
        """Get the app-wide initialized KnowledgeBase, or the app-free singleton.

        #18121: this used to construct ``KnowledgeBase()`` directly and write it to
        ``request.app.state.knowledge_base``. ``initialize()`` must be awaited after
        construction — it is what creates the vector store — so the instance handed back
        had ``initialized is False`` and would raise out of ``ensure_initialized()`` on
        first use. Worse, caching it replaced the store that every ``api/knowledge*.py``
        route reads, so one call here could break knowledge search process-wide.

        Both branches now go through ``knowledge_factory``, which initializes before
        returning and honours the #3094/#3106 retry cooldown, so no caller can receive an
        uninitialized instance and ``app.state`` is only ever written by the factory that
        owns it.

        Returns:
            The initialized ``KnowledgeBase``, or ``None`` when it is unavailable.
        """
        try:
            if request is not None:
                from knowledge_factory import get_or_create_knowledge_base

                return await get_or_create_knowledge_base(request.app)

            # No app context (background task, scheduler): the module-level singleton.
            from knowledge_factory import get_knowledge_base_async

            return await get_knowledge_base_async()

        except Exception as e:
            logger.error("Failed to resolve KnowledgeBase: %s", e)
            raise

    @staticmethod
    async def get_llm_interface(request: Request = None):
        """Get or create LLMService instance with app.state caching"""
        try:
            # Try app.state first
            if request is not None:
                llm = getattr(request.app.state, "llm_interface", None)
                if llm is not None:
                    logger.debug("Using pre-initialized LLMService from app.state")
                    return llm

            # Fallback to singleton accessor
            from services.llm_service import get_llm_service

            logger.info("Returning LLMService singleton")

            llm = get_llm_service()

            # Cache in app state if available
            if request is not None:
                request.app.state.llm_interface = llm
                logger.info("Cached LLMService in app.state for future requests")

            return llm

        except Exception as e:
            logger.error("Failed to get LLMService: %s", e)
            raise

    @staticmethod
    async def get_orchestrator(request: Request = None):
        """Get the shared Orchestrator singleton.

        Issue #2207: Delegates to module-level singleton.
        Issue #5038: Renamed from get_enhanced_orchestrator → get_orchestrator.
        The request parameter is kept for backward compatibility but no longer
        used for app.state caching — the singleton handles its own lifecycle.
        """
        from orchestrator import get_orchestrator_sync

        return get_orchestrator_sync()

    @staticmethod
    def get_initialized_chat_history_manager():
        """Return the process-wide ChatHistoryManager, or None — never constructs one.

        Issue #13686: request-free callers (the chat workflow manager runs outside
        any request scope) need the *same* manager the app initialised at startup,
        because that is the object that owns the initialised ``memory_graph``
        (``chat_history/base.py:166`` → ``_init_memory_graph``). Constructing a
        second manager would build a second ``AutoBotMemoryGraph``, which is
        exactly the duplicate-concept outcome #13686 forbids.

        ``initialization.lifespan.app_state`` is the canonical request-free mirror
        of ``app.state`` (written at ``lifespan.py:160``, already read this way by
        ``api/system.py``). Returns None before startup completes or outside an
        app process, so callers must degrade rather than assume.
        """
        try:
            from initialization.lifespan import app_state

            return app_state.get("chat_history_manager")
        except Exception as exc:  # pragma: no cover - import guard only
            logger.debug("No process-wide ChatHistoryManager available: %s", exc)
            return None

    @staticmethod
    async def get_chat_history_manager(request: Request = None):
        """Get or create ChatHistoryManager instance with app.state caching"""
        try:
            # Try app.state first
            if request is not None:
                chm = getattr(request.app.state, "chat_history_manager", None)
                if chm is not None:
                    logger.debug("Using pre-initialized ChatHistoryManager from app.state")
                    return chm

            # Fallback to module-level import and creation
            from chat_history import ChatHistoryManager

            # `config.config` is the SSOT AutoBotConfig proxy — it has neither
            # get_redis_config() nor get_nested(). The config *manager* is the
            # canonical holder of both, as every other call site uses.
            from config import unified_config_manager

            logger.info("Creating new ChatHistoryManager instance (expensive operation)")

            redis_config = unified_config_manager.get_redis_config()
            chm = ChatHistoryManager(
                history_file=unified_config_manager.get_nested("data.chat_history_file", "data/chat_history.json"),
                use_redis=redis_config.get("enabled", False),
                redis_host=redis_config.get("host", NetworkConstants.LOCALHOST_NAME),
                redis_port=redis_config.get("port", NetworkConstants.REDIS_PORT),
            )
            await chm.initialize()

            # Cache in app state if available
            if request is not None:
                request.app.state.chat_history_manager = chm
                logger.info("Cached ChatHistoryManager in app.state for future requests")

            return chm

        except Exception as e:
            logger.error("Failed to create ChatHistoryManager: %s", e)
            raise

    @staticmethod
    async def get_workflow_automation_manager(request: Request = None):
        """Get or create WorkflowAutomationManager instance with app.state caching"""
        try:
            # Try app.state first
            if request is not None:
                wam = getattr(request.app.state, "workflow_automation_manager", None)
                if wam is not None:
                    logger.debug("Using pre-initialized WorkflowAutomationManager from app.state")
                    return wam

            # Fallback to module-level import and creation
            from services.workflow_automation.manager import WorkflowAutomationManager

            logger.info("Creating new WorkflowAutomationManager instance (expensive operation)")

            wam = WorkflowAutomationManager()

            # Cache in app state if available
            if request is not None:
                request.app.state.workflow_automation_manager = wam
                logger.info("Cached WorkflowAutomationManager in app.state for future requests")

            return wam

        except Exception as e:
            logger.error("Failed to create WorkflowAutomationManager: %s", e)
            raise

    @staticmethod
    def get_all_cached_resources(request: Request) -> dict:
        """Get all cached resources from app.state for debugging/monitoring"""
        if request is None:
            return {}

        cached_resources = {}
        resource_names = [
            "knowledge_base",
            "llm_interface",
            "orchestrator",
            "chat_history_manager",
            "workflow_automation_manager",
            "advanced_workflow_orchestrator",
            "chat_knowledge_manager",
        ]

        for name in resource_names:
            resource = getattr(request.app.state, name, None)
            cached_resources[name] = {
                "cached": resource is not None,
                "type": type(resource).__name__ if resource else None,
            }

        return cached_resources


# Convenience functions for common use cases
async def get_kb(request: Request = None):
    """Shorthand for getting KnowledgeBase"""
    return await ResourceFactory.get_knowledge_base(request)


async def get_llm(request: Request = None):
    """Shorthand for getting LLMService"""
    return await ResourceFactory.get_llm_interface(request)


async def get_orchestrator(request: Request = None):
    """Shorthand for getting the Orchestrator singleton."""
    return await ResourceFactory.get_orchestrator(request)


async def get_chat_manager(request: Request = None):
    """Shorthand for getting ChatHistoryManager"""
    return await ResourceFactory.get_chat_history_manager(request)
