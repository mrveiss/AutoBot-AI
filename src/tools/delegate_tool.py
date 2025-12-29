# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Delegate Tool for Subordinate Agent Delegation.

Issue #657: Implements Agent Zero's subordinate agent pattern. This tool
allows the LLM to delegate subtasks to subordinate agents for better
task decomposition and parallel execution.
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class DelegateToolResponse:
    """Response from delegate tool execution."""

    success: bool
    message: str
    subordinate_id: Optional[str] = None
    result: Optional[str] = None
    break_loop: bool = False
    metadata: Optional[Dict[str, Any]] = None


class DelegateTool:
    """
    Tool for delegating subtasks to subordinate agents.

    Issue #657: This tool is available to the LLM for complex task
    decomposition. When invoked, it creates a subordinate agent to
    handle the specified subtask.

    Usage in LLM prompt:
        <TOOL_CALL name="delegate" params='{"task":"Install npm packages","reason":"Independent setup step"}'>
            Delegate package installation
        </TOOL_CALL>

    Attributes:
        name: Tool name for LLM recognition
        description: Tool description included in LLM prompt
        hierarchical_agent: Reference to parent HierarchicalAgent
    """

    name = "delegate"
    description = """
    Delegate a subtask to a subordinate agent.

    Use when:
    - Task has independent parts that can run separately
    - Subtask requires focused context
    - Breaking down complex task improves clarity
    - You want to execute multiple steps in parallel

    Do NOT use when:
    - Task is simple enough to do directly
    - Subtask depends on results from current context
    - You're already at maximum delegation depth
    - The subtask is trivial (just use execute_command instead)

    Parameters:
    - task (required): Description of the subtask to delegate
    - reason (required): Why this task should be delegated
    - wait_for_result (optional, default: true): Whether to wait for completion

    Example:
        Delegate the database setup to a subordinate while I work on API endpoints.
        <TOOL_CALL name="delegate" params='{"task":"Set up PostgreSQL database with migrations","reason":"Independent infrastructure task"}'>
            Delegate database setup
        </TOOL_CALL>
    """

    def __init__(self, hierarchical_agent=None):
        """
        Initialize delegate tool.

        Args:
            hierarchical_agent: HierarchicalAgent instance for delegation
        """
        self.hierarchical_agent = hierarchical_agent

    async def execute(
        self,
        task: str,
        reason: str,
        wait_for_result: bool = True,
    ) -> DelegateToolResponse:
        """
        Execute delegation to subordinate agent.

        Args:
            task: Task description for subordinate
            reason: Reason for delegation
            wait_for_result: Whether to wait for subordinate completion

        Returns:
            DelegateToolResponse with delegation result
        """
        from src.utils.errors import RepairableException

        logger.info(
            "[Issue #657] Delegate tool invoked: task=%s, reason=%s",
            task[:100],
            reason,
        )

        if not self.hierarchical_agent:
            logger.warning("[Issue #657] Delegate tool called without hierarchical agent")
            return DelegateToolResponse(
                success=False,
                message="Delegation not available in current context",
                metadata={"error": "no_hierarchical_agent"},
            )

        try:
            # Delegate to subordinate agent
            result = await self.hierarchical_agent.delegate(
                task=task,
                reason=reason,
                wait_for_result=wait_for_result,
            )

            if result.success:
                return DelegateToolResponse(
                    success=True,
                    message=f"Subordinate completed: {result.result[:500] if result.result else 'No output'}",
                    subordinate_id=result.agent_id,
                    result=result.result,
                    break_loop=False,  # Continue with next steps
                    metadata={
                        "execution_time": result.execution_time,
                        "subordinate_level": result.metadata.get("level", 1),
                    },
                )
            else:
                return DelegateToolResponse(
                    success=False,
                    message=f"Subordinate failed: {result.error or 'Unknown error'}",
                    subordinate_id=result.agent_id,
                    break_loop=False,
                    metadata={"error": result.error},
                )

        except RepairableException as e:
            logger.warning("[Issue #657] Delegation failed (repairable): %s", e.message)
            return DelegateToolResponse(
                success=False,
                message=e.message,
                metadata={"suggestion": e.suggestion},
            )

        except Exception as e:
            logger.error("[Issue #657] Delegation failed: %s", str(e))
            return DelegateToolResponse(
                success=False,
                message=f"Delegation failed: {str(e)}",
                metadata={"error_type": type(e).__name__},
            )

    def get_tool_definition(self) -> Dict[str, Any]:
        """
        Get tool definition for LLM prompt injection.

        Returns:
            Dictionary describing the tool for LLM
        """
        return {
            "name": self.name,
            "description": self.description.strip(),
            "parameters": {
                "task": {
                    "type": "string",
                    "required": True,
                    "description": "Description of the subtask to delegate",
                },
                "reason": {
                    "type": "string",
                    "required": True,
                    "description": "Why this task should be delegated",
                },
                "wait_for_result": {
                    "type": "boolean",
                    "required": False,
                    "default": True,
                    "description": "Whether to wait for subordinate completion",
                },
            },
        }

    def format_for_prompt(self) -> str:
        """
        Format tool description for inclusion in LLM system prompt.

        Returns:
            Formatted tool description string
        """
        return f"""
### Delegate Tool (Issue #657 - Subordinate Agent Delegation)
{self.description}

Syntax:
```
<TOOL_CALL name="delegate" params='{{"task":"<subtask_description>","reason":"<why_delegate>"}}'>Brief description</TOOL_CALL>
```
"""
