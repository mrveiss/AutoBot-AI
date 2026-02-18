# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Agent Terminal Module

Modular agent terminal service for secure command execution with approval workflow.

This module is organized into the following components:
- models.py: Data classes and enums
- utils.py: Helper functions (risk mapping, interactive command detection)
- session_manager.py: Session lifecycle management
- command_executor.py: Command execution with intelligent polling
- approval_handler.py: Approval workflow and auto-approval rules
- service.py: Main service class that composes all functionality
"""

from .models import AgentSessionState, AgentTerminalSession
from .service import AgentTerminalService

# Export main classes and enums
__all__ = [
    "AgentTerminalService",
    "AgentTerminalSession",
    "AgentSessionState",
]
