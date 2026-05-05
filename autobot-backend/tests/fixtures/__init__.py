# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Test fixtures for autobot-backend (canonical location, #6994).

Mirrors `autobot-infrastructure/shared/tests/fixtures/` but lives inside
`autobot-backend/` so the `__main__` demo blocks in `intelligence/` can
resolve `from tests.fixtures.mocks import ...` without depending on the
infrastructure repo path.
"""

from .mocks import (
    MockCommandValidator,
    MockKnowledgeBase,
    MockLLMInterface,
    MockLLMService,
    MockWorkerNode,
)

__all__ = [
    "MockCommandValidator",
    "MockKnowledgeBase",
    "MockLLMInterface",
    "MockLLMService",
    "MockWorkerNode",
]
