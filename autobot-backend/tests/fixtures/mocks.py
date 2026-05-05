# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Mock fixtures for AutoBot backend testing (canonical location for #6994).

Provides mock implementations of core components for tests and the
`__main__` demo blocks under `intelligence/`:

- MockLLMInterface  - Legacy mock matching the deleted LLMInterface surface
                      (kept per "never delete code — wire it in" policy).
- MockLLMService    - Mock matching the LLMService surface that replaced
                      LLMInterface in #3185. Returns LLMResponse-shaped
                      objects via `.chat(...)` so demos exercising
                      `IntelligentAgent` / `StreamingCommandExecutor`
                      run offline without network calls.
- MockCommandValidator - Mock validator for command safety testing.
- MockKnowledgeBase    - In-memory knowledge base for testing.
- MockWorkerNode       - Mock NPU/worker node for distributed-flow tests.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


class MockLLMInterface:
    """Legacy mock LLM interface for testing agent workflows.

    Predates the #3185 LLMInterface retirement. Kept for any test that
    still depends on the `generate_response()` surface. New code should
    prefer `MockLLMService`.
    """

    def __init__(self, responses: Optional[Dict[str, str]] = None):
        self._custom_responses = responses or {}
        self._call_count = 0
        self._call_history: list = []

    async def generate_response(self, prompt: str, **kwargs) -> str:
        self._call_count += 1
        self._call_history.append({"prompt": prompt, "kwargs": kwargs})

        for keyword, response in self._custom_responses.items():
            if keyword.lower() in prompt.lower():
                return response

        prompt_lower = prompt.lower()
        if "progress" in prompt_lower:
            return "Processing data..."
        if "completion" in prompt_lower:
            return "Task completed successfully!"
        if "command" in prompt_lower:
            return "COMMAND: echo 'This is a test response'\nEXPLANATION: Testing the system"
        return "Command executing..."

    @property
    def call_count(self) -> int:
        return self._call_count

    @property
    def call_history(self) -> list:
        return self._call_history

    def reset(self) -> None:
        self._call_count = 0
        self._call_history = []


@dataclass
class _MockLLMResponseShim:
    """Duck-typed fallback if `llm_interface_pkg.models.LLMResponse` is
    unavailable at import time. Matches the fields agents/cognifiers read
    (`.content`, `.model`, `.provider`)."""

    content: str
    model: str = "mock"
    provider: str = "mock"
    tokens_used: Optional[int] = None
    processing_time: float = 0.0
    cached: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    usage: Dict[str, int] = field(default_factory=dict)
    finish_reason: str = "stop"
    request_id: str = ""
    error: Optional[str] = None


def _build_mock_response(content: str):
    """Return the real `LLMResponse` if importable, else a duck-typed shim."""
    try:
        from llm_interface_pkg.models import LLMResponse

        return LLMResponse(content=content, model="mock", provider="mock")
    except Exception:
        return _MockLLMResponseShim(content=content)


