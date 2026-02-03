# AutoBot Agent Architecture Documentation

This documentation provides comprehensive information about all agents in the AutoBot system, their roles, interactions, and integration patterns.

> **📋 For system status updates and fixes, see:** [`../system-state.md`](../system-state.md)
> **📋 For development guidelines and project setup, see:** [`../../CLAUDE.md`](../../CLAUDE.md)

## 📋 Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Agent Categories](#agent-categories)
3. [System Interactions](#system-interactions)
4. [Integration Patterns](#integration-patterns)
5. [Agent Directory](#agent-directory)

## 🏗️ Architecture Overview

AutoBot uses a multi-agent orchestration system where specialized agents handle different types of tasks. The system follows a hub-and-spoke model with the Agent Orchestrator as the central coordinator.

```
┌─────────────────────────────────────────────────────────────────┐
│                    User Interface Layer                         │
│  (Frontend, API Endpoints, WebSocket, Chat Interface)          │
└─────────────────┬───────────────────────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────────────────────┐
│                 Agent Orchestrator                              │
│  • Request routing and delegation                               │
│  • Load balancing and failover                                  │
│  • Response aggregation                                         │
│  • Performance monitoring                                       │
└─────────────────┬───────────────────────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────────────────────┐
│                Specialized Agent Layer                          │
│  ┌─────────────┬─────────────┬─────────────┬─────────────┐      │
│  │ Knowledge   │ System      │ Research    │ Development │      │
│  │ Management  │ Operations  │ & Web       │ & Code      │      │
│  │ Agents      │ Agents      │ Agents      │ Agents      │      │
│  └─────────────┴─────────────┴─────────────┴─────────────┘      │
└─────────────────┬───────────────────────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────────────────────┐
│                Infrastructure Layer                             │
│  • Knowledge Base (SQLite/Vector DB)                           │
│  • Redis (Caching, Task Queue, Session State)                  │
│  • LLM Interfaces (Ollama, OpenAI, Local Models)              │
│  • NPU Acceleration (OpenVINO)                                 │
│  • Security Layer (RBAC, Audit Logging)                        │
│  • File System (Sandboxed Operations)                          │
└─────────────────────────────────────────────────────────────────┘
```

## 📂 Agent Categories

### 1. **Orchestration & Coordination**
- [Agent Orchestrator](./orchestration/agent_orchestrator.md) - Central routing and coordination
- [Base Agent](./orchestration/base_agent.md) - Abstract base class for all agents

### 2. **Knowledge Management**
- [KB Librarian Agent](./knowledge/kb_librarian_agent.md) - Knowledge base search and retrieval
- [Enhanced KB Librarian](./knowledge/enhanced_kb_librarian.md) - Advanced KB operations
- [Knowledge Retrieval Agent](./knowledge/knowledge_retrieval_agent.md) - Fast fact lookup
- [Knowledge Extraction Agent](./knowledge/knowledge_extraction_agent.md) - Document processing
- [System Knowledge Manager](./knowledge/system_knowledge_manager.md) - System state management

### 3. **Conversational & Chat**
- [Chat Agent](./chat/chat_agent.md) - Lightweight conversational interactions

### 4. **Document Processing & RAG**
- [RAG Agent](./rag/rag_agent.md) - Retrieval-Augmented Generation

### 5. **System Operations**
- [Enhanced System Commands Agent](./system/enhanced_system_commands_agent.md) - Secure command execution
- [System Command Agent](./system/system_command_agent.md) - Basic system commands
- [Interactive Terminal Agent](./system/interactive_terminal_agent.md) - Terminal sessions

### 6. **Research & Web**
- [Web Research Assistant](./research/web_research_assistant.md) - Web research and data gathering
- [Advanced Web Research](./research/advanced_web_research.md) - Advanced scraping with Playwright
- [Research Agent](./research/research_agent.md) - Multi-step research coordination

### 7. **Development & Code Analysis**
- [NPU Code Search Agent](./development/npu_code_search_agent.md) - High-performance code search
- [Development Speedup Agent](./development/development_speedup_agent.md) - Development acceleration

### 8. **Security & Network**
- [Security Scanner Agent](./security/security_scanner_agent.md) - Defensive security scanning
- [Network Discovery Agent](./security/network_discovery_agent.md) - Network topology discovery

### 9. **Utility & Support**
- [JSON Formatter Agent](./utility/json_formatter_agent.md) - JSON processing
- [Classification Agent](./utility/classification_agent.md) - Text/intent classification
- [LLM Failsafe Agent](./utility/llm_failsafe_agent.md) - Fallback responses

## 🔄 System Interactions

### Request Flow
1. **Request Entry**: User requests enter through REST API, WebSocket, or chat interface
2. **Authentication**: Security layer validates permissions and user roles
3. **Orchestration**: Agent Orchestrator analyzes request and selects appropriate agent(s)
4. **Execution**: Selected agent(s) process the request using system resources
5. **Response**: Results are aggregated and returned to the user

### Data Flow
- **Knowledge Base**: Agents read/write structured knowledge, facts, and documents
- **Redis**: Used for caching, session state, task queues, and real-time data
- **File System**: Sandboxed file operations for uploads, processing, and storage
- **External APIs**: Web research, LLM providers, and third-party integrations

### Communication Patterns
- **Synchronous**: Direct function calls for simple operations
- **Asynchronous**: Task queues and callbacks for long-running operations  
- **Event-driven**: WebSocket notifications and real-time updates
- **Batch Processing**: Bulk operations and background tasks

## 🔧 Integration Patterns

### 1. **Agent-to-Agent Communication**
```python
# Agents can call other agents through the orchestrator
await orchestrator.delegate_to_agent("kb_librarian", query_params)

# Or directly for performance-critical operations
from src.agents.knowledge_retrieval_agent import get_knowledge_retrieval_agent
knowledge_agent = get_knowledge_retrieval_agent()
results = await knowledge_agent.quick_lookup(term)
```

### 2. **System Resource Access**
```python
# Knowledge Base integration
from src.knowledge_base import KnowledgeBase
kb = KnowledgeBase()
chunks = await kb.search_chunks(query)

# Redis integration
from src.utils.redis_client import get_redis_client
redis_client = get_redis_client()
cached_result = redis_client.get(cache_key)

# Security integration
from src.security_layer import SecurityLayer
security = SecurityLayer()
if security.check_permission(user_role, "files.upload", resource):
    # Proceed with operation
```

### 3. **Error Handling Integration**
```python
from src.utils.error_boundaries import error_boundary

@error_boundary(component="agent_name", function="process_request")
async def process_request(self, request):
    # Agent processing logic with automatic error handling
    return response
```

## 📊 Performance Considerations

### Model Selection Strategy
- **1B Models**: Chat, simple classification, basic commands (fast responses)
- **3B Models**: RAG, research, complex routing decisions (better reasoning)
- **NPU Acceleration**: Code search, semantic similarity (hardware optimization)

### Caching Strategy
- **L1 Cache**: In-memory agent state and frequently accessed data
- **L2 Cache**: Redis for session state and cross-request data
- **L3 Cache**: Knowledge base for persistent structured data

### Load Balancing
- Multiple agent instances can run in containers
- Request routing based on agent availability and load
- Failover to backup agents when primary agents are unavailable

## 🚀 Getting Started

1. **Read the Architecture Overview** to understand the system design
2. **Explore Agent Categories** to find agents relevant to your use case
3. **Check Integration Examples** in individual agent documentation
4. **Review Security Considerations** for production deployment

## 🔗 Quick Links

- [Agent Development Guide](./development_guide.md)
- [Security Best Practices](./security_guide.md)
- [Performance Optimization](./performance_guide.md)
- [Troubleshooting Guide](./troubleshooting.md)

---

*Last updated: 2025-08-19*
*For questions or contributions, see the [CONTRIBUTING.md](../../CONTRIBUTING.md) guide.*