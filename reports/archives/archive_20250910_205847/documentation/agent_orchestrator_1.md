# Agent Orchestrator

## Overview

The Agent Orchestrator serves as the central hub for routing, coordinating, and managing all agent interactions within AutoBot. It implements intelligent request routing, load balancing, failover handling, and performance monitoring across the entire multi-agent system.

## System Integration & Interactions

### Architecture Position
```
┌─────────────────────────────────────────────────────────────┐
│                 User Interface Layer                        │
│    (REST API, WebSocket, Chat Interface, Frontend)         │
└─────────────────┬───────────────────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────────────────┐
│                Agent Orchestrator                           │
├─────────────────────────────────────────────────────────────┤
│ • Request Analysis & Routing                               │
│ • Agent Selection & Load Balancing                         │
│ • Response Aggregation & Synthesis                         │
│ • Performance Monitoring & Health Checks                   │
│ • Failover & Error Recovery                                │
└─────┬───────┬───────┬───────┬───────┬───────┬───────┬───────┘
      │       │       │       │       │       │       │
      ▼       ▼       ▼       ▼       ▼       ▼       ▼
 ┌────────┐ ┌─────┐ ┌─────┐ ┌──────┐ ┌──────┐ ┌─────┐ ┌─────┐
 │Knowledge│ │Chat │ │ RAG │ │System│ │Research│ │Dev  │ │Util │
 │Agents  │ │Agent│ │Agent│ │Agents│ │Agents │ │Agents│ │Agents│
 └────────┘ └─────┘ └─────┘ └──────┘ └──────┘ └─────┘ └─────┘
```

### Core System Interactions

#### 1. **Request Processing Pipeline**
```python
class AgentOrchestrator:
    async def process_request(self, request: dict) -> dict:
        """
        Main request processing pipeline
        
        Flow:
        1. Request validation and sanitization
        2. Intent analysis and classification
        3. Agent selection and routing
        4. Request execution with monitoring
        5. Response aggregation and formatting
        """
        
        # Step 1: Request validation
        validated_request = await self._validate_request(request)
        
        # Step 2: Intent analysis
        intent = await self._analyze_intent(validated_request)
        
        # Step 3: Agent selection
        selected_agents = await self._select_agents(intent)
        
        # Step 4: Execute with monitoring
        results = await self._execute_request(selected_agents, validated_request)
        
        # Step 5: Aggregate responses
        final_response = await self._aggregate_responses(results, intent)
        
        return final_response
```

**System Interactions:**
- **Security Layer**: Validates requests and checks permissions
- **Intent Classification**: Uses classification agents for request analysis
- **Agent Registry**: Maintains registry of available agents and capabilities
- **Performance Monitor**: Tracks execution times and success rates
- **Error Boundaries**: Provides error recovery and fallback strategies

#### 2. **Agent Registration & Discovery**
```python
class AgentRegistry:
    """Manages agent registration and capability discovery"""
    
    def __init__(self):
        self.agents = {}  # Active agent instances
        self.capabilities = {}  # Agent capability mappings
        self.health_status = {}  # Agent health monitoring
        self.performance_metrics = {}  # Performance tracking
        
    async def register_agent(self, agent_id: str, agent_instance, capabilities: dict):
        """Register an agent with the orchestrator"""
        self.agents[agent_id] = agent_instance
        self.capabilities[agent_id] = capabilities
        self.health_status[agent_id] = "healthy"
        
        # Initialize performance tracking
        self.performance_metrics[agent_id] = {
            "requests_processed": 0,
            "average_response_time": 0.0,
            "success_rate": 1.0,
            "last_health_check": time.time()
        }
```

**System Interactions:**
- **Agent Discovery**: Automatically discovers and registers agents on startup
- **Capability Mapping**: Maps agent capabilities to request types
- **Health Monitoring**: Continuously monitors agent health and availability
- **Load Balancing**: Distributes requests based on agent capacity and performance

