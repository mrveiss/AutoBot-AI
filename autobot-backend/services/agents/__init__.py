# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Agents Package - Autonomous subagent spawning and coordination (#4348)
"""

from .subagent_manager import SubagentManager
from .subagent_spawner import SubagentSpawner
from .subagent_task import (
    ConflictResolution,
    SubagentTask,
    TaskPriority,
    TaskResult,
    TaskStatus,
)

__all__ = [
    "SubagentSpawner",
    "SubagentManager",
    "SubagentTask",
    "TaskResult",
    "TaskStatus",
    "TaskPriority",
    "ConflictResolution",
]
