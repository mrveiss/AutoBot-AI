# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Base Agent Interface for Hybrid Local/Remote Deployment
Provides unified interface for agents running locally or in containers
"""

import asyncio
import json
import threading
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config
from autobot_shared.status_enums import AgentStatus  # #7504 consolidation

# Import communication protocol
from constants.threshold_constants import TimingConstants
from protocols.agent_communication import (
    AgentIdentity,
    MessageHeader,
    MessagePayload,
    MessageType,
    StandardMessage,
    get_communication_manager,
)

logger = get_logger(__name__)


class DeploymentMode(Enum):
    """Agent deployment modes"""

    LOCAL = "local"
    CONTAINER = "container"
    REMOTE = "remote"


# Performance optimization: O(1) lookup for available agent statuses (Issue #326)
AVAILABLE_AGENT_STATUSES = {AgentStatus.HEALTHY, AgentStatus.DEGRADED}


@dataclass
class AgentRequest:
    """Standardized agent request format"""

    request_id: str
    agent_type: str
    action: str
    payload: Dict[str, Any]
    context: Dict[str, Any] | None = None
    priority: str = "normal"  # low, normal, high, urgent
    timeout: float = 30.0
    metadata: Dict[str, Any] | None = None


@dataclass
class AgentResponse:
    """Standardized agent response format"""

    request_id: str
    agent_type: str
    status: str  # success, error, partial
    result: Any
    error: str | None = None
    execution_time: float = 0.0
    metadata: Dict[str, Any] | None = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "request_id": self.request_id,
            "agent_type": self.agent_type,
            "status": self.status,
            "result": self.result,
            "error": self.error,
            "execution_time": self.execution_time,
            "metadata": self.metadata or {},
        }


@dataclass
class AgentHealth:
    """Agent health information"""

    agent_type: str
    status: AgentStatus
    deployment_mode: DeploymentMode
    last_heartbeat: datetime
    response_time_ms: float
    success_rate: float
    error_count: int
    resource_usage: Dict[str, Any]
    capabilities: List[str]
    details: Dict[str, Any] | None = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "agent_type": self.agent_type,
            "status": self.status.value,
            "deployment_mode": self.deployment_mode.value,
            "last_heartbeat": self.last_heartbeat.isoformat(),
            "response_time_ms": self.response_time_ms,
            "success_rate": self.success_rate,
            "error_count": self.error_count,
            "resource_usage": self.resource_usage,
            "capabilities": self.capabilities,
            "details": self.details or {},
        }


class BaseAgent(ABC):
    """
    Abstract base class for all AutoBot agents.
    Designed for hybrid local/container deployment.
    """

    def __init__(self, agent_type: str, deployment_mode: DeploymentMode = DeploymentMode.LOCAL):
        """Initialize base agent with type, deployment mode, and tracking."""
        self.agent_type = agent_type
        self.deployment_mode = deployment_mode
        self.capabilities: List[str] = []
        self.startup_time = datetime.now(tz=timezone.utc)

        # Performance tracking (protected by _stats_lock)
        self.request_count = 0
        self.success_count = 0
        self.error_count = 0
        self.total_execution_time = 0.0
        self._stats_lock = threading.Lock()

        # Communication protocol integration
        self.agent_id = f"{agent_type}_{uuid.uuid4().hex[:8]}"
        self.communication_protocol = None
        self._message_handlers = {}
        self._handlers_lock = threading.Lock()

        # Per-agent diary (fire-and-forget; never blocks a turn)
        from memory.agent_diary import AgentDiaryService

        self._diary = AgentDiaryService()

        logger.info("Initialized %s agent in %s mode", agent_type, deployment_mode.value)

    @abstractmethod
    async def process_request(self, request: AgentRequest) -> AgentResponse:
        """
        Main request processing method.
        Must be implemented by all agents.
        """

    @abstractmethod
    def get_capabilities(self) -> List[str]:
        """
        Return list of capabilities this agent supports.
        Used for request routing and service discovery.
        """

    @abstractmethod
    async def is_available(self) -> bool:
        """
        Return whether this agent is currently available for processing.

        Issue #6659: Promoted from per-subclass implementation to abstract
        contract.  Required to be ``async`` because container-deployed agents
        need to make a network/health-check call; in-process agents can simply
        ``return True`` synchronously inside the coroutine.  Callers MUST
        ``await`` the result regardless of deployment mode.
        """

    async def health_check(self) -> AgentHealth:
        """
        Return current health status of the agent.
        Used by container orchestration and load balancers.
        """
        try:
            # Test basic functionality via ping
            start_time = datetime.now(tz=timezone.utc)
            await self._ping()
            response_time = (datetime.now(tz=timezone.utc) - start_time).total_seconds() * 1000

            status = AgentStatus.HEALTHY
            if response_time > 5000:  # 5 second threshold
                status = AgentStatus.DEGRADED

            # Read counters under lock (thread-safe)
            with self._stats_lock:
                success_count = self.success_count
                request_count = self.request_count
                error_count = self.error_count

            success_rate = (success_count / max(request_count, 1)) * 100

            return AgentHealth(
                agent_type=self.agent_type,
                status=status,
                deployment_mode=self.deployment_mode,
                last_heartbeat=datetime.now(tz=timezone.utc),
                response_time_ms=response_time,
                success_rate=success_rate,
                error_count=error_count,
                resource_usage=await self._get_resource_usage(),
                capabilities=self.get_capabilities(),
                details={},
            )

        except Exception as e:
            logger.error("Health check failed for %s: %s", self.agent_type, e)
            # Read error count under lock
            with self._stats_lock:
                error_count = self.error_count
            return AgentHealth(
                agent_type=self.agent_type,
                status=AgentStatus.UNHEALTHY,
                deployment_mode=self.deployment_mode,
                last_heartbeat=datetime.now(tz=timezone.utc),
                response_time_ms=0.0,
                success_rate=0.0,
                error_count=error_count + 1,
                resource_usage={},
                capabilities=[],
                details={},
            )

    async def _ping(self) -> bool:
        """Basic connectivity test - can be overridden by subclasses"""
        await asyncio.sleep(TimingConstants.YIELD_INTERVAL)  # Simulate minimal processing
        return True

    async def _get_resource_usage(self) -> Dict[str, Any]:
        """Get current resource usage - can be overridden by subclasses"""
        import os

        import psutil

        try:
            process = psutil.Process(os.getpid())
            memory_info = process.memory_info()

            return {
                "cpu_percent": process.cpu_percent(),
                "memory_rss_mb": memory_info.rss / 1024 / 1024,
                "memory_vms_mb": memory_info.vms / 1024 / 1024,
                "num_threads": process.num_threads(),
                "uptime_seconds": (datetime.now(tz=timezone.utc) - self.startup_time).total_seconds(),
            }
        except Exception as e:
            logger.warning("Could not get resource usage: %s", e)
            return {"error": "Resource usage unavailable"}

    async def execute_with_tracking(self, request: AgentRequest) -> AgentResponse:
        """
        Wrapper that adds performance tracking to request processing.
        Used by agent clients for monitoring.

        Persists each invocation to AgentAnalytics (Redis db=ANALYTICS) so
        usage data is queryable via GET /api/agents/usage.
        """
        start_time = datetime.now(tz=timezone.utc)
        task_id = str(uuid.uuid4())

        # Increment request count (thread-safe)
        with self._stats_lock:
            self.request_count += 1

        # Record invocation start in Redis analytics
        try:
            from services.agent_analytics import TaskStatus, get_agent_analytics

            analytics = get_agent_analytics()
            await analytics.track_task_start(
                agent_id=self.agent_type,
                agent_type=self.agent_type,
                task_id=task_id,
                task_name=request.action or "process_request",
                metadata={
                    "request_id": request.request_id,
                    "priority": request.priority,
                },
            )
        except Exception as analytics_err:
            logger.debug("Analytics track_task_start failed: %s", analytics_err)
            analytics = None

        try:
            response = await self.process_request(request)

            execution_time = (datetime.now(tz=timezone.utc) - start_time).total_seconds()

            # Update counters (thread-safe)
            with self._stats_lock:
                if response.status == "success":
                    self.success_count += 1
                else:
                    self.error_count += 1
                self.total_execution_time += execution_time

            response.execution_time = execution_time

            # Fire-and-forget diary write — never blocks the caller (#5071)
            _diary_entry = (f"action={request.action} status={response.status} " f"exec={execution_time:.2f}s")[:200]
            asyncio.create_task(
                self._diary.write(
                    self.agent_type,
                    request.request_id,
                    _diary_entry,
                    topic="turn",
                )
            )

            # Publish OBSERVATION event with any artifacts the agent collected (#4094)
            await self._publish_completion_observation(request, response, task_id)

            # Record completion in Redis analytics
            if analytics is not None:
                try:
                    outcome = TaskStatus.COMPLETED if response.status == "success" else TaskStatus.FAILED
                    tokens = response.metadata.get("token_usage") if response.metadata else None
                    await analytics.track_task_complete(
                        task_id=task_id,
                        status=outcome,
                        tokens_used=tokens,
                        error_message=response.error,
                    )
                except Exception as analytics_err:
                    logger.debug("Analytics track_task_complete failed: %s", analytics_err)

            return response

        except Exception as e:
            execution_time = (datetime.now(tz=timezone.utc) - start_time).total_seconds()

            # Increment error count (thread-safe)
            with self._stats_lock:
                self.error_count += 1

            # Record failure in Redis analytics
            if analytics is not None:
                try:
                    from services.agent_analytics import TaskStatus

                    await analytics.track_task_complete(
                        task_id=task_id,
                        status=TaskStatus.FAILED,
                        error_message=str(e),
                    )
                except Exception as analytics_err:
                    logger.debug("Analytics failure record failed: %s", analytics_err)

            logger.error("Agent %s error: %s", self.agent_type, e)
            return AgentResponse(
                request_id=request.request_id,
                agent_type=self.agent_type,
                status="error",
                result=None,
                error=str(e),
                execution_time=execution_time,
            )

    async def _publish_completion_observation(
        self,
        request: AgentRequest,
        response: AgentResponse,
        task_id: str,
    ) -> None:
        """
        Emit an OBSERVATION event carrying any TaskArtifacts produced by the
        agent.  Artifacts are read from ``response.metadata["artifacts"]``
        which should be a list of dicts matching the TaskArtifact schema.

        Failures are logged at DEBUG level so they never break the caller.
        """
        artifacts_raw = (response.metadata or {}).get("artifacts")
        if not artifacts_raw:
            return

        try:
            from events.stream_manager import RedisEventStreamManager
            from events.types import TaskArtifact, create_observation_event

            artifacts = [TaskArtifact.from_dict(a) if isinstance(a, dict) else a for a in artifacts_raw]

            obs_event = create_observation_event(
                action_id=request.request_id,
                tool_name=self.agent_type,
                success=response.status == "success",
                result=(response.result if isinstance(response.result, (str, type(None))) else str(response.result)),
                error=response.error,
                execution_time_ms=response.execution_time * 1000,
                task_id=task_id,
                artifacts=artifacts,
            )

            manager = RedisEventStreamManager()
            await manager.publish(obs_event)
            logger.debug(
                "Published completion observation with %d artifact(s) for task %s",
                len(artifacts),
                task_id,
            )
        except Exception as exc:
            logger.debug(
                "Could not publish completion observation for task %s: %s",
                task_id,
                exc,
            )

    # Communication Protocol Methods
    async def initialize_communication(self, capabilities: List[str] = None) -> bool:
        """Initialize agent communication protocol"""
        try:
            # Create agent identity
            identity = AgentIdentity(
                agent_id=self.agent_id,
                agent_type=self.agent_type,
                capabilities=capabilities or self.capabilities,
                supported_patterns=[],
                health_status="healthy",
            )

            # Register with communication manager
            manager = get_communication_manager()
            channel_configs = [
                {"type": "direct", "id": f"{self.agent_id}_direct"},
                {"type": "redis", "id": f"{self.agent_id}_redis"},
            ]

            self.communication_protocol = await manager.register_agent(identity, channel_configs)

            # Register default message handlers
            self.communication_protocol.register_message_handler(
                MessageType.REQUEST, self._handle_communication_request
            )

            logger.info("Agent %s communication initialized", self.agent_id)
            return True

        except Exception as e:
            logger.error("Failed to initialize communication for %s: %s", self.agent_id, e)
            return False

    async def _handle_communication_request(self, message: StandardMessage) -> StandardMessage | None:
        """Handle incoming communication requests"""
        try:
            # Convert communication message to AgentRequest
            request_data = message.payload.content
            agent_request = AgentRequest(
                request_id=message.header.message_id,
                agent_type=self.agent_type,
                action=request_data.get("action", "process"),
                payload=request_data.get("payload", {}),
                context=request_data.get("context", {}),
                priority=request_data.get("priority", "normal"),
            )

            # Process the request
            response = await self.process_request(agent_request)

            # Convert AgentResponse back to communication message
            response_message = StandardMessage(
                header=MessageHeader(message_type=MessageType.RESPONSE),
                payload=MessagePayload(
                    content={
                        "status": response.status,
                        "result": response.result,
                        "error": response.error,
                        "execution_time": response.execution_time,
                    }
                ),
            )

            return response_message

        except Exception as e:
            logger.error("Error handling communication request: %s", e)
            # Return error response
            return StandardMessage(
                header=MessageHeader(message_type=MessageType.ERROR),
                payload=MessagePayload(
                    content={
                        "error": "Communication request failed",
                        "error_type": type(e).__name__,
                    }
                ),
            )

    async def send_message_to_agent(self, recipient_id: str, message_data: Any, timeout: float = 30.0) -> Any | None:
        """Send a message to another agent"""
        if not self.communication_protocol:
            logger.error("Communication not initialized for agent %s", self.agent_id)
            return None

        try:
            from protocols.agent_communication import send_agent_request

            return await send_agent_request(self.agent_id, recipient_id, message_data, timeout)
        except Exception as e:
            logger.error("Error sending message to %s: %s", recipient_id, e)
            return None

    async def broadcast_message(self, message_data: Any) -> int:
        """Broadcast a message to all agents"""
        if not self.communication_protocol:
            logger.error("Communication not initialized for agent %s", self.agent_id)
            return 0

        try:
            from protocols.agent_communication import broadcast_to_all_agents

            return await broadcast_to_all_agents(self.agent_id, message_data)
        except Exception as e:
            logger.error("Error broadcasting message: %s", e)
            return 0

    async def shutdown_communication(self):
        """Shutdown agent communication"""
        if self.communication_protocol:
            try:
                manager = get_communication_manager()
                await manager.unregister_agent(self.agent_id)
                self.communication_protocol = None
                logger.info("Agent %s communication shutdown", self.agent_id)
            except Exception as e:
                logger.error("Error shutting down communication: %s", e)

    def get_mcp_token(self) -> str:
        """Return the auth token to use for MCP JSON-RPC calls (SEC-2 Phase 2, #6473).

        Prefers the run-scoped JWT set by the heartbeat scheduler via
        ``AUTOBOT_RUN_JWT``.  Falls back to the long-lived ``AUTOBOT_MCP_TOKEN``
        for direct user-driven calls that run outside a scheduled heartbeat.

        Usage::

            token = self.get_mcp_token()
            params = {"name": tool, "arguments": args}
            if token.count(".") == 2:  # JWT format
                params["run_jwt"] = token
            else:
                auth = token  # legacy bearer token
        """
        return config.run_jwt or config.mcp_token

    def get_statistics(self) -> Dict[str, Any]:
        """Get performance statistics for this agent (thread-safe)"""
        # Read all counters under lock
        with self._stats_lock:
            request_count = self.request_count
            success_count = self.success_count
            error_count = self.error_count
            total_execution_time = self.total_execution_time

        avg_execution_time = total_execution_time / max(request_count, 1)

        return {
            "agent_type": self.agent_type,
            "deployment_mode": self.deployment_mode.value,
            "total_requests": request_count,
            "successful_requests": success_count,
            "failed_requests": error_count,
            "success_rate": (success_count / max(request_count, 1)) * 100,
            "avg_execution_time_seconds": avg_execution_time,
            "total_execution_time_seconds": total_execution_time,
            "uptime_seconds": (datetime.now(tz=timezone.utc) - self.startup_time).total_seconds(),
        }


class LocalAgent(BaseAgent):
    """
    Base class for agents running locally (same process).
    Provides direct method calls for maximum performance.
    """

    def __init__(self, agent_type: str):
        """Initialize local agent with given type in local deployment mode."""
        super().__init__(agent_type, DeploymentMode.LOCAL)

    async def is_available(self) -> bool:
        """Check if agent is available for processing.

        Issue #6659: Async to match the BaseAgent contract; LocalAgent has no
        I/O to perform so the coroutine resolves immediately.
        """
        return True


class ContainerAgent(BaseAgent):
    """
    Base class for agents running in containers.
    Provides HTTP/gRPC communication interface.
    """

    def __init__(self, agent_type: str, container_url: str):
        """Initialize container agent with type and remote container URL."""
        super().__init__(agent_type, DeploymentMode.CONTAINER)
        self.container_url = container_url
        self.session = None  # Will be initialized with aiohttp session

    async def is_available(self) -> bool:
        """Check if container agent is available"""
        try:
            health = await self.health_check()
            return health.status in AVAILABLE_AGENT_STATUSES
        except Exception:
            return False


# Utility functions for agent management


def create_agent_request(
    agent_type: str,
    action: str,
    payload: Dict[str, Any],
    context: Dict[str, Any] | None = None,
    priority: str = "normal",
    timeout: float = 30.0,
) -> AgentRequest:
    """Helper function to create standardized agent requests"""
    import uuid

    return AgentRequest(
        request_id=str(uuid.uuid4()),
        agent_type=agent_type,
        action=action,
        payload=payload,
        context=context or {},
        priority=priority,
        timeout=timeout,
        metadata={
            "created_at": datetime.now(tz=timezone.utc).isoformat(),
            "source": "autobot_orchestrator",
        },
    )


def serialize_agent_request(request: AgentRequest) -> str:
    """Serialize agent request for transmission"""
    return json.dumps(
        {
            "request_id": request.request_id,
            "agent_type": request.agent_type,
            "action": request.action,
            "payload": request.payload,
            "context": request.context,
            "priority": request.priority,
            "timeout": request.timeout,
            "metadata": request.metadata,
        }
    )


def deserialize_agent_request(data: str) -> AgentRequest:
    """Deserialize agent request from transmission"""
    parsed = json.loads(data)
    return AgentRequest(**parsed)


def serialize_agent_response(response: AgentResponse) -> str:
    """Serialize agent response for transmission"""
    return json.dumps(response.to_dict())


def deserialize_agent_response(data: str) -> AgentResponse:
    """Deserialize agent response from transmission"""
    parsed = json.loads(data)
    return AgentResponse(**parsed)
