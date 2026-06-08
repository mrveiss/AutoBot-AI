# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Re-export shim for the centralized status enums (#7121, partial #6520).

Original location: ``autobot-backend/constants/status_enums.py`` (Issue #670).
Moved 2026-05-07 to ``autobot_shared.status_enums`` so canonical workflow
types in ``autobot_shared.workflow`` can use the same enums without
``autobot_shared`` taking a dependency on ``autobot-backend``. This shim
preserves the original import path ``from constants.status_enums import X``
for the 15+ existing callers.

New code should import directly from ``autobot_shared.status_enums``.
"""

from autobot_shared.status_enums import (
    AgentLifecycleStatus,
    AgentStatus,
    HealthStatus,
    LLMProvider,
    OperationOutcome,
    Priority,
    Severity,
    TaskPriority,
    TaskStatus,
)

__all__ = [
    "AgentLifecycleStatus",
    "AgentStatus",
    "HealthStatus",
    "LLMProvider",
    "OperationOutcome",
    "Priority",
    "Severity",
    "TaskPriority",
    "TaskStatus",
]
