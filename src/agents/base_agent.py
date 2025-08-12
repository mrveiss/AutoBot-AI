"""
Base Agent Interface for Hybrid Local/Remote Deployment
Provides unified interface for agents running locally or in containers
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Union
import json
from datetime import datetime

logger = logging.getLogger(__name__)


class DeploymentMode(Enum):
    """Agent deployment modes"""
    LOCAL = "local"
    CONTAINER = "container"
    REMOTE = "remote"


class AgentStatus(Enum):
    """Agent health status"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    OFFLINE = "offline"


@dataclass
class AgentRequest:
    """Standardized agent request format"""
    request_id: str
    agent_type: str
    action: str
    payload: Dict[str, Any]
    context: Optional[Dict[str, Any]] = None
    priority: str = "normal"  # low, normal, high, urgent
    timeout: float = 30.0
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class AgentResponse:
    """Standardized agent response format"""
    request_id: str
    agent_type: str
    status: str  # success, error, partial
    result: Any
    error: Optional[str] = None
    execution_time: float = 0.0
    metadata: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "request_id": self.request_id,
            "agent_type": self.agent_type,
            "status": self.status,
            "result": self.result,
            "error": self.error,
            "execution_time": self.execution_time,
            "metadata": self.metadata or {}
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
            "capabilities": self.capabilities
        }


class BaseAgent(ABC):
    """
    Abstract base class for all AutoBot agents.
    Designed for hybrid local/container deployment.
    """

    def __init__(self, agent_type: str, deployment_mode: DeploymentMode = DeploymentMode.LOCAL):
        self.agent_type = agent_type
        self.deployment_mode = deployment_mode
        self.capabilities: List[str] = []
        self.startup_time = datetime.now()
        
        # Performance tracking
        self.request_count = 0
        self.success_count = 0
        self.error_count = 0
        self.total_execution_time = 0.0
        
        logger.info(f"Initialized {agent_type} agent in {deployment_mode.value} mode")

    @abstractmethod
    async def process_request(self, request: AgentRequest) -> AgentResponse:
        """
        Main request processing method.
        Must be implemented by all agents.
        """
        pass

    @abstractmethod
    def get_capabilities(self) -> List[str]:
        """
        Return list of capabilities this agent supports.
        Used for request routing and service discovery.
        """
        pass

    async def health_check(self) -> AgentHealth:
        """
        Return current health status of the agent.
        Used by container orchestration and load balancers.
        """
        try:
            # Test basic functionality
            test_request = AgentRequest(
                request_id="health_check",
                agent_type=self.agent_type,
                action="ping",
                payload={"test": True}
            )
            
            start_time = datetime.now()
            await self._ping()
            response_time = (datetime.now() - start_time).total_seconds() * 1000
            
            status = AgentStatus.HEALTHY
            if response_time > 5000:  # 5 second threshold
                status = AgentStatus.DEGRADED
                
            success_rate = (
                self.success_count / max(self.request_count, 1)
            ) * 100
            
            return AgentHealth(
                agent_type=self.agent_type,
                status=status,
                deployment_mode=self.deployment_mode,
                last_heartbeat=datetime.now(),
                response_time_ms=response_time,
                success_rate=success_rate,
                error_count=self.error_count,
                resource_usage=await self._get_resource_usage(),
                capabilities=self.get_capabilities()
            )
            
        except Exception as e:
            logger.error(f"Health check failed for {self.agent_type}: {e}")
            return AgentHealth(
                agent_type=self.agent_type,
                status=AgentStatus.UNHEALTHY,
                deployment_mode=self.deployment_mode,
                last_heartbeat=datetime.now(),
                response_time_ms=0.0,
                success_rate=0.0,
                error_count=self.error_count + 1,
                resource_usage={},
                capabilities=[]
            )

    async def _ping(self) -> bool:
        """Basic connectivity test - can be overridden by subclasses"""
        await asyncio.sleep(0.001)  # Simulate minimal processing
        return True

    async def _get_resource_usage(self) -> Dict[str, Any]:
        """Get current resource usage - can be overridden by subclasses"""
        import psutil
        import os
        
        try:
            process = psutil.Process(os.getpid())
            memory_info = process.memory_info()
            
            return {
                "cpu_percent": process.cpu_percent(),
                "memory_rss_mb": memory_info.rss / 1024 / 1024,
                "memory_vms_mb": memory_info.vms / 1024 / 1024,
                "num_threads": process.num_threads(),
                "uptime_seconds": (datetime.now() - self.startup_time).total_seconds()
            }
        except Exception as e:
            logger.warning(f"Could not get resource usage: {e}")
            return {"error": str(e)}

    async def execute_with_tracking(self, request: AgentRequest) -> AgentResponse:
        """
        Wrapper that adds performance tracking to request processing.
        Used by agent clients for monitoring.
        """
        start_time = datetime.now()
        self.request_count += 1
        
        try:
            response = await self.process_request(request)
            
            if response.status == "success":
                self.success_count += 1
            else:
                self.error_count += 1
                
            execution_time = (datetime.now() - start_time).total_seconds()
            self.total_execution_time += execution_time
            response.execution_time = execution_time
            
            return response
            
        except Exception as e:
            self.error_count += 1
            execution_time = (datetime.now() - start_time).total_seconds()
            
            logger.error(f"Agent {self.agent_type} error: {e}")
            return AgentResponse(
                request_id=request.request_id,
                agent_type=self.agent_type,
                status="error",
                result=None,
                error=str(e),
                execution_time=execution_time
            )

    def get_statistics(self) -> Dict[str, Any]:
        """Get performance statistics for this agent"""
        avg_execution_time = (
            self.total_execution_time / max(self.request_count, 1)
        )
        
        return {
            "agent_type": self.agent_type,
            "deployment_mode": self.deployment_mode.value,
            "total_requests": self.request_count,
            "successful_requests": self.success_count,
            "failed_requests": self.error_count,
            "success_rate": (self.success_count / max(self.request_count, 1)) * 100,
            "avg_execution_time_seconds": avg_execution_time,
            "total_execution_time_seconds": self.total_execution_time,
            "uptime_seconds": (datetime.now() - self.startup_time).total_seconds()
        }


