# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Wire/validation types for a workflow graph (#18390).

Externally a graph refers to things by their human-readable keys -- a process by
``process_key``, a meta skill or handoff target by ``workflow_id`` -- exactly as
the existing ``/llc/workflows`` API does. The row UUIDs stay internal.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from llc.models.company_os_enums import EndOutcome, NodeKind, TransitionKind


class NodeSpec(BaseModel):
    key: str = Field(..., min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    kind: NodeKind
    label: Optional[str] = Field(None, max_length=255)
    process_key: Optional[str] = Field(None, max_length=255)
    meta_skill_id: Optional[str] = Field(None, max_length=255)
    end_outcome: Optional[EndOutcome] = None


class TransitionSpec(BaseModel):
    from_node: str = Field(..., min_length=1, max_length=64)
    kind: TransitionKind
    to_node: Optional[str] = Field(None, max_length=64)
    retry_max: Optional[int] = Field(None, ge=0)
    condition: Optional[str] = Field(None, max_length=2000)
    timeout_seconds: Optional[int] = Field(None, gt=0)
    handoff_workflow_id: Optional[str] = Field(None, max_length=255)


class GraphSpec(BaseModel):
    nodes: List[NodeSpec] = Field(default_factory=list, max_length=500)
    transitions: List[TransitionSpec] = Field(default_factory=list, max_length=2000)


@dataclass(frozen=True)
class HandoffTarget:
    """What validation needs to know about a workflow a handoff points at."""

    kind: str
    owner_role_id: Optional[uuid.UUID]


@dataclass
class GraphContext:
    """Everything the pure validator needs from the database, already scoped to
    ONE company by the caller -- an id absent from these maps does not exist as
    far as this company can tell, whether or not another company owns it."""

    own_workflow_id: str
    own_role_id: Optional[uuid.UUID]
    processes: Dict[str, List[str]] = field(default_factory=dict)  # process_key -> required skills
    meta_skills: frozenset = frozenset()
    handoff_targets: Dict[str, HandoffTarget] = field(default_factory=dict)
    held_skills: frozenset = frozenset()
    #: meta skill workflow_id -> the meta skills its stored graph calls.
    meta_calls: Dict[str, frozenset] = field(default_factory=dict)


@dataclass
class GraphReport:
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