#### 3. **LLM Integration for Routing Decisions**
```python
class RouteDecisionEngine:
    """Uses LLM for complex routing decisions"""
    
    def __init__(self):
        # Use 3B model for complex routing decisions
        self.llm_interface = LLMInterface()
        self.routing_model = "llama3.2:3b"
        
    async def analyze_request_routing(self, request: dict) -> dict:
        """Use LLM to determine optimal agent routing"""
        
        routing_prompt = f"""
        Analyze this user request and determine the best agent routing:
        
        Request: {request.get('content', '')}
        Context: {request.get('context', {})}
        
        Available agents and capabilities:
        {self._format_agent_capabilities()}
        
        Provide routing decision with confidence scores.
        """
        
        response = await self.llm_interface.chat_completion([
            {"role": "system", "content": "You are an expert at routing requests to specialized AI agents."},
            {"role": "user", "content": routing_prompt}
        ], model=self.routing_model)
        
        return self._parse_routing_decision(response)
```

**System Interactions:**
- **LLM Interface**: Uses unified LLM interface for routing decisions
- **Model Selection**: Automatically selects appropriate model size for routing complexity
- **Context Analysis**: Analyzes request context for better routing decisions
- **Confidence Scoring**: Provides confidence scores for routing choices

#### 4. **Redis Integration for State Management**
```python
class OrchestrationState:
    """Manages orchestrator state in Redis"""
    
    def __init__(self):
        self.redis_client = get_redis_client()
        self.state_prefix = "autobot:orchestrator:"
        
    async def store_request_state(self, request_id: str, state: dict):
        """Store request processing state"""
        state_key = f"{self.state_prefix}request:{request_id}"
        await self.redis_client.setex(
            state_key, 
            3600,  # 1 hour TTL
            json.dumps(state)
        )
        
    async def get_agent_metrics(self) -> dict:
        """Retrieve agent performance metrics from Redis"""
        metrics_pattern = f"{self.state_prefix}metrics:*"
        metric_keys = await self.redis_client.keys(metrics_pattern)
        
        metrics = {}
        for key in metric_keys:
            agent_id = key.split(":")[-1]
            metric_data = await self.redis_client.get(key)
            metrics[agent_id] = json.loads(metric_data)
            
        return metrics
```

**System Interactions:**
- **State Persistence**: Stores orchestration state in Redis for recovery
- **Metrics Collection**: Aggregates performance metrics across agents
- **Session Management**: Maintains conversation context and agent state
- **Distributed Coordination**: Enables multi-instance orchestrator coordination

## Core Functionality

### 1. **Request Routing Strategies**

#### Simple Rule-Based Routing
```python
def route_by_keywords(self, request: dict) -> List[str]:
    """Route based on keyword matching"""
    content = request.get('content', '').lower()
    
    routing_rules = {
        'kb_librarian': ['search', 'find', 'lookup', 'knowledge', 'what is'],
        'system_commands': ['execute', 'run', 'command', 'shell', 'terminal'],
        'web_research': ['research', 'web', 'internet', 'online', 'browse'],
        'rag_agent': ['analyze', 'summarize', 'synthesize', 'documents'],
        'chat_agent': ['hello', 'hi', 'how are you', 'chat', 'talk']
    }
    
    matched_agents = []
    for agent, keywords in routing_rules.items():
        if any(keyword in content for keyword in keywords):
            matched_agents.append(agent)
            
    return matched_agents or ['chat_agent']  # Default fallback
```

#### LLM-Based Intelligent Routing
```python
async def route_by_llm_analysis(self, request: dict) -> dict:
    """Use LLM for complex routing decisions"""
    
    # Prepare context with agent capabilities
    context = {
        "request": request,
        "available_agents": self._get_agent_capabilities(),
        "conversation_history": request.get("history", []),
        "user_context": request.get("user_context", {})
    }
    
    # Generate routing decision
    routing_response = await self.route_decision_engine.analyze_request_routing(request)
    
    return {
        "primary_agent": routing_response.get("primary_agent"),
        "secondary_agents": routing_response.get("secondary_agents", []),
        "confidence": routing_response.get("confidence", 0.5),
        "reasoning": routing_response.get("reasoning", "")
    }
```

### 2. **Load Balancing & Performance Optimization**