class LocalAgent(BaseAgent):
    """
    Base class for agents running locally (same process).
    Provides direct method calls for maximum performance.
    """
    
    def __init__(self, agent_type: str):
        super().__init__(agent_type, DeploymentMode.LOCAL)
        
    def is_available(self) -> bool:
        """Check if agent is available for processing"""
        return True


class ContainerAgent(BaseAgent):
    """
    Base class for agents running in containers.
    Provides HTTP/gRPC communication interface.
    """
    
    def __init__(self, agent_type: str, container_url: str):
        super().__init__(agent_type, DeploymentMode.CONTAINER)
        self.container_url = container_url
        self.session = None  # Will be initialized with aiohttp session
        
    async def is_available(self) -> bool:
        """Check if container agent is available"""
        try:
            health = await self.health_check()
            return health.status in [AgentStatus.HEALTHY, AgentStatus.DEGRADED]
        except Exception:
            return False


# Utility functions for agent management

def create_agent_request(
    agent_type: str,
    action: str,
    payload: Dict[str, Any],
    context: Optional[Dict[str, Any]] = None,
    priority: str = "normal",
    timeout: float = 30.0
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
            "created_at": datetime.now().isoformat(),
            "source": "autobot_orchestrator"
        }
    )


def serialize_agent_request(request: AgentRequest) -> str:
    """Serialize agent request for transmission"""
    return json.dumps({
        "request_id": request.request_id,
        "agent_type": request.agent_type,
        "action": request.action,
        "payload": request.payload,
        "context": request.context,
        "priority": request.priority,
        "timeout": request.timeout,
        "metadata": request.metadata
    })


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