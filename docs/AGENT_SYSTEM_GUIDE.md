# AutoBot Agent System: Complete Guide

## 🚀 Quick Reference

AutoBot features a revolutionary multi-agent system with intelligent orchestration. This guide provides comprehensive information for developers working with the agent architecture.

## 📋 Agent System Overview

### **Architecture Pattern**
```
User Request → Classification Agent → Orchestrator → Multi-Agent Execution → Result Synthesis
```

### **Agent Tiers**
- **Tier 1**: Core agents (always available) - 1B models for speed
- **Tier 2**: Processing agents (on-demand) - 3B models for complexity
- **Tier 3**: Specialized agents (task-specific) - Tool orchestration
- **Tier 4**: Advanced agents (multi-modal) - Cutting-edge AI integration

## 🤖 Agent Development

### **Creating a New Agent**

1. **Extend BaseAgent**:
```python
from src.agents.base_agent import BaseAgent, AgentRequest, AgentResponse

class YourAgent(BaseAgent):
    def __init__(self):
        super().__init__("your_agent", DeploymentMode.LOCAL)
        self.capabilities = ["capability1", "capability2"]

    async def process_request(self, request: AgentRequest) -> AgentResponse:
        # Your implementation here
        pass

    def get_capabilities(self) -> List[str]:
        return self.capabilities
```

2. **Add to Agent Registry**:
```python
# In src/agents/__init__.py
from .your_agent import YourAgent

__all__ = [
    # ... existing agents
    "YourAgent",
]
```

3. **Update Orchestrator**:
```python
# In src/orchestrator.py agent_registry
self.agent_registry = {
    # ... existing agents
    "your_agent": "Description of your agent's capabilities"
}
```

### **Agent Testing**

Create comprehensive tests:
```python
# tests/unit/test_your_agent.py
import pytest
from src.agents.your_agent import YourAgent
from src.agents.base_agent import AgentRequest

@pytest.mark.asyncio
async def test_your_agent_basic_functionality():
    agent = YourAgent()
    request = AgentRequest(
        request_id="test_1",
        agent_type="your_agent",
        action="test_action",
        payload={"test": "data"}
    )

    response = await agent.process_request(request)
    assert response.status == "success"
    assert response.agent_type == "your_agent"
```

## 🔧 Agent Configuration

### **Model Assignment**
```python
# In src/config.py
def get_task_specific_model(self, task_type: str) -> str:
    task_models = {
        "chat": "llama3.2:1b",           # Speed priority
        "orchestrator": "llama3.2:3b",   # Complexity priority
        "rag": "llama3.2:3b",           # Reasoning priority
        "your_agent": "llama3.2:1b",    # Configure as needed
    }
    return task_models.get(task_type, self.default_model)
```

### **Security Classification**
```python
# Agent risk levels for security routing
AGENT_RISK_LEVELS = {
    "chat": "LOW",              # Safe operations
    "kb_librarian": "LOW",      # Read-only access
    "system_commands": "MEDIUM", # Validated operations
    "security_scanner": "HIGH", # Active reconnaissance
    "interactive_terminal": "CRITICAL", # Direct system access
}
```

## 🛡️ Security Guidelines

### **Security Validation**
Always validate inputs and implement security controls:
```python
class SecureAgent(BaseAgent):
    async def process_request(self, request: AgentRequest) -> AgentResponse:
        # Input validation
        if not self._validate_request(request):
            return AgentResponse(
                request_id=request.request_id,
                agent_type=self.agent_type,
                status="error",
                result=None,
                error="Invalid request parameters"
            )

        # Risk assessment
        risk_level = self._assess_risk(request)
        if risk_level == "HIGH" and not request.context.get("approved"):
            return AgentResponse(
                request_id=request.request_id,
                agent_type=self.agent_type,
                status="approval_required",
                result={"approval_reason": "High-risk operation requires approval"}
            )

        # Safe execution
        try:
            result = await self._safe_execute(request)
            return AgentResponse(
                request_id=request.request_id,
                agent_type=self.agent_type,
                status="success",
                result=result
            )
        except Exception as e:
            logger.error(f"Agent execution failed: {e}")
            return AgentResponse(
                request_id=request.request_id,
                agent_type=self.agent_type,
                status="error",
                result=None,
                error=str(e)
            )
```

