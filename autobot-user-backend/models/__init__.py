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
from backend.models.activities import (
    BrowserActivityModel,
    DesktopActivityModel,
    FileActivityModel,
    SecretUsageModel,
    TerminalActivityModel,
)

# Other backend models
from backend.models.atomic_fact import AtomicFact
from backend.models.code_pattern import CodePattern
from backend.models.command_execution import CommandExecution
from backend.models.completion_feedback import CompletionFeedback
from backend.models.ml_model import MLModel
from backend.models.secret import Secret
from backend.models.session_collaboration import SessionCollaboration

__all__ = [
    # Activity models (referenced by User model)
    "TerminalActivityModel",
    "FileActivityModel",
    "BrowserActivityModel",
    "DesktopActivityModel",
    "SecretUsageModel",
    # Other models
    "AtomicFact",
    "CodePattern",
    "CommandExecution",
    "CompletionFeedback",
    "MLModel",
    "Secret",
    "SessionCollaboration",
]