#### Agent Load Balancing
```python
class LoadBalancer:
    """Manages agent load distribution"""
    
    def select_best_agent_instance(self, agent_type: str) -> str:
        """Select the best available instance of an agent type"""
        
        available_instances = self.get_agent_instances(agent_type)
        
        if not available_instances:
            return None
            
        # Score instances based on multiple factors
        scored_instances = []
        for instance_id in available_instances:
            score = self.calculate_instance_score(instance_id)
            scored_instances.append((instance_id, score))
            
        # Select highest scoring instance
        best_instance = max(scored_instances, key=lambda x: x[1])
        return best_instance[0]
        
    def calculate_instance_score(self, instance_id: str) -> float:
        """Calculate instance suitability score"""
        metrics = self.performance_metrics.get(instance_id, {})
        
        # Factors: response time, success rate, current load, health
        response_time_score = 1.0 - min(metrics.get('avg_response_time', 1.0) / 10.0, 1.0)
        success_rate_score = metrics.get('success_rate', 0.5)
        load_score = 1.0 - min(metrics.get('current_requests', 0) / 10.0, 1.0)
        health_score = 1.0 if metrics.get('health_status') == 'healthy' else 0.0
        
        # Weighted average
        total_score = (
            response_time_score * 0.3 +
            success_rate_score * 0.3 +
            load_score * 0.2 +
            health_score * 0.2
        )
        
        return total_score
```

### 3. **Multi-Agent Coordination**

#### Sequential Agent Execution
```python
async def execute_sequential_agents(self, agents: List[str], request: dict) -> dict:
    """Execute agents in sequence, passing results between them"""
    
    current_result = request
    execution_chain = []
    
    for agent_id in agents:
        try:
            agent = self.get_agent_instance(agent_id)
            
            # Execute agent with current context
            agent_result = await agent.process_request(current_result)
            
            # Update context with agent result
            current_result['previous_results'] = current_result.get('previous_results', [])
            current_result['previous_results'].append({
                'agent': agent_id,
                'result': agent_result,
                'timestamp': time.time()
            })
            
            execution_chain.append({
                'agent': agent_id,
                'success': True,
                'result': agent_result
            })
            
        except Exception as e:
            execution_chain.append({
                'agent': agent_id,
                'success': False,
                'error': str(e)
            })
            
            # Handle agent failure
            if self.should_continue_on_failure(agent_id):
                continue
            else:
                break
                
    return {
        'final_result': current_result,
        'execution_chain': execution_chain
    }
```

#### Parallel Agent Execution
```python
async def execute_parallel_agents(self, agents: List[str], request: dict) -> dict:
    """Execute multiple agents in parallel and aggregate results"""
    
    # Create tasks for parallel execution
    tasks = []
    for agent_id in agents:
        agent = self.get_agent_instance(agent_id)
        task = asyncio.create_task(
            self._execute_agent_with_timeout(agent, request, agent_id)
        )
        tasks.append((agent_id, task))
    
    # Wait for all tasks to complete
    results = {}
    for agent_id, task in tasks:
        try:
            result = await task
            results[agent_id] = {
                'success': True,
                'result': result,
                'agent': agent_id
            }
        except Exception as e:
            results[agent_id] = {
                'success': False,
                'error': str(e),
                'agent': agent_id
            }
    
    # Aggregate successful results
    successful_results = [r for r in results.values() if r['success']]
    failed_agents = [r['agent'] for r in results.values() if not r['success']]
    
    return {
        'aggregated_result': await self._aggregate_parallel_results(successful_results),
        'individual_results': results,
        'failed_agents': failed_agents,
        'success_rate': len(successful_results) / len(results) if results else 0
    }
```

## API Integration

### FastAPI Endpoint Integration
```python
# Main orchestration endpoint
@router.post("/orchestrate")
async def orchestrate_request(request: OrchestrationRequest):
    """Main endpoint for orchestrated agent requests"""
    
    orchestrator = get_agent_orchestrator()
    
    try:
        result = await orchestrator.process_request(request.dict())
        return OrchestrationResponse(
            success=True,
            result=result,
            execution_time=result.get('execution_time'),
            agents_used=result.get('agents_used', [])
        )
    except Exception as e:
        return OrchestrationResponse(
            success=False,
            error=str(e),
            error_type=type(e).__name__
        )

# Agent health monitoring endpoint
@router.get("/agents/health")
async def get_agent_health():
    """Get health status of all registered agents"""
    
    orchestrator = get_agent_orchestrator()
    health_status = await orchestrator.get_all_agent_health()
    
    return {
        "healthy_agents": [a for a, s in health_status.items() if s == "healthy"],
        "unhealthy_agents": [a for a, s in health_status.items() if s != "healthy"],
        "total_agents": len(health_status),
        "system_health": "healthy" if all(s == "healthy" for s in health_status.values()) else "degraded"
    }
```

