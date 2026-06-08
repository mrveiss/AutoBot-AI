# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Chat Workflow Module

Provides centralized chat workflow orchestration with modular architecture:
- Models: Data structures (WorkflowSession)
- Conversation: History management and persistence
- Tool Handler: Command execution and approval workflow
- LLM Handler: LLM interaction and interpretation
- Session Handler: Session lifecycle management
- Manager: Main orchestration class

Usage:
    from chat_workflow import (
        ChatWorkflowManager,
        WorkflowSession,
        get_chat_workflow_manager,
        initialize_chat_workflow_manager,
    )
"""

from autobot_shared.logging_manager import get_logger
from autobot_shared.singleton_factory import lazy_singleton

from .manager import ChatWorkflowManager
from .models import WorkflowSession

logger = get_logger(__name__)

# Issue #1047: LangGraph imports are conditional — langgraph is in
# requirements.txt but may fail on fresh installs before pip install.
try:
    from .graph import ChatState, build_chat_graph, get_compiled_graph
except ImportError:
    ChatState = None  # type: ignore[assignment,misc]
    build_chat_graph = None  # type: ignore[assignment]
    get_compiled_graph = None  # type: ignore[assignment]
    logger.warning("langgraph not installed — graph features disabled")

get_chat_workflow_manager = lazy_singleton(ChatWorkflowManager)


async def initialize_chat_workflow_manager() -> bool:
    """Initialize the global chat workflow manager."""
    manager = get_chat_workflow_manager()
    return await manager.initialize()


# Export main classes and functions
__all__ = [
    "ChatState",
    "ChatWorkflowManager",
    "WorkflowSession",
    "build_chat_graph",
    "get_chat_workflow_manager",
    "get_compiled_graph",
    "initialize_chat_workflow_manager",
]
