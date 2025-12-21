# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Distributed Agent Management Module

Issue #381: Extracted from agent_orchestrator.py god class refactoring.
Contains distributed agent registration, health monitoring, and lifecycle management.
"""

import asyncio
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional, Tuple

from src.constants.threshold_constants import TimingConstants

from .types import DistributedAgentInfo

if TYPE_CHECKING:
    from src.agents.base_agent import AgentHealth, BaseAgent

logger = logging.getLogger(__name__)


class DistributedAgentManager:
    """Manages distributed agent lifecycle and health monitoring."""

    def __init__(
        self,
        builtin_agents: Dict[str, Callable],
        health_check_interval: float = 30.0,
    ):
        """
        Initialize the distributed agent manager.

        Args:
            builtin_agents: Dict of agent type to agent class/factory
            health_check_interval: Interval for health checks in seconds
        """
        self.distributed_agents: Dict[str, DistributedAgentInfo] = {}
        self.builtin_distributed_agents = builtin_agents
        self.health_check_interval = health_check_interval
        self.health_monitor_task: Optional[asyncio.Task] = None
        self.is_running = False

    async def start(self) -> bool:
        """Start distributed agent management."""
        if self.is_running:
            logger.warning("Distributed mode already running")
            return True

        try:
            self.is_running = True

            # Initialize built-in distributed agents
            await self._initialize_distributed_agents()

            # Start health monitoring
            self.health_monitor_task = asyncio.create_task(self._health_monitor_loop())

            logger.info("Distributed agent mode started successfully")
            return True

        except Exception as e:
            logger.error("Failed to start distributed mode: %s", e)
            self.is_running = False
            return False

    async def stop(self) -> None:
        """Stop distributed agent management."""
        if not self.is_running:
            return

        self.is_running = False

        # Cancel health monitoring
        if self.health_monitor_task:
            self.health_monitor_task.cancel()

        # Shutdown distributed agents
        for agent_id in list(self.distributed_agents.keys()):
            await self.unregister_agent(agent_id)

        logger.info("Distributed agent mode stopped")

    async def _initialize_distributed_agents(self) -> None:
        """Initialize built-in distributed agents."""
        for agent_type, agent_class in self.builtin_distributed_agents.items():
            try:
                agent = agent_class()
                await self.register_agent(agent)
                logger.info("Initialized distributed agent: %s", agent_type)
            except Exception as e:
                logger.error(
                    f"Failed to initialize distributed agent {agent_type}: {e}"
                )

    async def register_agent(self, agent: "BaseAgent") -> bool:
        """Register a distributed agent."""
        try:
            agent_id = agent.agent_id

            # Initialize agent communication
            if not agent.communication_protocol:
                await agent.initialize_communication(agent.get_capabilities())

            # Perform health check
            health = await agent.health_check()

            # Register agent
            self.distributed_agents[agent_id] = DistributedAgentInfo(
                agent=agent,
                health=health,
                last_health_check=datetime.now(),
                active_tasks=set(),
            )

            logger.info("Registered distributed agent: %s", agent_id)
            return True

        except Exception as e:
            logger.error("Failed to register distributed agent: %s", e)
            return False

    async def unregister_agent(self, agent_id: str) -> bool:
        """Unregister a distributed agent."""
        try:
            if agent_id not in self.distributed_agents:
                return False

            agent_info = self.distributed_agents[agent_id]
            await agent_info.agent.shutdown_communication()
            del self.distributed_agents[agent_id]

            logger.info("Unregistered distributed agent: %s", agent_id)
            return True

        except Exception as e:
            logger.error("Failed to unregister distributed agent %s: %s", agent_id, e)
            return False

    async def _check_single_agent_health(
        self, agent_id: str, agent_info: DistributedAgentInfo
    ) -> Tuple[str, Optional["AgentHealth"], Optional[Exception]]:
        """Check health of single agent (Issue #334 - extracted helper)."""
        try:
            health = await agent_info.agent.health_check()
            return (agent_id, health, None)
        except Exception as e:
            return (agent_id, None, e)

    def _process_health_result(
        self,
        agent_id: str,
        health: Optional["AgentHealth"],
        error: Optional[Exception],
    ) -> None:
        """Process a single health check result (Issue #334 - extracted helper)."""
        agent_info = self.distributed_agents.get(agent_id)
        if not agent_info:
            return

        if error:
            logger.error(
                f"Health check failed for distributed agent {agent_id}: {error}"
            )
            return

        if not health:
            return

        agent_info.health = health
        agent_info.last_health_check = datetime.now()

        if health.status.value != "healthy":
            logger.warning(
                f"Distributed agent {agent_id} health issue: {health.status.value}"
            )

    async def _run_health_checks(
        self, agents_snapshot: list
    ) -> None:
        """Run parallel health checks on agents (Issue #334 - extracted helper)."""
        results = await asyncio.gather(
            *[
                self._check_single_agent_health(aid, ainfo)
                for aid, ainfo in agents_snapshot
            ],
            return_exceptions=True,
        )

        for result in results:
            if isinstance(result, Exception):
                logger.error("Health check task failed: %s", result)
                continue
            agent_id, health, error = result
            self._process_health_result(agent_id, health, error)

    async def _health_monitor_loop(self) -> None:
        """Background health monitoring for distributed agents."""
        while self.is_running:
            try:
                agents_snapshot = list(self.distributed_agents.items())
                if agents_snapshot:
                    await self._run_health_checks(agents_snapshot)
                await asyncio.sleep(self.health_check_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in distributed health monitor: %s", e)
                await asyncio.sleep(TimingConstants.ERROR_RECOVERY_DELAY)

    def get_healthy_agents(self) -> list:
        """Get list of healthy distributed agents."""
        return [
            info.agent
            for info in self.distributed_agents.values()
            if info.health.status.value == "healthy"
        ]

    def get_agent_info(self, agent_id: str) -> Optional[DistributedAgentInfo]:
        """Get info for a specific agent."""
        return self.distributed_agents.get(agent_id)

    def add_active_task(self, agent_id: str, task_id: str) -> None:
        """Add an active task to an agent."""
        if agent_id in self.distributed_agents:
            self.distributed_agents[agent_id].active_tasks.add(task_id)

    def remove_active_task(self, agent_id: str, task_id: str) -> None:
        """Remove an active task from an agent."""
        if agent_id in self.distributed_agents:
            self.distributed_agents[agent_id].active_tasks.discard(task_id)

    def get_statistics(self) -> Dict[str, Any]:
        """Get distributed agent statistics."""
        stats = {}
        for agent_id, agent_info in self.distributed_agents.items():
            stats[agent_id] = {
                "agent_type": agent_info.agent.agent_type,
                "health_status": agent_info.health.status.value,
                "last_health_check": agent_info.last_health_check.isoformat(),
                "active_tasks": len(agent_info.active_tasks),
                "active_task_list": list(agent_info.active_tasks),
            }
        return stats