class MockLLMService:
    """Mock `LLMService` for offline demo / sanity-check runs (#6994 wire-in).

    `IntelligentAgent` and `StreamingCommandExecutor` switched to the
    `LLMService.chat(messages, **kwargs)` surface during the #3185
    `LLMInterface` retirement. Their `__main__` demo blocks need a mock
    exposing that surface — which `MockLLMInterface` (with its legacy
    `generate_response()` method) does not. This class fills the gap.
    """

    def __init__(self, responses: Optional[Dict[str, str]] = None):
        self._custom_responses = responses or {}
        self._call_count = 0
        self._call_history: List[Dict[str, Any]] = []

    async def chat(self, messages, **kwargs):
        """Return a deterministic `LLMResponse` for the last user message."""
        self._call_count += 1
        prompt = self._extract_prompt(messages)
        self._call_history.append({"prompt": prompt, "kwargs": kwargs})
        return _build_mock_response(self._select_response(prompt))

    async def chat_optimized(self, messages, **kwargs):
        return await self.chat(messages, **kwargs)

    async def generate(self, prompt: str, **kwargs):
        return await self.chat([{"role": "user", "content": prompt}], **kwargs)

    async def get_metrics(self) -> Dict[str, Any]:
        return {"calls": self._call_count, "provider": "mock", "cached": 0}

    @staticmethod
    def _extract_prompt(messages) -> str:
        if isinstance(messages, str):
            return messages
        if isinstance(messages, list) and messages:
            last = messages[-1]
            if isinstance(last, dict):
                return str(last.get("content", ""))
            return str(last)
        return ""

    def _select_response(self, prompt: str) -> str:
        for keyword, response in self._custom_responses.items():
            if keyword.lower() in prompt.lower():
                return response

        prompt_lower = prompt.lower()
        if "command" in prompt_lower:
            return "COMMAND: echo 'mock LLM response'\n" "EXPLANATION: Demo path — no real LLM was called."
        if "progress" in prompt_lower:
            return "Processing data..."
        if "complet" in prompt_lower:
            return "Task completed successfully!"
        return "Mock LLM response."

    @property
    def call_count(self) -> int:
        return self._call_count

    @property
    def call_history(self) -> list:
        return self._call_history

    def reset(self) -> None:
        self._call_count = 0
        self._call_history = []


class MockCommandValidator:
    """Mock command validator for testing command safety."""

    def __init__(
        self,
        default_safe: bool = True,
        dangerous_patterns: Optional[list] = None,
    ):
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
        self._validation_history.append(command)
        command_lower = command.lower()
        for pattern in self._dangerous_patterns:
            if pattern.lower() in command_lower:
                return False
        return self._default_safe

    @property
    def validation_history(self) -> list:
        return self._validation_history

    def reset(self) -> None:
        self._validation_history = []


class MockKnowledgeBase:
    """In-memory mock knowledge base for testing."""

    def __init__(self):
        self._facts: list = []
        self._queries: list = []

    async def store_fact(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        fact = {
            "id": len(self._facts) + 1,
            "content": content,
            "metadata": metadata or {},
        }
        self._facts.append(fact)
        return {"status": "stored", "id": fact["id"]}

    async def query(self, query: str, limit: int = 10) -> list:
        self._queries.append(query)
        query_lower = query.lower()
        matches = [f for f in self._facts if query_lower in f["content"].lower()]
        return matches[:limit]

    @property
    def facts(self) -> list:
        return self._facts

    @property
    def query_history(self) -> list:
        return self._queries

    def reset(self) -> None:
        self._facts = []
        self._queries = []


class MockWorkerNode:
    """Mock worker node for testing distributed processing."""

    def __init__(
        self,
        node_id: str = "mock-worker-1",
        capabilities: Optional[list] = None,
    ):
        self.node_id = node_id
        self.capabilities = capabilities or ["text", "vision", "audio"]
        self._tasks_processed: list = []
        self._is_healthy = True

    async def process_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        self._tasks_processed.append(task)
        return {
            "status": "completed",
            "node_id": self.node_id,
            "task_id": task.get("id", "unknown"),
            "result": f"Mock processed: {task.get('type', 'unknown')}",
        }

    async def health_check(self) -> Dict[str, Any]:
        return {
            "healthy": self._is_healthy,
            "node_id": self.node_id,
            "capabilities": self.capabilities,
            "tasks_processed": len(self._tasks_processed),
        }

    def set_healthy(self, healthy: bool) -> None:
        self._is_healthy = healthy

    @property
    def tasks_processed(self) -> list:
        return self._tasks_processed

    def reset(self) -> None:
        self._tasks_processed = []
        self._is_healthy = True


__all__ = [
    "MockLLMInterface",
    "MockLLMService",
    "MockCommandValidator",
    "MockKnowledgeBase",
    "MockWorkerNode",
]
