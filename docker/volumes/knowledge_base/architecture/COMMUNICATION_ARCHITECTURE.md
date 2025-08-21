# AutoBot Communication Architecture

## Overview

AutoBot uses a **hybrid communication architecture** that combines API-based communication for cross-boundary interactions with direct function calls for internal operations. This document explains when and why each pattern is used.

## Architecture Diagram

```
┌─────────────────┐         ┌─────────────────────────────────────────┐
│                 │         │            Backend (FastAPI)             │
│   Frontend      │  REST   │                                         │
│   (Vue.js)      │◄──────►│  ┌─────────────┐    ┌───────────────┐  │
│                 │  WS     │  │   API       │    │  Internal     │  │
│                 │◄──────►│  │  Routers    │───►│  Components   │  │
└─────────────────┘         │  └─────────────┘    └───────────────┘  │
                            │         │                    ▲          │
                            │         │                    │          │
                            │         ▼                    │          │
                            │  ┌─────────────┐    Direct   │          │
                            │  │   Agents    │◄────────────┘          │
                            │  │             │                        │
                            │  └─────────────┘                        │
                            └─────────────────────────────────────────┘
                                      │ HTTP/WS
                                      ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Ollama LLM     │    │  Redis Stack    │    │  NPU Worker     │
│  :11434         │    │  :6379          │    │  :8081          │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## Communication Patterns

### 1. API-Based Communication

#### When to Use APIs
- **Cross-boundary communication**: Frontend ↔ Backend
- **Inter-container communication**: Backend ↔ Docker services
- **External service integration**: Third-party APIs
- **Scalable operations**: Operations that may be distributed

#### API Endpoints

| Category | Endpoint Pattern | Protocol | Purpose |
|----------|-----------------|----------|---------|
| Chat | `/api/chat/*` | REST | Chat operations, history, sessions |
| System | `/api/system/*` | REST | Health, status, diagnostics |
| Terminal | `/api/terminal/*` | REST/WS | Command execution, shell sessions |
| Workflow | `/api/workflow/*` | REST | Workflow automation |
| Knowledge | `/api/knowledge_base/*` | REST | KB queries, document management |
| Settings | `/api/settings/*` | REST | Configuration management |
| WebSocket | `/ws` | WebSocket | Real-time events, streaming |

#### External Service APIs

| Service | Endpoint | Protocol | Purpose |
|---------|----------|----------|---------|
| Ollama | `http://localhost:11434/api/*` | HTTP/REST | LLM inference |
| Redis | `localhost:6379` | Redis Protocol | Caching, pub/sub |
| NPU Worker | `http://localhost:8081/*` | HTTP/REST | Accelerated inference |
| Playwright | `http://localhost:3000/*` | HTTP/REST | Browser automation |

### 2. Direct Function Calls

#### When to Use Direct Calls
- **Internal backend operations**: Same-process communication
- **Performance-critical paths**: Low-latency requirements
- **Tightly coupled components**: Components that always run together
- **Utility functions**: Shared helper functions

#### Direct Call Examples

```python
# Component instantiation in app_factory.py
app.state.orchestrator = Orchestrator()
app.state.knowledge_base = KnowledgeBase()
app.state.security_layer = SecurityLayer()

# Agent communication
from src.agents.chat_agent import ChatAgent
agent = ChatAgent()
response = await agent.process(message)

# Utility usage
from src.utils.redis_client import get_redis_client
redis = get_redis_client()
```

## Component Communication Matrix

| From | To | Method | Example |
|------|----|--------|---------|
| Frontend | Backend | REST API | `POST /api/chat/send` |
| Frontend | Backend | WebSocket | `ws://localhost:8001/ws` |
| Backend | Ollama | HTTP API | `POST http://localhost:11434/api/chat` |
| Backend | Redis | TCP/Redis Protocol | `redis.get('key')` |
| Backend | NPU Worker | HTTP API | `POST http://localhost:8081/inference` |
| Backend API | Orchestrator | Direct Call | `app.state.orchestrator.process()` |
| Orchestrator | Agents | Direct Call | `agent.execute()` |
| Agents | LLM Interface | Direct Call | `llm.generate()` |
| LLM Interface | Ollama | HTTP API | `aiohttp.post()` |

## Design Principles

### 1. Separation of Concerns
- Frontend knows nothing about backend implementation
- API contracts define boundaries
- Internal refactoring doesn't affect external interfaces

### 2. Performance Optimization
- Direct calls for frequent, internal operations
- API calls only when crossing boundaries
- Caching at API boundaries to reduce overhead

### 3. Scalability
- API-based design allows horizontal scaling
- Containers can be replicated independently
- Load balancing possible at API layer

### 4. Security
- API layer provides authentication/authorization checkpoint
- Input validation at API boundaries
- Internal components trust each other (direct calls)

## Implementation Guidelines

### Creating New API Endpoints

```python
# backend/api/new_feature.py
from fastapi import APIRouter, Depends
from backend.dependencies import get_current_user

router = APIRouter()

@router.post("/action")
async def perform_action(
    request: ActionRequest,
    user = Depends(get_current_user)
):
    # API layer: validation, auth, rate limiting

    # Direct call to internal component
    result = await app.state.component.process(request)

    return {"status": "success", "data": result}
```

### Creating New Internal Components

```python
# src/components/new_component.py
class NewComponent:
    def __init__(self):
        # Direct dependencies injection
        self.llm = LLMInterface()
        self.redis = get_redis_client()

    async def process(self, data):
        # Direct internal calls
        enhanced = await self.llm.enhance(data)
        await self.redis.set(f"cache:{data.id}", enhanced)
        return enhanced
```

### Frontend API Integration

```javascript
// autobot-vue/src/services/api.js
export const newFeatureAPI = {
  async performAction(data) {
    const response = await apiClient.post('/api/new_feature/action', data);
    return response.data;
  }
};
```

## Best Practices

### DO:
- ✅ Use APIs for all frontend-backend communication
- ✅ Use APIs for container-to-container communication
- ✅ Use direct calls within the same Python process
- ✅ Document API contracts in OpenAPI/Swagger
- ✅ Version APIs for backward compatibility
- ✅ Add proper error handling at API boundaries

### DON'T:
- ❌ Expose internal Python objects directly to frontend
- ❌ Make synchronous API calls from async code
- ❌ Skip API validation for "trusted" clients
- ❌ Create circular dependencies between components
- ❌ Use APIs for same-process communication (performance waste)

## Monitoring and Debugging

### API Monitoring
- All API calls are logged with timing information
- Failed API calls trigger error monitoring
- Rate limiting applied at API layer
- Metrics exported for external monitoring

### Direct Call Debugging
- Python profiler can trace direct calls
- Logging at component boundaries
- Stack traces include full call chain
- Unit tests can mock dependencies

## Future Considerations

### Potential API Additions
- GraphQL endpoint for flexible queries
- gRPC for high-performance inter-service communication
- Message queue integration for async operations

### Potential Direct Call Optimizations
- Connection pooling for database access
- Lazy loading of heavy components
- Caching of frequently called functions
- Parallel execution of independent operations

## Conclusion

The hybrid architecture balances the benefits of API-based design (modularity, scalability, security) with the performance advantages of direct function calls. This approach allows AutoBot to maintain clean boundaries while delivering optimal performance for end users.
