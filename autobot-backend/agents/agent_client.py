# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Agent Client for Hybrid Local/Remote Deployment
Routes requests to local agents or remote containers based on configuration
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import aiohttp
from utils.service_registry import get_service_url

from autobot_shared.http_client import get_http_client

from .base_agent import (
    AgentHealth,
    AgentRequest,
    AgentResponse,
    AgentStatus,
    BaseAgent,
    DeploymentMode,
    create_agent_request,
    deserialize_agent_response,
    serialize_agent_request,
)

logger = logging.getLogger(__name__)


class AgentClientConfig:
    """Configuration for agent deployment modes"""

    def __init__(self, config_dict: Optional[Dict[str, Any]] = None):
        """Initialize agent client config with deployment settings."""
        self.config = config_dict or {}
        self.default_mode = DeploymentMode.LOCAL
        self.container_base_url = get_service_url("ai-stack")
        self.request_timeout = 30.0
        self.retry_attempts = 3
        self.health_check_interval = 60.0

        # Load from config if provided
        if config_dict:
            self.default_mode = DeploymentMode(config_dict.get("default_mode", "local"))
            self.container_base_url = config_dict.get(
                "container_base_url", self.container_base_url
            )
            self.request_timeout = config_dict.get(
                "request_timeout", self.request_timeout
            )
            self.retry_attempts = config_dict.get("retry_attempts", self.retry_attempts)
            self.health_check_interval = config_dict.get(
                "health_check_interval", self.health_check_interval
            )

    def get_agent_config(self, agent_type: str) -> Dict[str, Any]:
        """Get configuration for specific agent type"""
        return self.config.get("agents", {}).get(
            agent_type,
            {
                "mode": self.default_mode.value,
                "container_url": f"{self.container_base_url}/{agent_type}",
                "replicas": 1,
                "enabled": True,
            },
        )


class AgentRegistry:
    """Registry for tracking available agents and their health"""

    def __init__(self):
        """Initialize registry with empty agent and health tracking dicts."""
        self.agents: Dict[str, BaseAgent] = {}
        self.agent_health: Dict[str, AgentHealth] = {}
        self.last_health_check: Dict[str, datetime] = {}

    def register_agent(self, agent_type: str, agent: BaseAgent):
        """Register an agent in the registry"""
        self.agents[agent_type] = agent
        logger.info(
            f"Registered {agent_type} agent in {agent.deployment_mode.value} mode"
        )

    def unregister_agent(self, agent_type: str):
        """Remove agent from registry"""
        if agent_type in self.agents:
            del self.agents[agent_type]
            if agent_type in self.agent_health:
                del self.agent_health[agent_type]
            if agent_type in self.last_health_check:
                del self.last_health_check[agent_type]
            logger.info("Unregistered %s agent", agent_type)

    def get_agent(self, agent_type: str) -> Optional[BaseAgent]:
        """Get agent by type"""
        return self.agents.get(agent_type)

    def list_agents(self) -> List[str]:
        """List all registered agent types"""
        return list(self.agents.keys())

    def get_healthy_agents(self) -> List[str]:
        """Get list of healthy agent types"""
        healthy = []
        for agent_type, health in self.agent_health.items():
            if health.status in (AgentStatus.HEALTHY, AgentStatus.DEGRADED):
                healthy.append(agent_type)
        return healthy

    async def update_agent_health(self, agent_type: str, force: bool = False):
        """Update health information for an agent"""
        agent = self.agents.get(agent_type)
        if not agent:
            return

        last_check = self.last_health_check.get(agent_type, datetime.min)
        if not force and datetime.now() - last_check < timedelta(minutes=1):
            return  # Skip if checked recently

        try:
            health = await agent.health_check()
            self.agent_health[agent_type] = health
            self.last_health_check[agent_type] = datetime.now()
        except Exception as e:
            logger.error("Health check failed for %s: %s", agent_type, e)


