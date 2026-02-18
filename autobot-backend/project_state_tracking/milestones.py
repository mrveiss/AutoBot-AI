# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Project State Tracking Milestones Module

Milestone definitions and evaluation logic.

Part of Issue #381 - God Class Refactoring
"""

from typing import Any, Dict, List, Tuple

from .models import ProjectMilestone, StateSnapshot
from .types import TrackingMetric


def define_default_milestones() -> Dict[str, ProjectMilestone]:
    """Define project milestones to track"""
    return {
        "first_phase_complete": ProjectMilestone(
            "First Phase Complete",
            "Complete the first development phase",
            {"phases_completed": 1},
        ),
        "half_way_there": ProjectMilestone(
            "Halfway There",
            "Reach 50% overall system maturity",
            {"system_maturity": 50.0},
        ),
        "core_system_ready": ProjectMilestone(
            "Core System Ready",
            "Complete first 5 phases",
            {"phases_completed": 5},
        ),
        "advanced_features_unlocked": ProjectMilestone(
            "Advanced Features Unlocked",
            "Unlock advanced AI capabilities",
            {
                "capabilities_unlocked": [
                    "multimodal_ai",
                    "code_search",
                    "intelligent_agents",
                ]
            },
        ),
        "production_ready": ProjectMilestone(
            "Production Ready",
            "System ready for production deployment",
            {"phases_completed": 10, "system_maturity": 95.0},
        ),
        "fully_autonomous": ProjectMilestone(
            "Fully Autonomous",
            "System can self-manage and evolve",
            {
                "capabilities_unlocked": [
                    "self_improvement",
                    "auto_documentation",
                    "error_recovery",
                ]
            },
        ),
    }


def evaluate_milestone_criteria(
    milestone: ProjectMilestone, snapshot: StateSnapshot
) -> Tuple[bool, List[str]]:
    """Evaluate if milestone criteria are met and collect evidence"""
    criteria_met = True
    evidence = []

    for criterion, target in milestone.criteria.items():
        met, criterion_evidence = check_single_criterion(criterion, target, snapshot)
        if met:
            evidence.append(criterion_evidence)
        else:
            criteria_met = False

    return criteria_met, evidence


def check_single_criterion(
    criterion: str, target: Any, snapshot: StateSnapshot
) -> Tuple[bool, str]:
    """Check a single milestone criterion"""
    if criterion == "phases_completed":
        actual = snapshot.system_metrics.get(TrackingMetric.PHASE_COMPLETION, 0)
        if actual >= target:
            return True, f"Completed {actual} phases (target: {target})"
        return False, ""

    if criterion == "system_maturity":
        actual = snapshot.system_metrics.get(TrackingMetric.SYSTEM_MATURITY, 0)
        if actual >= target:
            return True, f"System maturity: {actual}% (target: {target}%)"
        return False, ""

    if criterion == "capabilities_unlocked":
        required_capabilities = set(target)
        if required_capabilities.issubset(snapshot.active_capabilities):
            return (
                True,
                f"Unlocked capabilities: {', '.join(required_capabilities)}",
            )
        return False, ""

    return False, ""
