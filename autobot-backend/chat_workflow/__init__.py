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

import threading
from typing import Optional

from .graph import ChatState, build_chat_graph, get_compiled_graph
from .manager import ChatWorkflowManager
from .models import WorkflowSession

# Global instance for easy access (thread-safe)
_workflow_manager: Optional[ChatWorkflowManager] = None
_workflow_manager_lock = threading.Lock()


def get_chat_workflow_manager() -> ChatWorkflowManager:
    """Get the global chat workflow manager instance (thread-safe)."""
    global _workflow_manager
    if _workflow_manager is None:
        with _workflow_manager_lock:
            # Double-check after acquiring lock
            if _workflow_manager is None:
                _workflow_manager = ChatWorkflowManager()
    return _workflow_manager


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