class ContainerAgentProxy(BaseAgent):
    """Proxy for agents running in containers"""

    def __init__(self, agent_type: str, container_url: str):
        """Initialize container proxy with agent type and endpoint URL."""
        super().__init__(agent_type, DeploymentMode.CONTAINER)
        self.container_url = container_url.rstrip("/")
        self._http_client = get_http_client()  # Use singleton HTTP client

    async def process_request(self, request: AgentRequest) -> AgentResponse:
        """Send request to containerized agent via HTTP"""
        try:
            request_data = serialize_agent_request(request)

            async with await self._http_client.post(
                f"{self.container_url}/process",
                data=request_data,
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=request.timeout),
            ) as response:
                if response.status == 200:
                    response_data = await response.text()
                    return deserialize_agent_response(response_data)
                else:
                    error_text = await response.text()
                    return AgentResponse(
                        request_id=request.request_id,
                        agent_type=self.agent_type,
                        status="error",
                        result=None,
                        error=f"HTTP {response.status}: {error_text}",
                    )

        except asyncio.TimeoutError:
            return AgentResponse(
                request_id=request.request_id,
                agent_type=self.agent_type,
                status="error",
                result=None,
                error=f"Request timeout after {request.timeout}s",
            )
        except Exception as e:
            return AgentResponse(
                request_id=request.request_id,
                agent_type=self.agent_type,
                status="error",
                result=None,
                error=f"Container communication error: {str(e)}",
            )

    def get_capabilities(self) -> List[str]:
        """Get capabilities from container (cached or queried)"""
        # This would typically be cached from container registration
        return ["container_agent"]

    async def _ping(self) -> bool:
        """Ping the container agent"""
        try:
            async with await self._http_client.get(
                f"{self.container_url}/health", timeout=aiohttp.ClientTimeout(total=5.0)
            ) as response:
                return response.status == 200
        except Exception:
            return False