## Performance Monitoring & Analytics

### Metrics Collection
```python
class OrchestrationMetrics:
    """Collects and analyzes orchestration performance metrics"""
    
    def __init__(self):
        self.metrics_store = {}
        self.redis_client = get_redis_client()
        
    async def record_request_metrics(self, request_id: str, metrics: dict):
        """Record metrics for a processed request"""
        
        metrics_data = {
            'request_id': request_id,
            'timestamp': time.time(),
            'routing_time_ms': metrics.get('routing_time_ms'),
            'execution_time_ms': metrics.get('execution_time_ms'),
            'agents_used': metrics.get('agents_used', []),
            'success': metrics.get('success', True),
            'user_satisfaction': metrics.get('user_satisfaction'),
            'cache_hit_rate': metrics.get('cache_hit_rate')
        }
        
        # Store in Redis for analytics
        metrics_key = f"autobot:orchestrator:metrics:{request_id}"
        await self.redis_client.setex(metrics_key, 86400, json.dumps(metrics_data))
        
        # Update running averages
        await self._update_performance_averages(metrics_data)
```

### Health Monitoring
```python
class HealthMonitor:
    """Monitors system and agent health"""
    
    async def perform_health_checks(self):
        """Perform comprehensive health checks"""
        
        health_report = {
            'timestamp': time.time(),
            'orchestrator_status': 'healthy',
            'agent_health': {},
            'system_resources': await self._check_system_resources(),
            'external_dependencies': await self._check_external_dependencies()
        }
        
        # Check each registered agent
        for agent_id in self.registered_agents:
            try:
                agent_health = await self._check_agent_health(agent_id)
                health_report['agent_health'][agent_id] = agent_health
            except Exception as e:
                health_report['agent_health'][agent_id] = {
                    'status': 'unhealthy',
                    'error': str(e)
                }
        
        # Determine overall system health
        unhealthy_agents = [a for a, h in health_report['agent_health'].items() 
                          if h.get('status') != 'healthy']
        
        if len(unhealthy_agents) > len(self.registered_agents) * 0.5:
            health_report['orchestrator_status'] = 'degraded'
        elif unhealthy_agents:
            health_report['orchestrator_status'] = 'warning'
            
        return health_report
```

## Error Handling & Recovery

### Circuit Breaker Pattern
```python
class CircuitBreaker:
    """Implements circuit breaker pattern for agent calls"""
    
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        
    async def call_agent(self, agent_func, *args, **kwargs):
        """Execute agent call with circuit breaker protection"""
        
        if self.state == "OPEN":
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = "HALF_OPEN"
            else:
                raise CircuitBreakerOpenError("Circuit breaker is OPEN")
        
        try:
            result = await agent_func(*args, **kwargs)
            
            # Success - reset failure count
            if self.state == "HALF_OPEN":
                self.state = "CLOSED"
                self.failure_count = 0
                
            return result
            
        except Exception as e:
            self.failure_count += 1
            self.last_failure_time = time.time()
            
            if self.failure_count >= self.failure_threshold:
                self.state = "OPEN"
                
            raise
```

## Configuration

### Orchestrator Settings
```yaml
# config/orchestrator.yaml
orchestrator:
  routing_strategy: "hybrid"  # "simple", "llm", "hybrid"
  max_concurrent_requests: 100
  request_timeout: 300  # seconds
  health_check_interval: 30  # seconds
  
  load_balancing:
    enabled: true
    algorithm: "weighted_round_robin"  # "round_robin", "least_connections", "weighted"
    
  circuit_breaker:
    enabled: true
    failure_threshold: 5
    recovery_timeout: 60
    
  metrics:
    collection_enabled: true
    retention_days: 7
    detailed_logging: false
```

---

*The Agent Orchestrator demonstrates sophisticated system integration, providing centralized coordination while maintaining flexibility and performance across AutoBot's multi-agent architecture.*