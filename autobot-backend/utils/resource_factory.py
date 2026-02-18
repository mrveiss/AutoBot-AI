#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Resource Factory - Centralized management of expensive shared resources
Provides singleton-like behavior with app.state integration for optimal performance
"""

import logging

from backend.constants.network_constants import NetworkConstants
from fastapi import Request

logger = logging.getLogger(__name__)


class ResourceFactory:
    """Factory for managing expensive shared resources with caching"""

    @staticmethod
    async def get_knowledge_base(request: Request = None):
        """Get or create KnowledgeBase instance with app.state caching"""
        try:
            # Try app.state first
            if request is not None:
                kb = getattr(request.app.state, "knowledge_base", None)
                if kb is not None:
                    logger.debug("Using pre-initialized KnowledgeBase from app.state")
                    return kb

            # Fallback to module-level import and creation
            from knowledge_base import KnowledgeBase

            logger.info("Creating new KnowledgeBase instance (expensive operation)")

            kb = KnowledgeBase()

            # Cache in app state if available
            if request is not None:
                request.app.state.knowledge_base = kb
                logger.info("Cached KnowledgeBase in app.state for future requests")

            return kb

        except Exception as e:
            logger.error("Failed to create KnowledgeBase: %s", e)
            raise

    @staticmethod
    async def get_llm_interface(request: Request = None):
        """Get or create LLMInterface instance with app.state caching"""
        try:
            # Try app.state first
            if request is not None:
                llm = getattr(request.app.state, "llm_interface", None)
                if llm is not None:
                    logger.debug("Using pre-initialized LLMInterface from app.state")
                    return llm

            # Fallback to module-level import and creation
            from llm_interface import LLMInterface

            logger.info("Creating new LLMInterface instance (expensive operation)")

            llm = LLMInterface()

            # Cache in app state if available
            if request is not None:
                request.app.state.llm_interface = llm
                logger.info("Cached LLMInterface in app.state for future requests")

            return llm

        except Exception as e:
            logger.error("Failed to create LLMInterface: %s", e)
            raise

    @staticmethod
    async def get_enhanced_orchestrator(request: Request = None):
        """Get or create EnhancedOrchestrator instance with app.state caching"""
        try:
            # Try app.state first
            if request is not None:
                orch = getattr(request.app.state, "enhanced_orchestrator", None)
                if orch is not None:
                    logger.debug(
                        "Using pre-initialized EnhancedOrchestrator from app.state"
                    )
                    return orch

            # Fallback to module-level import and creation
            from enhanced_orchestrator import EnhancedOrchestrator

            logger.info(
                "Creating new EnhancedOrchestrator instance (expensive operation)"
            )

            orch = EnhancedOrchestrator()

            # Cache in app state if available
            if request is not None:
                request.app.state.enhanced_orchestrator = orch
                logger.info(
                    "Cached EnhancedOrchestrator in app.state for future requests"
                )

            return orch

        except Exception as e:
            logger.error("Failed to create EnhancedOrchestrator: %s", e)
            raise

    @staticmethod
    async def get_chat_history_manager(request: Request = None):
        """Get or create ChatHistoryManager instance with app.state caching"""
        try:
            # Try app.state first
            if request is not None:
                chm = getattr(request.app.state, "chat_history_manager", None)
                if chm is not None:
                    logger.debug(
                        "Using pre-initialized ChatHistoryManager from app.state"
                    )
                    return chm

            # Fallback to module-level import and creation
            from chat_history import ChatHistoryManager
            from config import config as global_config_manager

            logger.info(
                "Creating new ChatHistoryManager instance (expensive operation)"
            )

            redis_config = global_config_manager.get_redis_config()
            chm = ChatHistoryManager(
                history_file=global_config_manager.get_nested(
                    "data.chat_history_file", "data/chat_history.json"
                ),
                use_redis=redis_config.get("enabled", False),
                redis_host=redis_config.get("host", NetworkConstants.LOCALHOST_NAME),
                redis_port=redis_config.get("port", NetworkConstants.REDIS_PORT),
            )

            # Cache in app state if available
            if request is not None:
                request.app.state.chat_history_manager = chm
                logger.info(
                    "Cached ChatHistoryManager in app.state for future requests"
                )

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
                    logger.debug(
                        "Using pre-initialized WorkflowAutomationManager from app.state"
                    )
                    return wam

            # Fallback to module-level import and creation
            from backend.api.workflow_automation import WorkflowAutomationManager

            logger.info(
                "Creating new WorkflowAutomationManager instance (expensive operation)"
            )

            wam = WorkflowAutomationManager()

            # Cache in app state if available
            if request is not None:
                request.app.state.workflow_automation_manager = wam
                logger.info(
                    "Cached WorkflowAutomationManager in app.state for future requests"
                )

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
            "enhanced_orchestrator",
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
    """Shorthand for getting LLMInterface"""
    return await ResourceFactory.get_llm_interface(request)


async def get_orchestrator(request: Request = None):
    """Shorthand for getting EnhancedOrchestrator"""
    return await ResourceFactory.get_enhanced_orchestrator(request)


async def get_chat_manager(request: Request = None):
    """Shorthand for getting ChatHistoryManager"""
    return await ResourceFactory.get_chat_history_manager(request)
