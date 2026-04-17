# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Backward-compatibility shim for services.orchestration.subagent_orchestrator.

Issue #5040: Module renamed to subagent_dispatcher.py.
All names re-exported here so existing imports continue to work.
"""

from .subagent_dispatcher import (  # noqa: F401
    SubagentDispatcher as SubagentOrchestrator,
    SubagentDispatcher,
    SubagentTask,
    get_subagent_dispatcher as get_subagent_orchestrator,
    get_subagent_dispatcher,
)
