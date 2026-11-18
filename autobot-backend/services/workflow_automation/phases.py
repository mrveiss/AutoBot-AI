# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The workflow state machine's phases -- enum-only, so codegen can load them (#19334).

Split out of ``state_machine`` (which pulls in pydantic and the message bus) so
``gen_frontend_types.py`` can generate the frontend ``WorkflowPhase`` union from it.
``state_machine`` re-imports the name, so ``from .state_machine import WorkflowPhase`` keeps working.
"""

from enum import Enum


class WorkflowPhase(str, Enum):
    """Discrete phases a workflow can occupy."""

    PLANNING = "planning"
    AWAITING_APPROVAL = "awaiting_approval"  # #1402: approval gate
    EXECUTING = "executing"
    VALIDATING = "validating"
    COMPLETE = "complete"
    FAILED = "failed"
