# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Test fixtures package for AutoBot.

Provides reusable mock components and test utilities.
"""

from .mocks import (
    MockCommandValidator,
    MockKnowledgeBase,
    MockLLMInterface,
    MockWorkerNode,
)

__all__ = [
    "MockLLMInterface",
    "MockCommandValidator",
    "MockKnowledgeBase",
    "MockWorkerNode",
]
