# AutoBot Agents Documentation

## Overview

AutoBot includes a comprehensive suite of intelligent agents that provide specialized assistance for various tasks. These agents work autonomously and collaboratively to enhance user productivity and system functionality.

## Agent Categories

### 🔍 Librarian Agents
Intelligent information management and research assistants.

- **[Librarian Agents Guide](librarian-agents-guide.md)** - Complete guide to all librarian functionality
  - KB Librarian Agent - Local knowledge base search and summarization
  - Containerized Librarian Assistant - Web research with quality assessment
  - Enhanced KB Librarian - Advanced knowledge management features
  - System Knowledge Manager - System-wide knowledge operations

### 🛠️ Helper Agents  
Specialized assistants for various productivity and system tasks.

- **[Helper Agents Guide](helper-agents-guide.md)** - Complete guide to helper agent functionality
  - Web Research Assistant - Multi-source web research and aggregation
  - Advanced Web Research Agent - Complex research with validation
  - Interactive Terminal Agent - Command-line assistance and automation
  - System Command Agent - Safe system command execution

## Quick Reference

### Librarian Agent API Endpoints
```bash
# KB Librarian
GET    /api/kb-librarian/status
POST   /api/kb-librarian/query
PUT    /api/kb-librarian/configure

# Knowledge Base Operations
GET    /api/knowledge_base/stats
POST   /api/knowledge_base/sync
GET    /api/knowledge_base/sync-status
```

### Common Usage Patterns

#### Knowledge Base Search
```python
from src.agents import get_kb_librarian

librarian = get_kb_librarian()
results = await librarian.process_query("How to install dependencies?")
```

#### Web Research
```python
from src.agents import get_containerized_librarian_assistant

assistant = get_containerized_librarian_assistant()
research = await assistant.research_query("Python async best practices 2025")
```

#### System Operations
```python
from src.agents.interactive_terminal_agent import InteractiveTerminalAgent

terminal = InteractiveTerminalAgent()
status = await terminal.get_system_status()
```

## Agent Integration Flow

```
User Query
    ↓
Chat System
    ↓
Agent Router ──→ KB Librarian (searches local docs first)
    ↓                    ↓
    ↓               Found Results? ──→ Yes ──→ Summarize & Respond
    ↓                    ↓
    ↓                   No
    ↓                    ↓
Web Research ──→ Containerized Librarian (web search)
Assistant                ↓
    ↓               Quality Content? ──→ Yes ──→ Store in KB
    ↓                    ↓
    ↓                   No
    ↓                    ↓
Helper Agents ──→ System/Terminal Agents (if system query)
    ↓
Final Response (with sources & attribution)
```

## Configuration

### Global Agent Settings
```yaml
# config/config.yaml
agents:
  enabled: true
  max_concurrent: 5
  timeout_seconds: 30
  logging:
    level: INFO
    performance_metrics: true

# KB Librarian
kb_librarian:
  enabled: true
  similarity_threshold: 0.7
  max_results: 5
  auto_summarize: true

# Web Research
librarian_assistant:
  enabled: true
  playwright_service_url: "http://localhost:3000"
  max_search_results: 5
  quality_threshold: 0.7
```

## Monitoring and Health

### Agent Status Dashboard
```bash
# Check all agent status
curl "http://localhost:8001/api/system/health" | jq '.agents'

# KB Librarian specific status
curl "http://localhost:8001/api/kb-librarian/status"

# Knowledge base sync status
curl "http://localhost:8001/api/knowledge_base/sync-status"
```

### Performance Metrics
- Query response times
- Success/failure rates
- Knowledge base hit rates
- Web research quality scores
- System resource usage

## Troubleshooting

### Common Issues

**KB Librarian returns no results:**
```bash
# Sync knowledge base
python scripts/sync_kb_docs.py

# Check KB status
curl "http://localhost:8001/api/knowledge_base/stats"
```

**Web research fails:**
```bash
# Check Playwright service
docker ps | grep playwright

# Test connectivity
curl "http://localhost:3000/health"
```

**Agent timeouts:**
```bash
# Check system resources
curl "http://localhost:8001/api/system/health" | jq '.system'

# Review agent logs
tail -f logs/agents.log
```

## Development Guide

### Adding New Agents

1. **Create Agent Class**:
```python
# src/agents/my_custom_agent.py
class MyCustomAgent:
    def __init__(self):
        self.config = config
        self.enabled = self.config.get_nested("my_agent.enabled", True)
    
    async def process(self, query: str) -> Dict[str, Any]:
        # Agent implementation
        pass
```

2. **Register Agent**:
```python
# src/agents/__init__.py
from .my_custom_agent import MyCustomAgent

__all__ = [..., "MyCustomAgent"]
```

3. **Add Configuration**:
```yaml
# config/config.yaml
my_agent:
  enabled: true
  custom_setting: "value"
```

4. **Create Tests**:
```python
# tests/agents/test_my_agent.py
import pytest
from src.agents.my_custom_agent import MyCustomAgent

@pytest.mark.asyncio
async def test_my_agent():
    agent = MyCustomAgent()
    result = await agent.process("test query")
    assert result["status"] == "success"
```

### Best Practices

1. **Agent Design**:
   - Single responsibility principle
   - Async/await for all I/O operations
   - Comprehensive error handling
   - Configurable behavior

2. **Integration**:
   - Use existing interfaces (KnowledgeBase, LLMInterface)
   - Follow naming conventions
   - Provide clear API documentation

3. **Testing**:
   - Unit tests for core functionality
   - Integration tests with other agents
   - End-to-end tests via API

## Security Considerations

### Agent Security Model
- Input validation and sanitization
- Output filtering and verification
- Rate limiting and resource management
- Audit logging for all operations

### Web Research Security
- Domain allowlisting/blocklisting
- Content sanitization
- SSL/TLS verification
- User agent rotation

### System Agent Security
- Command whitelisting
- Permission validation
- Sandboxed execution
- Comprehensive audit trails

## Future Roadmap

### Planned Enhancements
- **Multi-modal Agents**: Support for image, video, and audio processing
- **Collaborative Agents**: Multi-agent coordination and task distribution
- **Learning Agents**: Agents that improve through user feedback
- **Custom Agent Builder**: UI for creating custom agents

### Integration Targets
- **External APIs**: Integration with specialized knowledge APIs
- **Enterprise Systems**: Connection to corporate knowledge bases
- **Cloud Services**: Scalable cloud-based agent execution
- **Mobile Support**: Mobile-optimized agent interactions

---

## Getting Started

1. **Enable Agents**: Ensure agents are enabled in your configuration
2. **Populate KB**: Run `python scripts/sync_kb_docs.py` to populate knowledge base
3. **Test Functionality**: Try queries through the chat interface or API
4. **Monitor Performance**: Check agent status and performance metrics

For detailed information about specific agents, see the individual guide files:
- [Librarian Agents Guide](librarian-agents-guide.md)
- [Helper Agents Guide](helper-agents-guide.md)