# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Mock fixtures for AutoBot testing.

Provides mock implementations of core components for testing:
- MockLLMInterface - Mock LLM for testing agent workflows
- MockCommandValidator - Mock validator for command safety testing
- MockKnowledgeBase - Mock KB for knowledge management testing
- MockWorkerNode - Mock worker for distributed testing

Moved from production code as part of Issue #458.
"""

from typing import Any, Dict, Optional


class MockLLMInterface:
    """Mock LLM interface for testing agent workflows.

    Provides deterministic responses based on prompt keywords
    to enable predictable testing of agent behavior.
    """

    def __init__(self, responses: Optional[Dict[str, str]] = None):
        """Initialize mock LLM with optional custom responses.

        Args:
            responses: Dict mapping keywords to responses.
        """
        self._custom_responses = responses or {}
        self._call_count = 0
        self._call_history: list = []

    async def generate_response(self, prompt: str, **kwargs) -> str:
        """Generate mock LLM response based on prompt keywords.

        Args:
            prompt: Input prompt text.
            **kwargs: Additional parameters (ignored in mock).

        Returns:
            Mock response string.
        """
        self._call_count += 1
        self._call_history.append({"prompt": prompt, "kwargs": kwargs})

        # Check custom responses first
        for keyword, response in self._custom_responses.items():
            if keyword.lower() in prompt.lower():
                return response

        # Default responses based on prompt content
        prompt_lower = prompt.lower()
        if "progress" in prompt_lower:
            return "Processing data..."
        elif "completion" in prompt_lower:
            return "Task completed successfully!"
        elif "command" in prompt_lower:
            return (
                "COMMAND: echo 'This is a test response'\n"
                "EXPLANATION: Testing the system"
            )
        else:
            return "Command executing..."

    @property
    def call_count(self) -> int:
        """Get number of times generate_response was called."""
        return self._call_count

    @property
    def call_history(self) -> list:
        """Get history of all calls to generate_response."""
        return self._call_history

    def reset(self) -> None:
        """Reset call count and history."""
        self._call_count = 0
        self._call_history = []


class MockCommandValidator:
    """Mock command validator for testing command safety.

    Provides configurable validation behavior for testing
    both safe and unsafe command scenarios.
    """

    def __init__(
        self,
        default_safe: bool = True,
        dangerous_patterns: Optional[list] = None,
    ):
        """Initialize mock validator.

        Args:
            default_safe: Default safety for unmatched commands.
            dangerous_patterns: List of patterns to mark as unsafe.
        """
        self._default_safe = default_safe
        self._dangerous_patterns = dangerous_patterns or [
            "rm -r",
            "format",
            "del /s",
            "mkfs",
            "dd if=",
        ]
        self._validation_history: list = []

    def is_command_safe(self, command: str) -> bool:
        """Check if command is safe by filtering dangerous patterns.

        Args:
            command: Command string to validate.

        Returns:
            True if command is considered safe.
        """
        self._validation_history.append(command)

        # Check against dangerous patterns
        command_lower = command.lower()
        for pattern in self._dangerous_patterns:
            if pattern.lower() in command_lower:
                return False

        return self._default_safe

    @property
    def validation_history(self) -> list:
        """Get history of validated commands."""
        return self._validation_history

    def reset(self) -> None:
        """Reset validation history."""
        self._validation_history = []


class MockKnowledgeBase:
    """Mock knowledge base for testing knowledge management.

    Provides in-memory storage for testing fact storage
    and retrieval without requiring actual database connections.
    """

    def __init__(self):
        """Initialize mock knowledge base."""
        self._facts: list = []
        self._queries: list = []

    async def store_fact(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Store a fact in the mock knowledge base.

        Args:
            content: Fact content to store.
            metadata: Optional metadata for the fact.

        Returns:
            Dict with storage confirmation.
        """
        fact = {
            "id": len(self._facts) + 1,
            "content": content,
            "metadata": metadata or {},
        }
        self._facts.append(fact)
        return {"status": "stored", "id": fact["id"]}

    async def query(
        self,
        query: str,
        limit: int = 10,
    ) -> list:
        """Query the mock knowledge base.

        Args:
            query: Search query.
            limit: Maximum results to return.

        Returns:
            List of matching facts.
        """
        self._queries.append(query)
        query_lower = query.lower()

        # Simple keyword matching
        matches = [
            fact
            for fact in self._facts
            if query_lower in fact["content"].lower()
        ]
        return matches[:limit]

    @property
    def facts(self) -> list:
        """Get all stored facts."""
        return self._facts

    @property
    def query_history(self) -> list:
        """Get history of all queries."""
        return self._queries

    def reset(self) -> None:
        """Reset knowledge base state."""
        self._facts = []
        self._queries = []


class MockWorkerNode:
    """Mock worker node for testing distributed processing.

    Provides simulation of NPU/worker node behavior for
    testing distributed workflows without actual hardware.
    """

    def __init__(
        self,
        node_id: str = "mock-worker-1",
        capabilities: Optional[list] = None,
    ):
        """Initialize mock worker node.

        Args:
            node_id: Identifier for this worker.
            capabilities: List of supported capabilities.
        """
        self.node_id = node_id
        self.capabilities = capabilities or ["text", "vision", "audio"]
        self._tasks_processed: list = []
        self._is_healthy = True

    async def process_task(
        self,
        task: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Process a task on the mock worker.

        Args:
            task: Task to process.

        Returns:
            Processing result.
        """
        self._tasks_processed.append(task)
        return {
            "status": "completed",
            "node_id": self.node_id,
            "task_id": task.get("id", "unknown"),
            "result": f"Mock processed: {task.get('type', 'unknown')}",
        }

    async def health_check(self) -> Dict[str, Any]:
        """Check worker health status.

        Returns:
            Health status dict.
        """
        return {
            "healthy": self._is_healthy,
            "node_id": self.node_id,
            "capabilities": self.capabilities,
            "tasks_processed": len(self._tasks_processed),
        }

    def set_healthy(self, healthy: bool) -> None:
        """Set worker health status for testing.

        Args:
            healthy: Health status to set.
        """
        self._is_healthy = healthy

    @property
    def tasks_processed(self) -> list:
        """Get list of processed tasks."""
        return self._tasks_processed

    def reset(self) -> None:
        """Reset worker state."""
        self._tasks_processed = []
        self._is_healthy = True


__all__ = [
    "MockLLMInterface",
    "MockCommandValidator",
    "MockKnowledgeBase",
    "MockWorkerNode",
]
