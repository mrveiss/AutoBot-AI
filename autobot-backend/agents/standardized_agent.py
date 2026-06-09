# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Standardized Agent Base Class

Provides common implementation patterns for process_request to eliminate
duplication across 24+ agent implementations.

This addresses the critical duplicate pattern identified in the codebase analysis:
- process_request: 24 duplicate implementations
- Standardizes request handling, error management, and response formatting
"""

import asyncio
import time
from abc import abstractmethod
from dataclasses import dataclass
from typing import Any, Callable, Dict, List

from autobot_shared.logging_manager import get_logger
from autobot_shared.prompt_rules import LEDGER_VS_EXECUTOR_RULE
from memory.manager import UnifiedMemoryManager
from prompt_manager import get_language_instruction, resolve_language

from .base_agent import AgentRequest, AgentResponse, BaseAgent, DeploymentMode


@dataclass
class ActionHandler:
    """Configuration for an action handler"""

    handler_method: str
    required_params: List[str] = None
    optional_params: List[str] = None
    description: str = ""


class StandardizedAgent(BaseAgent):
    """
    Standardized base agent that eliminates process_request duplication.

    Features:
    - Automatic action routing based on configuration
    - Standardized error handling and logging
    - Performance monitoring and metrics
    - Consistent response formatting
    - Built-in request validation
    """

    def __init__(self, agent_type: str, deployment_mode: DeploymentMode = DeploymentMode.LOCAL):
        """Initialize standardized agent with action handlers and metrics."""
        super().__init__(agent_type, deployment_mode)
        self.logger = get_logger(f"{__name__}.{agent_type}")

        # Lazy memory facade — created on first access so agents that never
        # use memory don't pay the UnifiedMemoryManager construction cost.
        self._memory_manager: UnifiedMemoryManager | None = None

        # Action handlers mapping - to be configured by subclasses
        self._action_handlers: Dict[str, ActionHandler] = {}

        # Performance tracking
        self._request_count = 0
        self._total_processing_time = 0.0
        self._last_request_time = None

        # Error tracking
        self._error_count = 0
        self._last_error = None

        # Lock for thread-safe counter access
        # Named differently from BaseAgent._stats_lock (threading.Lock)
        self._async_stats_lock = asyncio.Lock()

    @property
    def memory_manager(self) -> UnifiedMemoryManager:
        """Unified memory facade (lazy-init). Subsystems via properties:
        working_memory, essential_story, agent_diary.
        """
        if self._memory_manager is None:
            self._memory_manager = UnifiedMemoryManager()
        return self._memory_manager

    def register_action_handler(self, action: str, handler: ActionHandler):
        """Register an action handler for this agent"""
        self._action_handlers[action] = handler
        self.logger.debug(f"Registered action handler: {action} -> {handler.handler_method}")

    def register_actions(self, actions: Dict[str, ActionHandler]):
        """Register multiple action handlers at once"""
        for action, handler in actions.items():
            self.register_action_handler(action, handler)

    def _validate_action_and_handler(
        self, request: AgentRequest
    ) -> tuple[AgentResponse | None, ActionHandler | None, Callable | None]:
        """Validate action and get handler method (Issue #398: extracted).

        Returns:
            (error_response, handler_config, handler_method) - error_response is set
            if validation fails.
        """
        if not request.action:
            return (
                self._create_error_response(request, "No action specified in request", "validation_error"),
                None,
                None,
            )

        if request.action not in self._action_handlers:
            supported_actions = list(self._action_handlers.keys())
            return (
                self._create_error_response(
                    request,
                    f"Unsupported action '{request.action}'. " f"Supported actions: {supported_actions}",
                    "unsupported_action",
                ),
                None,
                None,
            )

        handler_config = self._action_handlers[request.action]
        validation_error = self._validate_request_params(request, handler_config)
        if validation_error:
            return (
                self._create_error_response(request, validation_error, "validation_error"),
                None,
                None,
            )

        handler_method = getattr(self, handler_config.handler_method, None)
        if not handler_method:
            return (
                self._create_error_response(
                    request,
                    f"Handler method '{handler_config.handler_method}' not found",
                    "configuration_error",
                ),
                None,
                None,
            )

        return None, handler_config, handler_method

    def _get_localized_system_prompt(self, language=None):
        """Get system prompt with language instruction and rules appended.

        Issue #1327: Wraps _get_system_prompt() with language injection.
        Issue #7380: Injects LEDGER_VS_EXECUTOR rule to clarify coordination semantics.
        Resolves language from request param > personality > 'en'.
        English adds no extra instruction.
        """
        base = self._get_system_prompt()
        lang_code = resolve_language(language)
        return base + "\n\n" + LEDGER_VS_EXECUTOR_RULE + "\n\n" + get_language_instruction(lang_code)

    def _build_success_response(self, request: AgentRequest, result: Any, processing_time: float) -> AgentResponse:
        """Build successful response (Issue #398: extracted)."""
        return AgentResponse(
            request_id=request.request_id,
            agent_type=self.agent_type,
            status="success",
            result=result,
            metadata={
                "processing_time": processing_time,
                "action": request.action,
                "agent_stats": self.get_performance_stats(),
            },
        )

    async def _before_process(self, context: dict) -> dict:
        """Load working memory into context before request handling.

        Override in subclasses to enrich the context with session state
        or prior conversation history from ``self.memory_manager.working_memory``.

        Args:
            context: Mutable context dict forwarded from the request.

        Returns:
            Enriched context dict (may be the same object or a new one).
        """
        return context

    async def _after_process(self, context: dict, result: Any) -> None:
        """Persist key outputs to working memory after request handling.

        Override in subclasses to write agent outputs back to
        ``self.memory_manager.working_memory`` so downstream agents can share state.

        Args:
            context: Context dict as returned by _before_process.
            result:  The handler return value (may be None on error).
        """

    async def process_request(self, request: AgentRequest) -> AgentResponse:
        """Standardized request processing (Issue #398: refactored to use helpers)."""
        start_time = time.time()

        async with self._async_stats_lock:
            self._request_count += 1
            self._last_request_time = start_time

        try:
            self.logger.debug(
                "Processing request %s with action: %s",
                request.request_id,
                request.action,
            )

            # --- memory lifecycle: before ---
            context = dict(request.context or {})
            try:
                t0 = time.time()
                context = await self._before_process(context)
                self.logger.debug(
                    "_before_process for %s took %.3fs",
                    request.request_id,
                    time.time() - t0,
                )
            except Exception as hook_exc:
                self.logger.warning(
                    "_before_process hook failed for %s (ignored): %s",
                    request.request_id,
                    hook_exc,
                )

            # Note: enriched context is available to _after_process.
            # Handlers access request.payload directly; context carries
            # cross-hook state (session_id, working memory entries, etc.).

            # Validate and get handler (Issue #398: extracted)
            (
                error_response,
                handler_config,
                handler_method,
            ) = self._validate_action_and_handler(request)
            if error_response:
                return error_response

            result = await self._call_handler_safely(handler_method, request)

            # --- memory lifecycle: after ---
            try:
                t0 = time.time()
                await self._after_process(context, result)
                self.logger.debug(
                    "_after_process for %s took %.3fs",
                    request.request_id,
                    time.time() - t0,
                )
            except Exception as hook_exc:
                self.logger.warning(
                    "_after_process hook failed for %s (ignored): %s",
                    request.request_id,
                    hook_exc,
                )

            processing_time = time.time() - start_time
            async with self._async_stats_lock:
                self._total_processing_time += processing_time

            self.logger.debug(
                "Request %s processed successfully in %.3fs",
                request.request_id,
                processing_time,
            )
            return self._build_success_response(request, result, processing_time)

        except Exception as e:
            # Update error count (thread-safe)
            async with self._async_stats_lock:
                self._error_count += 1
                self._last_error = str(e)

            processing_time = time.time() - start_time
            self.logger.error("Error processing request %s: %s", request.request_id, e)

            return self._create_error_response(
                request,
                f"Processing failed: {str(e)}",
                "processing_error",
                {"processing_time": processing_time, "error_type": type(e).__name__},
            )

    def _validate_request_params(self, request: AgentRequest, handler_config: ActionHandler) -> str | None:
        """Validate request parameters against handler requirements"""
        if not handler_config.required_params:
            return None

        payload = request.payload or {}
        missing_params = []

        for param in handler_config.required_params:
            if param not in payload:
                missing_params.append(param)

        if missing_params:
            return f"Missing required parameters: {missing_params}"

        return None

    async def _call_handler_safely(self, handler_method: Callable, request: AgentRequest) -> Any:
        """Safely call the handler method with error handling"""
        if asyncio.iscoroutinefunction(handler_method):
            return await handler_method(request)
        else:
            return handler_method(request)

    def _create_error_response(
        self,
        request: AgentRequest,
        error_message: str,
        error_type: str,
        extra_metadata: Dict = None,
    ) -> AgentResponse:
        """Create a standardized error response"""
        metadata = {
            "error_type": error_type,
            "timestamp": time.time(),
            "agent_stats": self.get_performance_stats(),
        }
        if extra_metadata:
            metadata.update(extra_metadata)

        return AgentResponse(
            request_id=request.request_id,
            agent_type=self.agent_type,
            status="error",
            result=None,
            error=error_message,
            metadata=metadata,
        )

    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics for this agent"""
        avg_processing_time = self._total_processing_time / self._request_count if self._request_count > 0 else 0.0

        return {
            "request_count": self._request_count,
            "error_count": self._error_count,
            "error_rate": self._error_count / max(self._request_count, 1),
            "avg_processing_time": avg_processing_time,
            "total_processing_time": self._total_processing_time,
            "last_request_time": self._last_request_time,
            "last_error": self._last_error,
        }

    async def health_check(self):
        """Enhanced health check with performance metrics"""
        base_health = await super().health_check()

        # Add performance-based health assessment
        stats = self.get_performance_stats()

        # Determine health based on error rate and response time
        if stats["error_rate"] > 0.1:  # More than 10% error rate
            base_health.status = "degraded"
            base_health.details["performance_issue"] = "High error rate detected"
        elif stats["avg_processing_time"] > 30.0:  # Slower than 30 seconds
            base_health.status = "degraded"
            base_health.details["performance_issue"] = "Slow response times detected"

        # Add stats to health details
        base_health.details.update(
            {
                "performance_stats": stats,
                "supported_actions": list(self._action_handlers.keys()),
            }
        )

        return base_health

    async def cleanup(self):
        """Standardized cleanup with logging (thread-safe)"""
        self.logger.info("Cleaning up %s agent", self.agent_type)

        # Log final stats
        stats = self.get_performance_stats()
        self.logger.info("Final stats: %s", stats)

        # Reset counters (thread-safe)
        async with self._async_stats_lock:
            self._request_count = 0
            self._total_processing_time = 0.0
            self._error_count = 0
            self._last_error = None

        # Call parent cleanup if it exists
        if hasattr(super(), "cleanup"):
            super().cleanup()

    async def _get_mcp_tools_prompt(self, role: str = "user") -> str:
        """Build an MCP tools section for the system prompt (#2596, #2631).

        Fetches available tool definitions from the dispatcher and formats them
        as a Markdown list for LLM injection.  The cache refresh is attempted
        but failures fall through to whatever stale data is available, so a
        transient registry outage never blocks a chat response (#2631).

        Args:
            role: Caller RBAC role — passed to filter admin-only tools (#2629).

        Returns:
            Formatted Markdown string, or "" when no tools are registered.
        """
        from services.mcp_dispatch import get_mcp_dispatcher

        dispatcher = get_mcp_dispatcher()
        try:
            await dispatcher._ensure_cache_fresh()
        except Exception:
            pass  # Use stale cache rather than blocking
        tools = dispatcher.get_tool_definitions(role=role)
        if not tools:
            return ""
        tool_lines = [f"- **{t['name']}**: {t['description']}" for t in tools]
        return (
            "\n\n## Available MCP Tools\n"
            "You can call these tools by name when the user's request requires them:\n" + "\n".join(tool_lines)
        )

    @abstractmethod
    def _get_system_prompt(self) -> str:
        """Return the system prompt for this agent - must be implemented by subclasses."""

    @abstractmethod
    def get_capabilities(self) -> List[str]:
        """Return list of capabilities - must be implemented by subclasses"""

    async def is_available(self) -> bool:
        """In-process default — override in subclasses with external dependencies.

        #6659 promoted ``is_available`` to an abstract method on ``BaseAgent``
        so container-deployed agents can do a network/health probe. The
        contract for in-process StandardizedAgent subclasses is "always
        available unless overridden". Without this default every
        StandardizedAgent subclass crashes at instantiation
        (``TypeError: Can't instantiate abstract class …``), which took down
        the backend at module-load time of the JSONFormatterAgent
        singleton — see backend-error.log on 2026-05-02.
        Subclasses needing an LLM/network probe override this and return
        the probe result.
        """
        return True

    # Convenience methods for common action patterns

    def register_simple_action(
        self,
        action: str,
        method_name: str,
        required_params: List[str] = None,
        description: str = "",
    ):
        """Register a simple action handler"""
        handler = ActionHandler(
            handler_method=method_name,
            required_params=required_params or [],
            description=description,
        )
        self.register_action_handler(action, handler)

    def register_query_action(self, action: str = "query", method_name: str = "process_query"):
        """Register a standard query action"""
        self.register_simple_action(
            action,
            method_name,
            required_params=["query"],
            description="Process a query request",
        )

    def register_chat_action(self, action: str = "chat", method_name: str = "process_chat"):
        """Register a standard chat action"""
        self.register_simple_action(
            action,
            method_name,
            required_params=["message"],
            description="Process a chat message",
        )

    def register_analysis_action(self, action: str = "analyze", method_name: str = "process_analysis"):
        """Register a standard analysis action"""
        self.register_simple_action(
            action,
            method_name,
            required_params=["data"],
            description="Process an analysis request",
        )


# Utility function for easy migration
def create_action_handlers_from_existing_agent(agent_class) -> Dict[str, ActionHandler]:
    """
    Helper function to analyze existing agent and create action handler mappings.
    This can be used to migrate existing agents to the standardized pattern.
    """
    # This would analyze the existing process_request method and extract patterns
    # For now, return empty dict - specific agents need to configure their own handlers
    return {}


# Example usage for migration:
class ExampleMigratedAgent(StandardizedAgent):
    """
    Example of how to migrate an existing agent to use StandardizedAgent.
    This eliminates the duplicate process_request implementation.
    """

    def __init__(self):
        """Initialize example agent with chat and query action handlers."""
        super().__init__("example_agent")

        # Register action handlers instead of implementing process_request
        self.register_actions(
            {
                "chat": ActionHandler(
                    handler_method="handle_chat",
                    required_params=["message"],
                    optional_params=["context", "chat_history"],
                    description="Process chat messages",
                ),
                "query": ActionHandler(
                    handler_method="handle_query",
                    required_params=["query"],
                    optional_params=["context"],
                    description="Process queries",
                ),
            }
        )

    def _get_system_prompt(self) -> str:
        """Return agent system prompt."""
        return "You are a helpful assistant."

    def get_capabilities(self) -> List[str]:
        """Return list of supported agent capabilities."""
        return ["chat", "query", "general_conversation"]

    async def handle_chat(self, request: AgentRequest) -> Dict[str, Any]:
        """Handle chat action - replaces duplicate process_request logic"""
        message = request.payload["message"]
        context = request.payload.get("context", {})

        # Agent-specific logic here
        response = f"Processed message: {message}"

        return {"response": response, "context": context, "timestamp": time.time()}

    async def handle_query(self, request: AgentRequest) -> Dict[str, Any]:
        """Handle query action - replaces duplicate process_request logic"""
        query = request.payload["query"]

        # Agent-specific logic here
        result = f"Query result for: {query}"

        return {"result": result, "query": query, "timestamp": time.time()}
