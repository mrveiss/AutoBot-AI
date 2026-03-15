# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Backend SQLAlchemy Models

Issue #898: Created to ensure activity models are loaded before
User model initialization, resolving forward reference errors.

All models are imported here to register them with SQLAlchemy metadata
before relationships are configured.
"""

# Activity tracking models - MUST be imported before user_management models
# to resolve forward references in User.terminal_activities, etc.
from models.activities import (
    BrowserActivityModel,
    DesktopActivityModel,
    FileActivityModel,
    SecretUsageModel,
    TerminalActivityModel,
)

# Agent org hierarchy models (#1405)
from models.agent_org import AgentOrgNode

# Approval gate models (#1402)
from models.approval import Approval, ApprovalComment, TaskApprovalLink

# Other backend models (SQLAlchemy models only)
from models.code_pattern import CodePattern
from models.completion_feedback import CompletionFeedback

# Config revision model (#1404)
from models.config_revision import ConfigRevision
from models.ml_model import MLModel

# Process adapter models (#1406)
from models.process_run import AgentSession, ProcessRun, TaskDecomposition
from models.secret import Secret
from models.session_collaboration import SessionCollaboration

__all__ = [
    # Activity models (referenced by User model)
    "TerminalActivityModel",
    "FileActivityModel",
    "BrowserActivityModel",
    "DesktopActivityModel",
    "SecretUsageModel",
    # Other SQLAlchemy models
    "CodePattern",
    "CompletionFeedback",
    "MLModel",
    "Secret",
    "SessionCollaboration",
    # Agent org hierarchy (#1405)
    "AgentOrgNode",
    # Approval gate models (#1402)
    "Approval",
    "ApprovalComment",
    "TaskApprovalLink",
    # Config revision model (#1404)
    "ConfigRevision",
    # Process adapter models (#1406)
    "ProcessRun",
    "TaskDecomposition",
    "AgentSession",
]
