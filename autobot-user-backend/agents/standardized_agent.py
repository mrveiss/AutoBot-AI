# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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
import logging
import time
from abc import abstractmethod
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional


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

    def __init__(
        self, agent_type: str, deployment_mode: DeploymentMode = DeploymentMode.LOCAL
    ):
        """Initialize standardized agent with action handlers and metrics."""
        super().__init__(agent_type, deployment_mode)
        self.logger = logging.getLogger(f"{__name__}.{agent_type}")

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
        self._stats_lock = asyncio.Lock()

    def register_action_handler(self, action: str, handler: ActionHandler):
        """Register an action handler for this agent"""
        self._action_handlers[action] = handler
        self.logger.debug(
            f"Registered action handler: {action} -> {handler.handler_method}"
        )

    def register_actions(self, actions: Dict[str, ActionHandler]):
        """Register multiple action handlers at once"""
        for action, handler in actions.items():
            self.register_action_handler(action, handler)

    def _validate_action_and_handler(
        self, request: AgentRequest
    ) -> tuple[Optional[AgentResponse], Optional[ActionHandler], Optional[Callable]]:
        """Validate action and get handler method (Issue #398: extracted).

        Returns:
            (error_response, handler_config, handler_method) - error_response is set if validation fails
        """
        if not request.action:
            return (
                self._create_error_response(request, "No action specified in request", "validation_error"),
                None, None
            )

        if request.action not in self._action_handlers:
            supported_actions = list(self._action_handlers.keys())
            return (
                self._create_error_response(
                    request,
                    f"Unsupported action '{request.action}'. Supported actions: {supported_actions}",
                    "unsupported_action",
                ),
                None, None
            )

        handler_config = self._action_handlers[request.action]
        validation_error = self._validate_request_params(request, handler_config)
        if validation_error:
            return (
                self._create_error_response(request, validation_error, "validation_error"),
                None, None
            )

        handler_method = getattr(self, handler_config.handler_method, None)
        if not handler_method:
            return (
                self._create_error_response(
                    request,
                    f"Handler method '{handler_config.handler_method}' not found",
                    "configuration_error",
                ),
                None, None
            )

        return None, handler_config, handler_method

    def _build_success_response(
        self, request: AgentRequest, result: Any, processing_time: float
    ) -> AgentResponse:
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

    async def process_request(self, request: AgentRequest) -> AgentResponse:
        """Standardized request processing (Issue #398: refactored to use helpers)."""
        start_time = time.time()

        async with self._stats_lock:
            self._request_count += 1
            self._last_request_time = start_time

        try:
            self.logger.debug("Processing request %s with action: %s", request.request_id, request.action)

            # Validate and get handler (Issue #398: extracted)
            error_response, handler_config, handler_method = self._validate_action_and_handler(request)
            if error_response:
                return error_response

            result = await self._call_handler_safely(handler_method, request)

            processing_time = time.time() - start_time
            async with self._stats_lock:
                self._total_processing_time += processing_time

            self.logger.debug("Request %s processed successfully in %.3fs", request.request_id, processing_time)
            return self._build_success_response(request, result, processing_time)

        except Exception as e:
            # Update error count (thread-safe)
            async with self._stats_lock:
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

    def _validate_request_params(
        self, request: AgentRequest, handler_config: ActionHandler
    ) -> Optional[str]:
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

    async def _call_handler_safely(
        self, handler_method: Callable, request: AgentRequest
    ) -> Any:
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
        avg_processing_time = (
            self._total_processing_time / self._request_count
            if self._request_count > 0
            else 0.0
        )

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
        async with self._stats_lock:
            self._request_count = 0
            self._total_processing_time = 0.0
            self._error_count = 0
            self._last_error = None

        # Call parent cleanup if it exists
        if hasattr(super(), "cleanup"):
            super().cleanup()

    @abstractmethod
    def get_capabilities(self) -> List[str]:
        """Return list of capabilities - must be implemented by subclasses"""

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

    def register_query_action(
        self, action: str = "query", method_name: str = "process_query"
    ):
        """Register a standard query action"""
        self.register_simple_action(
            action,
            method_name,
            required_params=["query"],
            description="Process a query request",
        )

    def register_chat_action(
        self, action: str = "chat", method_name: str = "process_chat"
    ):
        """Register a standard chat action"""
        self.register_simple_action(
            action,
            method_name,
            required_params=["message"],
            description="Process a chat message",
        )

    def register_analysis_action(
        self, action: str = "analyze", method_name: str = "process_analysis"
    ):
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
