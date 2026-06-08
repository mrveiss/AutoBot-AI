# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Canonical workflow types for cross-service consolidation (#6951).

This module is the single source of truth for `WorkflowTask`, `WorkflowPlan`,
`PromptSpec`, and `ExecutionStrategy`. Phase 2 of #6951 migrates the existing
8 step shapes / 4 task shapes / 2 template shapes onto these canonical types,
completing the consolidation that #381 did not finish.

Usage:
    from autobot_shared.workflow import WorkflowTask, WorkflowPlan, PromptSpec

The shapes intentionally treat ``prompt`` and ``tools_allowed`` / ``tools_denied``
as first-class fields. Existing duplicate shapes smuggle prompts inside
``action: str`` strings and have no per-step tool gates.
"""

from autobot_shared.workflow.types import (
    ExecutionStrategy,
    PromptSpec,
    WorkflowPlan,
    WorkflowTask,
)

__all__ = [
    "ExecutionStrategy",
    "PromptSpec",
    "WorkflowPlan",
    "WorkflowTask",
]