class AgentClient:
    """
    Unified client for calling agents in hybrid deployment mode.
    Routes requests to local agents or remote containers.
    """

    def __init__(self, config: Optional[AgentClientConfig] = None):
        """Initialize unified agent client with registry and stats tracking."""
        self.config = config or AgentClientConfig()
        self.registry = AgentRegistry()
        self.container_agents: Dict[str, ContainerAgentProxy] = {}

        # Performance tracking
        self.request_stats: Dict[str, Dict[str, Any]] = {}

    async def initialize(self):
        """Initialize the agent client"""
        # HTTP session handled by singleton HTTPClientManager
        logger.info("Agent client initialized")

    async def cleanup(self):
        """Cleanup resources - HTTP session managed by singleton HTTPClientManager"""

    async def register_local_agent(self, agent: BaseAgent):
        """Register a local agent"""
        self.registry.register_agent(agent.agent_type, agent)
        await self.registry.update_agent_health(agent.agent_type, force=True)

    async def register_container_agent(self, agent_type: str, container_url: str):
        """Register a container agent"""
        proxy = ContainerAgentProxy(agent_type, container_url)
        self.registry.register_agent(agent_type, proxy)
        self.container_agents[agent_type] = proxy

        # Check if container is available
        await self.registry.update_agent_health(agent_type, force=True)

    async def call_agent(
        self,
        agent_type: str,
        action: str,
        payload: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
        priority: str = "normal",
        timeout: Optional[float] = None,
    ) -> AgentResponse:
        """
        Call an agent with automatic local/remote routing.
        """
        # Create standardized request
        request = create_agent_request(
            agent_type=agent_type,
            action=action,
            payload=payload,
            context=context,
            priority=priority,
            timeout=timeout or self.config.request_timeout,
        )

        return await self.process_request(request)

    async def process_request(self, request: AgentRequest) -> AgentResponse:
        """Process an agent request with routing and fallback logic"""
        start_time = time.time()

        try:
            # Get agent from registry
            agent = self.registry.get_agent(request.agent_type)
            if not agent:
                return AgentResponse(
                    request_id=request.request_id,
                    agent_type=request.agent_type,
                    status="error",
                    result=None,
                    error=f"Agent type '{request.agent_type}' not registered",
                )

            # Check agent health
            await self.registry.update_agent_health(request.agent_type)
            health = self.registry.agent_health.get(request.agent_type)

            if health and health.status == AgentStatus.UNHEALTHY:
                return AgentResponse(
                    request_id=request.request_id,
                    agent_type=request.agent_type,
                    status="error",
                    result=None,
                    error=f"Agent '{request.agent_type}' is unhealthy",
                )

            # Execute request with retries
            response = await self._execute_with_retries(agent, request)

            # Track statistics
            execution_time = time.time() - start_time
            self._update_stats(request.agent_type, response.status, execution_time)

            return response

        except Exception as e:
            logger.error("Error processing request for %s: %s", request.agent_type, e)
            execution_time = time.time() - start_time
            self._update_stats(request.agent_type, "error", execution_time)

            return AgentResponse(
                request_id=request.request_id,
                agent_type=request.agent_type,
                status="error",
                result=None,
                error=f"Client error: {str(e)}",
                execution_time=execution_time,
            )

    async def _execute_with_retries(
        self, agent: BaseAgent, request: AgentRequest
    ) -> AgentResponse:
        """Execute request with retry logic"""
        last_error = None

        for attempt in range(self.config.retry_attempts):
            try:
                response = await agent.execute_with_tracking(request)

                # Return immediately on success or non-retryable errors
                if (
                    response.status == "success"
                    or attempt == self.config.retry_attempts - 1
                ):
                    return response

                # Wait before retry
                if attempt < self.config.retry_attempts - 1:
                    await asyncio.sleep(2**attempt)  # Exponential backoff

                last_error = response.error

            except Exception as e:
                last_error = str(e)
                if attempt < self.config.retry_attempts - 1:
                    await asyncio.sleep(2**attempt)

        # All retries failed
        return AgentResponse(
            request_id=request.request_id,
            agent_type=request.agent_type,
            status="error",
            result=None,
            error=f"All retry attempts failed. Last error: {last_error}",
        )

    def _update_stats(self, agent_type: str, status: str, execution_time: float):
        """Update performance statistics"""
        if agent_type not in self.request_stats:
            self.request_stats[agent_type] = {
                "total_requests": 0,
                "successful_requests": 0,
                "failed_requests": 0,
                "total_time": 0.0,
                "avg_time": 0.0,
            }

        stats = self.request_stats[agent_type]
        stats["total_requests"] += 1
        stats["total_time"] += execution_time
        stats["avg_time"] = stats["total_time"] / stats["total_requests"]

        if status == "success":
            stats["successful_requests"] += 1
        else:
            stats["failed_requests"] += 1

    async def get_agent_health_status(
        self, agent_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get health status for all agents or specific agent"""
        if agent_type:
            await self.registry.update_agent_health(agent_type, force=True)
            health = self.registry.agent_health.get(agent_type)
            return (
                health.to_dict()
                if health
                else {"error": f"Agent {agent_type} not found"}
            )

        # Get all agent health
        health_status = {}
        for atype in self.registry.list_agents():
            await self.registry.update_agent_health(atype, force=True)
            health = self.registry.agent_health.get(atype)
            if health:
                health_status[atype] = health.to_dict()

        return health_status

    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics for all agents"""
        return {
            "client_stats": self.request_stats.copy(),
            "agent_stats": {
                agent_type: agent.get_statistics()
                for agent_type, agent in self.registry.agents.items()
            },
        }

    async def discover_container_agents(
        self, base_url: Optional[str] = None
    ) -> List[str]:
        """Discover available container agents"""
        url = base_url or self.config.container_base_url
        discovered = []

        try:
            if not self.http_session:
                await self.initialize()

            async with self.http_session.get(f"{url}/agents") as response:
                if response.status == 200:
                    agents_data = await response.json()
                    for agent_info in agents_data.get("agents", []):
                        agent_type = agent_info["type"]
                        agent_url = agent_info["url"]
                        await self.register_container_agent(agent_type, agent_url)
                        discovered.append(agent_type)

        except Exception as e:
            logger.warning("Could not discover container agents: %s", e)

        return discovered


# Singleton instance for global access (thread-safe)
_agent_client_instance: Optional[AgentClient] = None
_agent_client_lock = asyncio.Lock()


async def get_agent_client(config: Optional[AgentClientConfig] = None) -> AgentClient:
    """Get or create the global agent client instance (thread-safe)"""
    global _agent_client_instance

    if _agent_client_instance is None:
        async with _agent_client_lock:
            # Double-check after acquiring lock
            if _agent_client_instance is None:
                _agent_client_instance = AgentClient(config)
                await _agent_client_instance.initialize()

    return _agent_client_instance


async def cleanup_agent_client():
    """Cleanup the global agent client (thread-safe)"""
    global _agent_client_instance

    async with _agent_client_lock:
        if _agent_client_instance:
            await _agent_client_instance.cleanup()
            _agent_client_instance = None
