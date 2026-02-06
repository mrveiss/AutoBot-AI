# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Dependency Analyzer

Analyzes dependencies between tool calls to enable parallel execution.
Based on Cursor's dependency detection patterns.
"""

import logging
from typing import Callable, Optional

from tools.parallel.types import DependencyType, ToolCall

logger = logging.getLogger(__name__)


class DependencyAnalyzer:
    """Analyzes dependencies between tool calls for parallel execution"""

    # Tools that read from resources
    READ_TOOLS = {
        "read_file",
        "grep_search",
        "file_search",
        "list_dir",
        "list_directory",
        "web_search",
        "query_database",
        "get_redis_value",
        "semantic_search",
        "search_knowledge",
    }

    # Tools that write to resources
    WRITE_TOOLS = {
        "edit_file",
        "write_file",
        "delete_file",
        "execute_command",
        "set_redis_value",
        "insert_database",
        "create_file",
        "move_file",
        "rename_file",
    }

    # Tools that affect system state
    STATE_TOOLS = {
        "execute_command",
        "manage_service",
        "create_directory",
        "delete_directory",
        "run_shell",
        "start_process",
        "stop_process",
    }

    # Resource extraction patterns for common tools
    RESOURCE_EXTRACTORS: dict[str, Callable[[dict], Optional[str]]] = {
        "read_file": lambda args: args.get("file_path") or args.get("path"),
        "edit_file": lambda args: args.get("file_path") or args.get("path"),
        "write_file": lambda args: args.get("file_path") or args.get("path"),
        "delete_file": lambda args: args.get("file_path") or args.get("path"),
        "create_file": lambda args: args.get("file_path") or args.get("path"),
        "grep_search": lambda args: args.get("path") or args.get("directory"),
        "list_dir": lambda args: args.get("path") or args.get("directory"),
        "list_directory": lambda args: args.get("path") or args.get("directory"),
        "create_directory": lambda args: args.get("path"),
        "move_file": lambda args: args.get("source") or args.get("destination"),
    }

    def __init__(self):
        self._custom_extractors: dict[str, Callable[[dict], Optional[str]]] = {}

    def register_resource_extractor(
        self,
        tool_name: str,
        extractor: Callable[[dict], Optional[str]],
    ) -> None:
        """Register a custom resource extractor for a tool"""
        self._custom_extractors[tool_name] = extractor

    def analyze_dependencies(
        self,
        tool_calls: list[ToolCall],
    ) -> dict[str, list[str]]:
        """
        Analyze dependencies between tool calls.

        Returns:
            Dict mapping call_id to list of call_ids it depends on
        """
        dependencies: dict[str, list[str]] = {tc.call_id: [] for tc in tool_calls}

        for i, call_a in enumerate(tool_calls):
            for j, call_b in enumerate(tool_calls):
                if i >= j:  # Only check forward dependencies
                    continue

                dep_type = self._check_dependency(call_a, call_b)
                if dep_type != DependencyType.NONE:
                    dependencies[call_b.call_id].append(call_a.call_id)
                    call_b.depends_on.append(call_a.call_id)
                    call_b.dependency_types[call_a.call_id] = dep_type

        return dependencies

    def _check_dependency(
        self,
        call_a: ToolCall,
        call_b: ToolCall,
    ) -> DependencyType:
        """Check if call_b depends on call_a"""

        # Rule 1: Write → Read/Write on same resource
        if call_a.tool_name in self.WRITE_TOOLS:
            resource_a = self._extract_resource(call_a)
            resource_b = self._extract_resource(call_b)

            if resource_a and resource_b:
                if self._resources_overlap(resource_a, resource_b):
                    return DependencyType.RESOURCE

        # Rule 2: Read → Write on same resource (read must complete first)
        if call_a.tool_name in self.READ_TOOLS and call_b.tool_name in self.WRITE_TOOLS:
            resource_a = self._extract_resource(call_a)
            resource_b = self._extract_resource(call_b)

            if resource_a and resource_b:
                if self._resources_overlap(resource_a, resource_b):
                    return DependencyType.RESOURCE

        # Rule 3: State-changing tools create order dependencies
        if call_a.tool_name in self.STATE_TOOLS:
            if self._might_depend_on_state(call_a, call_b):
                return DependencyType.ORDER

        # Rule 4: Explicit output → input dependency
        if self._has_data_dependency(call_a, call_b):
            return DependencyType.DATA

        return DependencyType.NONE

    def _extract_resource(self, call: ToolCall) -> Optional[str]:
        """Extract resource identifier from tool call"""
        # Check custom extractors first
        if call.tool_name in self._custom_extractors:
            return self._custom_extractors[call.tool_name](call.arguments)

        # Fall back to built-in extractors
        extractor = self.RESOURCE_EXTRACTORS.get(call.tool_name)
        if extractor:
            return extractor(call.arguments)

        return None

    def _resources_overlap(self, resource_a: str, resource_b: str) -> bool:
        """Check if two resources might conflict"""
        # Normalize paths
        resource_a = resource_a.rstrip("/")
        resource_b = resource_b.rstrip("/")

        # Same file/resource
        if resource_a == resource_b:
            return True

        # Parent-child directory relationship
        if resource_a.startswith(resource_b + "/"):
            return True
        if resource_b.startswith(resource_a + "/"):
            return True

        return False

    def _might_depend_on_state(
        self,
        state_call: ToolCall,
        dependent_call: ToolCall,
    ) -> bool:
        """Check if dependent_call might need state from state_call"""

        # create_directory → write_file in that directory
        if state_call.tool_name == "create_directory":
            dir_path = state_call.arguments.get("path", "")
            file_path = dependent_call.arguments.get("file_path", "")
            if file_path and dir_path and file_path.startswith(dir_path):
                return True

        # execute_command might affect any subsequent operation
        if state_call.tool_name == "execute_command":
            command = state_call.arguments.get("command", "")

            # Check for commands that definitely affect state
            state_changing_commands = [
                "mkdir",
                "rm",
                "mv",
                "cp",
                "touch",
                "chmod",
                "chown",
                "git",
                "npm",
                "pip",
            ]

            for cmd in state_changing_commands:
                if cmd in command:
                    return True

        return False

    def _has_data_dependency(
        self,
        call_a: ToolCall,
        call_b: ToolCall,
    ) -> bool:
        """
        Check if call_b uses output from call_a as input.

        This requires semantic analysis or explicit markers.
        For now, we only detect obvious patterns.
        """
        # Check if call_b arguments reference call_a's ID
        for arg_value in call_b.arguments.values():
            if isinstance(arg_value, str) and call_a.call_id in arg_value:
                return True

        return False

    def get_parallel_groups(
        self,
        tool_calls: list[ToolCall],
    ) -> list[list[ToolCall]]:
        """
        Group tool calls for parallel execution.

        Returns:
            Ordered list of groups, where each group can run concurrently,
            but groups must run sequentially.
        """
        # First analyze dependencies
        self.analyze_dependencies(tool_calls)

        groups: list[list[ToolCall]] = []
        remaining = set(tc.call_id for tc in tool_calls)
        completed: set[str] = set()
        call_map = {tc.call_id: tc for tc in tool_calls}

        while remaining:
            # Find calls with all dependencies completed
            ready = []
            for call_id in remaining:
                call = call_map[call_id]
                deps = call.depends_on
                if all(dep_id in completed for dep_id in deps):
                    ready.append(call)

            if not ready:
                # Circular dependency or error
                logger.error(
                    "Circular dependency detected, remaining: %s",
                    [call_map[cid].tool_name for cid in remaining],
                )
                # Add remaining as sequential fallback
                for call_id in remaining:
                    groups.append([call_map[call_id]])
                break

            groups.append(ready)
            for call in ready:
                remaining.remove(call.call_id)
                completed.add(call.call_id)

        return groups

    def can_parallelize(self, call_a: ToolCall, call_b: ToolCall) -> bool:
        """Quick check if two calls can run in parallel"""
        return self._check_dependency(call_a, call_b) == DependencyType.NONE