### **Approval Workflows**
For high-risk operations:
```python
from src.takeover_manager import takeover_manager, TakeoverTrigger

async def execute_high_risk_operation(self, request: AgentRequest):
    # Trigger approval workflow
    approval = await takeover_manager.trigger_takeover(
        TakeoverTrigger.SECURITY_RISK,
        context={
            "operation": request.action,
            "risk_level": "HIGH",
            "agent": self.agent_type
        }
    )

    if approval.approved:
        # Proceed with operation
        return await self._execute_operation(request)
    else:
        return AgentResponse(status="denied", error="Operation denied by user")
```

## 📊 Performance Optimization

### **Resource Management**
```python
class OptimizedAgent(BaseAgent):
    def __init__(self):
        super().__init__("optimized_agent")
        self._resource_pool = None
        self._connection_pool = None

    async def _initialize_resources(self):
        """Lazy resource initialization"""
        if not self._resource_pool:
            self._resource_pool = await create_resource_pool()
        if not self._connection_pool:
            self._connection_pool = await create_connection_pool()

    async def process_request(self, request: AgentRequest) -> AgentResponse:
        await self._initialize_resources()

        # Use pooled resources
        async with self._resource_pool.acquire() as resource:
            result = await self._process_with_resource(resource, request)

        return result
```

### **Caching Strategies**
```python
from functools import lru_cache
import redis

class CachedAgent(BaseAgent):
    def __init__(self):
        super().__init__("cached_agent")
        self.redis_client = redis.Redis(host='localhost', port=6379)

    @lru_cache(maxsize=128)  # Memory cache for frequent calls
    def _get_static_data(self, key: str):
        return expensive_computation(key)

    async def _get_dynamic_data(self, key: str):
        # Redis cache for dynamic data
        cached = self.redis_client.get(f"agent_cache:{key}")
        if cached:
            return json.loads(cached)

        data = await fetch_dynamic_data(key)
        self.redis_client.setex(f"agent_cache:{key}", 300, json.dumps(data))
        return data
```

## 🔄 Agent Communication

### **Inter-Agent Communication**
```python
from src.agents.agent_orchestrator import AgentOrchestrator

class CommunicatingAgent(BaseAgent):
    def __init__(self):
        super().__init__("communicating_agent")
        self.orchestrator = AgentOrchestrator()

    async def process_request(self, request: AgentRequest) -> AgentResponse:
        # Step 1: Get information from research agent
        research_request = AgentRequest(
            request_id=f"{request.request_id}_research",
            agent_type="research",
            action="search_web",
            payload={"query": request.payload.get("topic")}
        )

        research_response = await self.orchestrator.route_request(research_request)

        # Step 2: Synthesize with RAG agent
        rag_request = AgentRequest(
            request_id=f"{request.request_id}_rag",
            agent_type="rag",
            action="synthesize",
            payload={
                "documents": research_response.result,
                "query": request.payload.get("question")
            }
        )

        rag_response = await self.orchestrator.route_request(rag_request)

        # Step 3: Combine results
        combined_result = {
            "research_findings": research_response.result,
            "synthesized_answer": rag_response.result,
            "confidence": min(research_response.metadata.get("confidence", 1.0),
                            rag_response.metadata.get("confidence", 1.0))
        }

        return AgentResponse(
            request_id=request.request_id,
            agent_type=self.agent_type,
            status="success",
            result=combined_result
        )
```

## 🏗️ Deployment Patterns

### **Container-Based Agent**
```python
# For agents requiring isolation
class ContainerizedAgent(BaseAgent):
    def __init__(self):
        super().__init__("containerized_agent", DeploymentMode.CONTAINER)

    async def process_request(self, request: AgentRequest) -> AgentResponse:
        # This agent runs in a separate container
        # Communication happens via HTTP API calls

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"http://agent-container:8080/process",
                json=request.__dict__
            ) as response:
                result = await response.json()
                return AgentResponse(**result)
```

