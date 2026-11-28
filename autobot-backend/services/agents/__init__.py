# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Agents Package - Autonomous subagent spawning and coordination (#4348)
"""

from .subagent_manager import SubagentManager
from .subagent_spawner import SubagentSpawner
from .subagent_task import (
    SubagentConflictResolution,
    SubagentTask,
    SubagentTaskResult,
    TaskPriority,
    TaskStatus,
)

__all__ = [
    "SubagentSpawner",
    "SubagentManager",
    "SubagentTask",
    "SubagentTaskResult",
    "TaskStatus",
    "TaskPriority",
    "SubagentConflictResolution",
]
