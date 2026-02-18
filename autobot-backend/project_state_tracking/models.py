# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Project State Tracking Data Models

Dataclasses for state snapshots, changes, and milestones.

Part of Issue #381 - God Class Refactoring
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from .types import StateChangeType, TrackingMetric


@dataclass
class StateSnapshot:
    """A snapshot of system state at a point in time"""

    timestamp: datetime
    phase_states: Dict[str, Dict[str, Any]]
    active_capabilities: Set[str]
    system_metrics: Dict[TrackingMetric, float]
    configuration: Dict[str, Any]
    validation_results: Dict[str, float]
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StateChange:
    """Records a change in system state"""

    timestamp: datetime
    change_type: StateChangeType
    before_state: Optional[Dict[str, Any]]
    after_state: Dict[str, Any]
    description: str
    user_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProjectMilestone:
    """Represents a significant project milestone"""

    name: str
    description: str
    criteria: Dict[str, Any]
    achieved: bool = False
    achieved_at: Optional[datetime] = None
    evidence: List[str] = field(default_factory=list)
