# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Skill Dependency Resolver (Issue #731)

Resolves skill dependencies using topological sort to determine
correct loading order and detect circular dependencies.
"""

import logging
from typing import Dict, List, Set, Tuple

logger = logging.getLogger(__name__)


class DependencyCycleError(Exception):
    """Raised when a circular dependency is detected between skills."""

    def __init__(self, cycle: List[str]) -> None:
        self.cycle = cycle
        super().__init__(f"Circular dependency detected: {' -> '.join(cycle)}")


def resolve_dependencies(
    skill_deps: Dict[str, List[str]],
) -> List[str]:
    """Resolve skill loading order via topological sort (Kahn's algorithm).

    Args:
        skill_deps: Mapping of skill name -> list of dependency names.

    Returns:
        List of skill names in valid loading order.

    Raises:
        DependencyCycleError: If a circular dependency is detected.
    """
    in_degree: Dict[str, int] = {name: 0 for name in skill_deps}
    adjacency: Dict[str, List[str]] = {name: [] for name in skill_deps}

    for name, deps in skill_deps.items():
        for dep in deps:
            if dep not in skill_deps:
                logger.warning("Skill '%s' depends on unknown skill '%s'", name, dep)
                continue
            adjacency[dep].append(name)
            in_degree[name] += 1

    queue = [name for name, degree in in_degree.items() if degree == 0]
    order: List[str] = []

    while queue:
        queue.sort()
        current = queue.pop(0)
        order.append(current)
        for neighbor in adjacency[current]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(order) != len(skill_deps):
        cycle = _find_cycle(skill_deps)
        raise DependencyCycleError(cycle)

    return order


def check_missing_dependencies(
    skill_name: str,
    dependencies: List[str],
    available_skills: Set[str],
) -> List[str]:
    """Check which dependencies are missing for a skill.

    Returns list of missing dependency names.
    """
    return [dep for dep in dependencies if dep not in available_skills]


def _find_cycle(skill_deps: Dict[str, List[str]]) -> List[str]:
    """Find a cycle in the dependency graph for error reporting.

    Helper for resolve_dependencies (Issue #731).
    """
    visited: Set[str] = set()
    path: List[str] = []
    path_set: Set[str] = set()

    def dfs(node: str) -> Tuple[bool, List[str]]:
        if node in path_set:
            cycle_start = path.index(node)
            return True, path[cycle_start:] + [node]
        if node in visited:
            return False, []
        visited.add(node)
        path.append(node)
        path_set.add(node)
        for dep in skill_deps.get(node, []):
            if dep in skill_deps:
                found, cycle = dfs(dep)
                if found:
                    return True, cycle
        path.pop()
        path_set.discard(node)
        return False, []

    for name in skill_deps:
        found, cycle = dfs(name)
        if found:
            return cycle
    return list(skill_deps.keys())[:3] + ["..."]
