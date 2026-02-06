# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Base Extension class for the extension hooks system.

Issue #658: Implements Agent Zero's extension pattern where extensions
can hook into 22 lifecycle points to modify agent behavior.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.extensions.hooks import HookPoint

logger = logging.getLogger(__name__)


@dataclass
class HookContext:
    """
    Context passed to all hook invocations.

    This dataclass carries all relevant information about the current
    operation and provides methods for extensions to read/modify data.

    Attributes:
        session_id: Current chat session ID
        message: Original user message
        agent_id: ID of the current agent (for hierarchical agents)
        data: Shared data dictionary for extensions to communicate

    Usage:
        # Read data set by previous extension
        prompt = ctx.get("prompt", "")

        # Modify data for subsequent extensions
        ctx.set("prompt", modified_prompt)

        # Store multiple values
        ctx.merge({"key1": "value1", "key2": "value2"})
    """

    session_id: str = ""
    message: str = ""
    agent_id: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)

    def set(self, key: str, value: Any) -> None:
        """
        Set a value in the context data.

        Args:
            key: Data key
            value: Data value
        """
        self.data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a value from the context data.

        Args:
            key: Data key
            default: Default value if key not found

        Returns:
            The value or default
        """
        return self.data.get(key, default)

    def merge(self, updates: Dict[str, Any]) -> None:
        """
        Merge multiple values into context data.

        Args:
            updates: Dictionary of key-value pairs to merge
        """
        self.data.update(updates)

    def has(self, key: str) -> bool:
        """
        Check if a key exists in context data.

        Args:
            key: Data key

        Returns:
            True if key exists
        """
        return key in self.data

    def remove(self, key: str) -> Optional[Any]:
        """
        Remove and return a value from context data.

        Args:
            key: Data key

        Returns:
            The removed value or None
        """
        return self.data.pop(key, None)

    def to_dict(self) -> Dict[str, Any]:
        """Convert context to dictionary for serialization."""
        return {
            "session_id": self.session_id,
            "message": self.message,
            "agent_id": self.agent_id,
            "data": self.data,
        }


class Extension:
    """
    Base class for extensions.

    Issue #658: Extensions can hook into 22 lifecycle points to modify
    agent behavior without changing core code. Override hook methods
    as needed in subclasses.

    Attributes:
        name: Unique extension name for identification
        priority: Execution order (lower = runs first, default 100)
        enabled: Whether extension is active

    Usage:
        class MyExtension(Extension):
            name = "my_extension"
            priority = 50  # Run before default (100)

            async def on_before_tool_execute(self, ctx: HookContext) -> Optional[bool]:
                # Return False to cancel tool execution
                if ctx.get("tool_name") == "dangerous_tool":
                    return False
                return None  # Continue normally
    """

    name: str = "base"
    priority: int = 100
    enabled: bool = True

    async def on_hook(
        self,
        hook: HookPoint,
        context: HookContext,
    ) -> Optional[Any]:
        """
        Dispatch to specific hook method.

        This method is called by ExtensionManager and routes to the
        appropriate on_<hook_name> method.

        Args:
            hook: The hook point being invoked
            context: Hook context with relevant data

        Returns:
            Result from the specific hook method or None
        """
        if not self.enabled:
            return None

        # Convert hook name to method name: BEFORE_MESSAGE_PROCESS -> on_before_message_process
        method_name = f"on_{hook.name.lower()}"
        method = getattr(self, method_name, None)

        if method and callable(method):
            try:
                return await method(context)
            except Exception as e:
                logger.error(
                    "[Issue #658] Extension %s error on %s: %s",
                    self.name,
                    hook.name,
                    str(e),
                )
                # Don't re-raise - extension errors shouldn't crash the system
                return None

        return None

    # ========== Message Preparation Hooks ==========

    async def on_before_message_process(self, ctx: HookContext) -> Optional[None]:
        """
        Called at the start of message handling.

        Use to preprocess the message or initialize extension state.

        Args:
            ctx: Hook context with message

        Returns:
            None (modify ctx.data directly)
        """

    async def on_after_prompt_build(self, ctx: HookContext) -> Optional[str]:
        """
        Called after system prompt is built.

        Use to modify or append to the prompt.

        Args:
            ctx: Hook context with prompt in data["prompt"]

        Returns:
            Modified prompt string or None to keep unchanged
        """

    # ========== LLM Interaction Hooks ==========

    async def on_before_llm_call(self, ctx: HookContext) -> Optional[bool]:
        """
        Called before calling the LLM.

        Use to modify prompt, change model, or cancel the call.

        Args:
            ctx: Hook context with prompt and model in data

        Returns:
            False to cancel LLM call, None to continue
        """

    async def on_during_llm_streaming(self, ctx: HookContext) -> Optional[str]:
        """
        Called for each streaming chunk from LLM.

        Use to modify or filter streaming content.

        Args:
            ctx: Hook context with chunk in data["chunk"]

        Returns:
            Modified chunk or None to keep unchanged
        """

    async def on_after_llm_response(self, ctx: HookContext) -> Optional[str]:
        """
        Called after full response is received.

        Use to post-process the complete LLM response.

        Args:
            ctx: Hook context with response in data["response"]

        Returns:
            Modified response or None to keep unchanged
        """

    # ========== Tool Execution Hooks ==========

    async def on_before_tool_parse(self, ctx: HookContext) -> Optional[str]:
        """
        Called before parsing tool calls from response.

        Use to modify response before tool parsing.

        Args:
            ctx: Hook context with response in data["response"]

        Returns:
            Modified response or None to keep unchanged
        """

    async def on_before_tool_execute(self, ctx: HookContext) -> Optional[bool]:
        """
        Called before each tool execution.

        Use to validate, modify, or cancel tool execution.

        Args:
            ctx: Hook context with tool_call in data

        Returns:
            False to cancel execution, None to continue
        """

    async def on_after_tool_execute(self, ctx: HookContext) -> Optional[Any]:
        """
        Called after tool execution completes.

        Use to post-process tool results.

        Args:
            ctx: Hook context with result in data["result"]

        Returns:
            Modified result or None to keep unchanged
        """

    async def on_tool_error(self, ctx: HookContext) -> Optional[Any]:
        """
        Called when a tool throws an error.

        Use to convert errors to RepairableException or handle.

        Args:
            ctx: Hook context with error in data["error"]

        Returns:
            RepairableException or None to use default handling
        """

    # ========== Continuation Loop Hooks ==========

    async def on_before_continuation(self, ctx: HookContext) -> Optional[bool]:
        """
        Called before LLM continuation iteration.

        Use to modify context or stop the continuation loop.

        Args:
            ctx: Hook context with iteration info

        Returns:
            False to stop loop, None to continue
        """

    async def on_after_continuation(self, ctx: HookContext) -> Optional[None]:
        """
        Called after each continuation iteration.

        Use for logging or state updates.

        Args:
            ctx: Hook context with iteration results

        Returns:
            None
        """

    async def on_loop_complete(self, ctx: HookContext) -> Optional[None]:
        """
        Called when message loop completes.

        Use for cleanup or final processing.

        Args:
            ctx: Hook context with final_response

        Returns:
            None
        """

    # ========== Error Handling Hooks ==========

    async def on_repairable_error(self, ctx: HookContext) -> Optional[str]:
        """
        Called when a repairable error occurs.

        Use to modify suggestion or add context.

        Args:
            ctx: Hook context with error and suggestion

        Returns:
            Modified suggestion or None to keep unchanged
        """

    async def on_critical_error(self, ctx: HookContext) -> Optional[None]:
        """
        Called when a critical error occurs.

        Use for logging or alerting only.

        Args:
            ctx: Hook context with error

        Returns:
            None (logging only)
        """

    # ========== Response Hooks ==========

    async def on_before_response_send(self, ctx: HookContext) -> Optional[str]:
        """
        Called before sending response via WebSocket.

        Use to modify or filter outgoing responses.

        Args:
            ctx: Hook context with response in data

        Returns:
            Modified response or None to keep unchanged
        """

    async def on_after_response_send(self, ctx: HookContext) -> Optional[None]:
        """
        Called after response is sent.

        Use for logging or metrics only.

        Args:
            ctx: Hook context

        Returns:
            None (logging only)
        """

    # ========== Session Lifecycle Hooks ==========

    async def on_session_create(self, ctx: HookContext) -> Optional[None]:
        """
        Called when a new session is created.

        Use to initialize session-specific state.

        Args:
            ctx: Hook context with session info

        Returns:
            None
        """

    async def on_session_destroy(self, ctx: HookContext) -> Optional[None]:
        """
        Called when a session is destroyed.

        Use for cleanup only.

        Args:
            ctx: Hook context with session info

        Returns:
            None (cleanup only)
        """

    # ========== Knowledge Integration Hooks ==========

    async def on_before_rag_query(self, ctx: HookContext) -> Optional[str]:
        """
        Called before querying knowledge base.

        Use to modify the query or add filters.

        Args:
            ctx: Hook context with query in data

        Returns:
            Modified query or None to keep unchanged
        """

    async def on_after_rag_results(
        self, ctx: HookContext
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Called after RAG results are retrieved.

        Use to filter, rank, or modify results.

        Args:
            ctx: Hook context with results and citations

        Returns:
            Modified results or None to keep unchanged
        """

    # ========== Approval Flow Hooks ==========

    async def on_approval_required(self, ctx: HookContext) -> Optional[bool]:
        """
        Called when tool requires user approval.

        Use to auto-approve or modify approval request.

        Args:
            ctx: Hook context with tool_call and message

        Returns:
            True to auto-approve, None for normal flow
        """

    async def on_approval_received(self, ctx: HookContext) -> Optional[None]:
        """
        Called when user approval is received.

        Use for logging or analytics.

        Args:
            ctx: Hook context with approval info

        Returns:
            None (logging only)
        """

    # ========== Utility Methods ==========

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(name='{self.name}', priority={self.priority})"
        )
