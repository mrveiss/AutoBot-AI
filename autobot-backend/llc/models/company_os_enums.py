# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Vocabulary of the Company OS model: roles -> workflows -> processes (#18390).

Stored as plain ``String`` columns, validated here at every write site, for the
same reason ``LLCRoleAssignment.holder_type`` is: widening a vocabulary must not
need a Postgres ``ALTER TYPE``.
"""

from enum import Enum


class WorkflowKind(str, Enum):
    """What a row of the ``workflows`` table is."""

    #: Belongs to one role, has one trigger.
    WORKFLOW = "workflow"
    #: A reusable process graph with no trigger and no owning role. Roles hold it
    #: and workflows call it as one step.
    META_SKILL = "meta_skill"


class WorkflowTriggerKind(str, Enum):
    """What starts a workflow. One per workflow."""

    MANUAL = "manual"
    SCHEDULE = "schedule"
    EMAIL_RECEIVED = "email_received"
    WORK_ITEM_STATUS = "work_item_status"
    WEBHOOK = "webhook"
    FOLDER_FILE_ADDED = "folder_file_added"
    PROCESS_RESULT = "process_result"


class NodeKind(str, Enum):
    START = "start"
    PROCESS = "process"
    META_SKILL = "meta_skill"
    END = "end"


class EndOutcome(str, Enum):
    DONE = "done"
    FAILED = "failed"


class TransitionKind(str, Enum):
    """The typed edges of a workflow graph."""

    SUCCESS = "success"
    #: Optional ``retry_max`` retries first, then the edge is taken.
    FAILURE = "failure"
    #: Carries a ``condition``; a node with an ``if`` needs an ``else``.
    IF = "if"
    ELSE = "else"
    #: Taken after ``timeout_seconds``.
    TIMEOUT = "timeout"
    #: Triggers another role's workflow instead of reaching a node of this one.
    HANDOFF = "handoff"


#: Upper bound on ``retry_max`` so a typo cannot mean an unbounded retry loop.
MAX_RETRIES = 10


__all__ = [
    "MAX_RETRIES",
    "EndOutcome",
    "NodeKind",
    "TransitionKind",
    "WorkflowTriggerKind",
    "WorkflowKind",
]