### **NPU-Accelerated Agent**
```python
# For agents using hardware acceleration
class NPUAgent(BaseAgent):
    def __init__(self):
        super().__init__("npu_agent", DeploymentMode.REMOTE)
        self.npu_client = NPUWorkerClient()

    async def process_request(self, request: AgentRequest) -> AgentResponse:
        # Route to NPU worker for hardware-accelerated inference
        npu_response = await self.npu_client.infer(
            model_id="specialized_model",
            input_data=request.payload
        )

        return AgentResponse(
            request_id=request.request_id,
            agent_type=self.agent_type,
            status="success",
            result=npu_response.result,
            execution_time=npu_response.inference_time
        )
```

## 🧪 Testing & Debugging

### **Agent Health Checks**
```python
@pytest.mark.asyncio
async def test_agent_health():
    agent = YourAgent()
    health = await agent.health_check()

    assert health.status == AgentStatus.HEALTHY
    assert health.response_time_ms < 5000  # Less than 5 seconds
    assert health.success_rate > 0.9  # 90% success rate
    assert "your_capability" in health.capabilities
```

### **Integration Testing**
```python
@pytest.mark.asyncio
async def test_agent_integration():
    orchestrator = AgentOrchestrator()

    # Test routing to your agent
    request = AgentRequest(
        request_id="integration_test",
        agent_type="your_agent",
        action="test_action",
        payload={"test_data": "value"}
    )

    response = await orchestrator.route_request(request)
    assert response.status == "success"
    assert response.agent_type == "your_agent"
```

## 📈 Monitoring & Metrics

### **Performance Tracking**
```python
from src.metrics.workflow_metrics import workflow_metrics

class MonitoredAgent(BaseAgent):
    async def process_request(self, request: AgentRequest) -> AgentResponse:
        # Start timing
        start_time = time.time()

        try:
            result = await self._execute_request(request)

            # Record success
            workflow_metrics.record_agent_success(
                self.agent_type,
                execution_time=time.time() - start_time
            )

            return result

        except Exception as e:
            # Record failure
            workflow_metrics.record_agent_failure(
                self.agent_type,
                error_type=type(e).__name__
            )
            raise
```

## 🔮 Advanced Features

### **Self-Improving Agent**
```python
class LearningAgent(BaseAgent):
    def __init__(self):
        super().__init__("learning_agent")
        self.performance_history = []

    async def process_request(self, request: AgentRequest) -> AgentResponse:
        response = await self._execute_request(request)

        # Learn from execution
        self._update_performance_model(request, response)

        return response

    def _update_performance_model(self, request, response):
        """Update internal model based on request/response patterns"""
        performance_data = {
            "request_type": request.action,
            "success": response.status == "success",
            "execution_time": response.execution_time,
            "confidence": response.metadata.get("confidence", 0.5)
        }

        self.performance_history.append(performance_data)

        # Adjust behavior based on patterns
        if len(self.performance_history) > 100:
            self._optimize_behavior()

    def _optimize_behavior(self):
        """Optimize agent behavior based on historical performance"""
        # Implement learning algorithm
        pass
```

## 🚀 Best Practices

1. **Always extend BaseAgent** for standardized interface
2. **Implement comprehensive error handling** with proper logging
3. **Use security validation** for all inputs and operations
4. **Implement health checks** for monitoring and debugging
5. **Cache expensive operations** to improve performance
6. **Use appropriate deployment modes** based on security requirements
7. **Test thoroughly** with unit, integration, and security tests
8. **Document capabilities** clearly for orchestrator routing
9. **Monitor performance** and optimize based on metrics
10. **Follow security classifications** for risk-appropriate handling

## 📚 Additional Resources

- [Base Agent Interface](src/agents/base_agent.py) - Core agent implementation
- [Agent Orchestrator](src/agents/agent_orchestrator.py) - Multi-agent coordination
- [Security Guidelines](docs/security/) - Security best practices
- [Performance Optimization](docs/features/) - Performance tuning guides
- [Testing Framework](tests/) - Comprehensive test examples

This guide provides the foundation for developing, deploying, and maintaining agents within AutoBot's sophisticated multi-agent ecosystem.
