# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Agent Selection Utilities - Shared logic for agent selection and performance tracking.

This module provides reusable functions for agent task assignment and performance
metrics tracking. Extracted from orchestrator.py and enhanced_orchestrator.py to
eliminate code duplication (Issue #292).

Functions:
    find_best_agent_for_task: Find the most suitable agent for a given task
    update_agent_performance: Update agent performance metrics after task completion
    reserve_agent: Reserve an agent for task execution
    release_agent: Release an agent after task completion
"""

from typing import Any, Dict, List, Optional, Set, Tuple

from autobot_shared.logging_manager import get_logger

logger = get_logger("agent_selection")


def _calculate_agent_suitability_score(
    agent: Any,
    task_type: str,
    current_workload_attr: str,
    max_concurrent_tasks_attr: str,
    preferred_task_types_attr: str,
    specializations_attr: str,
    success_rate_attr: str,
) -> float:
    """Calculate suitability score for an agent for a given task (Issue #398: extracted).

    Returns:
        Float score where higher is better
    """
    # Check task type preference
    task_match_score = 0
    preferred_tasks = getattr(agent, preferred_task_types_attr, [])
    if task_type in preferred_tasks:
        task_match_score += 2

    specializations = getattr(agent, specializations_attr, [])
    if any(spec in task_type for spec in specializations):
        task_match_score += 1

    # Calculate workload and performance factors
    current_workload = getattr(agent, current_workload_attr, 0)
    max_concurrent = getattr(agent, max_concurrent_tasks_attr, 3)
    workload_factor = (
        1.0 - (current_workload / max_concurrent) if max_concurrent > 0 else 1.0
    )
    performance_factor = getattr(agent, success_rate_attr, 1.0)

    return (
        (task_match_score * 0.4) + (workload_factor * 0.3) + (performance_factor * 0.3)
    )


def _is_agent_eligible(
    agent: Any,
    required_capabilities: Set[Any],
    availability_status_attr: str,
    current_workload_attr: str,
    max_concurrent_tasks_attr: str,
    capabilities_attr: str,
) -> bool:
    """Check if agent is eligible for task assignment (Issue #398: extracted).

    Returns:
        True if agent is available and has required capabilities
    """
    # Check availability
    availability = getattr(agent, availability_status_attr, "available")
    if availability != "available":
        return False

    # Check workload capacity
    current_workload = getattr(agent, current_workload_attr, 0)
    max_concurrent = getattr(agent, max_concurrent_tasks_attr, 3)
    if current_workload >= max_concurrent:
        return False

    # Check capabilities
    if required_capabilities:
        agent_capabilities = getattr(agent, capabilities_attr, set())
        if not required_capabilities.issubset(agent_capabilities):
            return False

    return True


def _select_best_agent_from_candidates(
    suitable_agents: List[Tuple[str, float]],
    task_type: str,
) -> Optional[str]:
    """
    Select the best agent from a list of scored candidates.

    Sorts candidates by suitability score and returns the agent with the
    highest score, logging the selection. Issue #620.

    Args:
        suitable_agents: List of (agent_id, score) tuples
        task_type: Type of task for logging context

    Returns:
        Agent ID of the best suitable agent, or None if list is empty
    """
    if not suitable_agents:
        logger.warning("No suitable agent found for task type: %s", task_type)
        return None

    # Return agent with highest suitability score
    suitable_agents.sort(key=lambda x: x[1], reverse=True)
    best_agent_id = suitable_agents[0][0]

    logger.debug(
        f"Selected agent {best_agent_id} for task {task_type} "
        f"(score: {suitable_agents[0][1]:.2f})"
    )
    return best_agent_id


def find_best_agent_for_task(
    agent_registry: Dict[str, Any],
    task_type: str,
    required_capabilities: Optional[Set[Any]] = None,
    availability_status_attr: str = "availability_status",
    current_workload_attr: str = "current_workload",
    max_concurrent_tasks_attr: str = "max_concurrent_tasks",
    capabilities_attr: str = "capabilities",
    preferred_task_types_attr: str = "preferred_task_types",
    specializations_attr: str = "specializations",
    success_rate_attr: str = "success_rate",
) -> Optional[str]:
    """
    Find the best agent for a specific task based on capabilities and current workload.

    This is a standalone function that can be used by any orchestrator implementation.
    It calculates a suitability score based on:
    - Task type match (preferred tasks and specializations)
    - Current workload (agents with less load are preferred)
    - Historical performance (success rate)

    Args:
        agent_registry: Dictionary mapping agent_id to agent objects
        task_type: Type of task to assign
        required_capabilities: Set of capabilities the agent must have (optional)
        availability_status_attr: Attribute name for agent availability status
        current_workload_attr: Attribute name for current workload count
        max_concurrent_tasks_attr: Attribute name for max concurrent tasks
        capabilities_attr: Attribute name for agent capabilities
        preferred_task_types_attr: Attribute name for preferred task types
        specializations_attr: Attribute name for agent specializations
        success_rate_attr: Attribute name for success rate

    Returns:
        Agent ID of the best suitable agent, or None if no suitable agent found

    Example:
        >>> best_agent = find_best_agent_for_task(
        ...     agent_registry=self.agent_registry,
        ...     task_type="code_review",
        ...     required_capabilities={AgentCapability.ANALYSIS}
        ... )
    """
    required_capabilities = required_capabilities or set()

    # Find eligible agents and calculate scores (Issue #398: refactored to use helpers)
    suitable_agents: List[Tuple[str, float]] = []

    for agent_id, agent in agent_registry.items():
        if not _is_agent_eligible(
            agent,
            required_capabilities,
            availability_status_attr,
            current_workload_attr,
            max_concurrent_tasks_attr,
            capabilities_attr,
        ):
            continue

        suitability_score = _calculate_agent_suitability_score(
            agent,
            task_type,
            current_workload_attr,
            max_concurrent_tasks_attr,
            preferred_task_types_attr,
            specializations_attr,
            success_rate_attr,
        )
        suitable_agents.append((agent_id, suitability_score))

    return _select_best_agent_from_candidates(suitable_agents, task_type)


def _update_success_rate(
    agent: Any,
    success: bool,
    performance_metrics_attr: str,
    success_rate_attr: str,
) -> float:
    """
    Update agent success rate based on task outcome.

    Calculates and sets the new success rate using a running average
    of total attempts and successes. Issue #620.

    Args:
        agent: Agent object to update
        success: Whether the task was successful
        performance_metrics_attr: Attribute name for performance metrics dict
        success_rate_attr: Attribute name for success rate

    Returns:
        The newly calculated success rate
    """
    performance_metrics = getattr(agent, performance_metrics_attr, {})

    current_attempts = performance_metrics.get("total_attempts", 0)
    current_successes = performance_metrics.get("total_successes", 0)

    new_attempts = current_attempts + 1
    new_successes = current_successes + (1 if success else 0)

    new_success_rate = new_successes / new_attempts if new_attempts > 0 else 1.0
    setattr(agent, success_rate_attr, new_success_rate)

    performance_metrics["total_attempts"] = new_attempts
    performance_metrics["total_successes"] = new_successes
    setattr(agent, performance_metrics_attr, performance_metrics)

    return new_success_rate


def _update_average_completion_time(
    agent: Any,
    execution_time: float,
    average_completion_time_attr: str,
) -> float:
    """
    Update agent average completion time with weighted average.

    Uses a weighted average favoring recent performance (30% weight
    for new time, 70% for historical). Issue #620.

    Args:
        agent: Agent object to update
        execution_time: Time taken to complete the task in seconds
        average_completion_time_attr: Attribute name for average completion time

    Returns:
        The newly calculated average completion time
    """
    current_avg_time = getattr(agent, average_completion_time_attr, 0.0)
    if current_avg_time == 0:
        new_avg_time = execution_time
    else:
        # Weighted average (give more weight to recent performance)
        new_avg_time = (current_avg_time * 0.7) + (execution_time * 0.3)
    setattr(agent, average_completion_time_attr, new_avg_time)
    return new_avg_time


def update_agent_performance(
    agent_registry: Dict[str, Any],
    agent_id: str,
    success: bool,
    execution_time: float,
    performance_metrics_attr: str = "performance_metrics",
    success_rate_attr: str = "success_rate",
    average_completion_time_attr: str = "average_completion_time",
) -> bool:
    """
    Update agent performance metrics after task completion. Issue #620.

    Args:
        agent_registry: Dictionary mapping agent_id to agent objects
        agent_id: ID of the agent to update
        success: Whether the task was successful
        execution_time: Time taken to complete the task in seconds
        performance_metrics_attr: Attribute name for performance metrics dict
        success_rate_attr: Attribute name for success rate
        average_completion_time_attr: Attribute name for average completion time

    Returns:
        True if update was successful, False if agent not found
    """
    if agent_id not in agent_registry:
        logger.warning("Cannot update performance for unknown agent: %s", agent_id)
        return False

    agent = agent_registry[agent_id]
    new_success_rate = _update_success_rate(
        agent, success, performance_metrics_attr, success_rate_attr
    )
    new_avg_time = _update_average_completion_time(
        agent, execution_time, average_completion_time_attr
    )
    _log_performance_update(agent_id, new_success_rate, new_avg_time)
    return True


def _log_performance_update(
    agent_id: str, success_rate: float, avg_time: float
) -> None:
    """Log agent performance update details. Issue #620."""
    logger.debug(
        "Updated agent %s performance: success_rate=%.2f, avg_time=%.2fs",
        agent_id,
        success_rate,
        avg_time,
    )


def reserve_agent(
    agent_registry: Dict[str, Any],
    agent_id: str,
    current_workload_attr: str = "current_workload",
    max_concurrent_tasks_attr: str = "max_concurrent_tasks",
    availability_status_attr: str = "availability_status",
) -> bool:
    """
    Reserve an agent for task execution by incrementing workload.

    Args:
        agent_registry: Dictionary mapping agent_id to agent objects
        agent_id: ID of the agent to reserve
        current_workload_attr: Attribute name for current workload
        max_concurrent_tasks_attr: Attribute name for max concurrent tasks
        availability_status_attr: Attribute name for availability status

    Returns:
        True if reservation successful, False if agent not found
    """
    if agent_id not in agent_registry:
        return False

    agent = agent_registry[agent_id]
    current_workload = getattr(agent, current_workload_attr, 0)
    max_concurrent = getattr(agent, max_concurrent_tasks_attr, 3)

    setattr(agent, current_workload_attr, current_workload + 1)

    new_status = "busy" if (current_workload + 1) >= max_concurrent else "available"
    setattr(agent, availability_status_attr, new_status)

    return True


def release_agent(
    agent_registry: Dict[str, Any],
    agent_id: str,
    current_workload_attr: str = "current_workload",
    max_concurrent_tasks_attr: str = "max_concurrent_tasks",
    availability_status_attr: str = "availability_status",
) -> bool:
    """
    Release an agent after task completion by decrementing workload.

    Args:
        agent_registry: Dictionary mapping agent_id to agent objects
        agent_id: ID of the agent to release
        current_workload_attr: Attribute name for current workload
        max_concurrent_tasks_attr: Attribute name for max concurrent tasks
        availability_status_attr: Attribute name for availability status

    Returns:
        True if release successful, False if agent not found
    """
    if agent_id not in agent_registry:
        return False

    agent = agent_registry[agent_id]
    current_workload = getattr(agent, current_workload_attr, 0)
    max_concurrent = getattr(agent, max_concurrent_tasks_attr, 3)

    new_workload = max(0, current_workload - 1)
    setattr(agent, current_workload_attr, new_workload)

    new_status = "available" if new_workload < max_concurrent else "busy"
    setattr(agent, availability_status_attr, new_status)

    return True
