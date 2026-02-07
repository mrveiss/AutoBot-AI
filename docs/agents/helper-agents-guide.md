# AutoBot Helper Agents Guide

## Overview

AutoBot includes various helper agents that provide specialized assistance for different tasks. These agents work behind the scenes to enhance user productivity and system functionality.

## Available Helper Agents

### 1. Web Research Assistant (`WebResearchAssistant`)

**Location**: `autobot-user-backend/agents/web_research_assistant.py`

A specialized agent for conducting web research, gathering information from online sources, and presenting structured results.

#### Features:
- **Multi-source Research**: Searches across multiple web sources
- **Content Aggregation**: Combines information from different sources
- **Result Ranking**: Prioritizes most relevant and credible sources
- **Structured Output**: Presents findings in organized, readable format

#### Key Capabilities:
- Search query optimization
- Source credibility assessment  
- Content deduplication
- Result summarization
- Reference tracking

### 2. Advanced Web Research Agent (`advanced_web_research.py`)

**Location**: `autobot-user-backend/agents/advanced_web_research.py`

An enhanced version of the web research assistant with advanced capabilities for complex research tasks.

#### Advanced Features:
- **Multi-step Research**: Breaks complex queries into research steps
- **Cross-reference Validation**: Verifies information across sources
- **Domain-specific Search**: Specialized search for technical domains
- **Temporal Analysis**: Considers information freshness and relevance

### 3. Interactive Terminal Agent (`InteractiveTerminalAgent`)

**Location**: `autobot-user-backend/agents/interactive_terminal_agent.py`

Provides intelligent command-line assistance and system interaction capabilities.

#### Features:
- **Command Suggestions**: Intelligent command completion and suggestions
- **Error Diagnosis**: Analyzes command errors and suggests fixes
- **System Monitoring**: Tracks system status and resource usage
- **Automation Scripts**: Generates and executes automation scripts

#### Use Cases:
- System administration tasks
- DevOps automation
- Troubleshooting assistance
- Performance monitoring

### 4. System Command Agent (`system_command_agent.py`)

**Location**: `autobot-user-backend/agents/system_command_agent.py`

Handles system-level commands and operations with safety checks and intelligent execution.

#### Features:
- **Safe Command Execution**: Built-in safety checks for system commands
- **Permission Management**: Handles privilege escalation appropriately
- **Output Processing**: Structured processing of command outputs
- **Error Recovery**: Automatic error handling and recovery suggestions

## Integration with Chat System

Helper agents are integrated into AutoBot's chat system and can be invoked contextually:

```python
# Example integration in chat endpoint
@router.post("/chat")
async def chat_endpoint(request: ChatRequest):
    # Detect if query needs web research
    if requires_web_research(request.message):
        web_assistant = WebResearchAssistant()
        research_results = await web_assistant.research(request.message)

    # Detect if query needs system commands
    elif requires_system_action(request.message):
        system_agent = SystemCommandAgent()
        command_result = await system_agent.execute_safe(request.message)
```

## Configuration

### Web Research Settings
```yaml
web_research:
  enabled: true
  max_sources: 5
  timeout_seconds: 30
  trusted_domains:
    - "github.com"
    - "stackoverflow.com"
    - "docs.python.org"
  blocked_domains:
    - "example-spam.com"
```

### System Agent Settings
```yaml
system_agents:
  terminal:
    enabled: true
    safe_mode: true
    allowed_commands:
      - "ls"
      - "ps"
      - "df"
      - "free"
    blocked_commands:
      - "rm -rf"
      - "dd"
      - "mkfs"
```

## Usage Examples

### Web Research Assistant

```python
from src.agents.web_research_assistant import WebResearchAssistant

agent = WebResearchAssistant()

# Basic research
results = await agent.research("Python asyncio best practices 2025")

# Advanced research with filters
results = await agent.research(
    query="Docker security hardening",
    domains=["docs.docker.com", "security.stackexchange.com"],
    max_results=3,
    recent_only=True
)
```

### Terminal Agent

```python
from src.agents.interactive_terminal_agent import InteractiveTerminalAgent

terminal = InteractiveTerminalAgent()

# Get system status
status = await terminal.get_system_status()

# Analyze disk usage
analysis = await terminal.analyze_disk_usage()

# Suggest optimizations
suggestions = await terminal.suggest_system_optimizations()
```

## Helper Agent Architecture

### Agent Communication
```
User Query → Chat System → Agent Router → Specific Helper Agent → Results
     ↓                                          ↓
Knowledge Base ← Results Storage ← Quality Filter ← Agent Response
```

### Quality Assurance
1. **Input Validation**: All queries are validated before processing
2. **Output Filtering**: Results are filtered for quality and relevance
3. **Source Verification**: Web sources are verified for credibility
4. **Safety Checks**: System commands undergo safety validation

## Monitoring and Logging

### Agent Performance Metrics
```python
# Example metrics tracked
{
    "agent_type": "web_research_assistant",
    "query_count": 156,
    "avg_response_time": 2.3,
    "success_rate": 0.94,
    "sources_found": 1245,
    "quality_score": 0.82
}
```

### Logging Configuration
```yaml
logging:
  agents:
    level: INFO
    file: "logs/agents.log"
    format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    rotation:
      when: "midnight"
      interval: 1
      backup_count: 7
```

## Error Handling

### Common Issues and Solutions

**Web Research Timeouts**:
```python
try:
    results = await web_agent.research(query, timeout=30)
except TimeoutError:
    # Fallback to cached results or reduced scope
    results = await web_agent.research(query, max_sources=2, timeout=15)
```

**System Command Failures**:
```python
try:
    result = await system_agent.execute("complex_command")
except PermissionError:
    # Request elevated permissions or suggest alternative
    alternative = system_agent.suggest_alternative("complex_command")
```

**Network Connectivity Issues**:
```python
if not await web_agent.check_connectivity():
    # Use offline knowledge base instead
    results = await kb_agent.search_local(query)
```

## Security Considerations

### Web Research Security
- **URL Validation**: All URLs are validated before access
- **Content Sanitization**: Web content is sanitized before processing  
- **Rate Limiting**: Built-in rate limiting prevents abuse
- **Domain Filtering**: Malicious domains are blocked

### System Command Security
- **Command Whitelisting**: Only approved commands allowed
- **Permission Checks**: Proper permission validation
- **Input Sanitization**: Command arguments are sanitized
- **Audit Logging**: All system commands are logged

## Performance Optimization

### Caching Strategies
```python
# Web research caching
@lru_cache(maxsize=100)
def cached_web_search(query: str, max_age_hours: int = 24):
    # Cache results for 24 hours
    pass

# System command caching
@lru_cache(maxsize=50)
def cached_system_info():
    # Cache system status for 5 minutes
    pass
```

### Async Operations
- All agents use async/await for non-blocking operations
- Concurrent research across multiple sources
- Background caching and preloading
- Parallel command execution where safe

## Testing Helper Agents

### Unit Tests
```bash
# Test web research agent
pytest tests/agents/test_web_research.py -v

# Test system agents
pytest tests/agents/test_system_agents.py -v

# Test integration
pytest tests/integration/test_agent_integration.py -v
```

### Integration Tests
```bash
# Test full research workflow
pytest tests/e2e/test_research_workflow.py

# Test system command workflow  
pytest tests/e2e/test_system_workflow.py
```

## Future Enhancements

### Planned Features
1. **Machine Learning Integration**: ML-powered query understanding
2. **Multi-modal Support**: Image and video content analysis
3. **Real-time Collaboration**: Multi-agent coordination
4. **Custom Agent Creation**: User-defined helper agents

### API Improvements
1. **GraphQL Support**: More flexible API queries
2. **Webhook Integration**: Event-driven agent activation
3. **Streaming Responses**: Real-time result streaming
4. **Batch Operations**: Multiple queries in single request

## Best Practices

### Agent Development
1. **Single Responsibility**: Each agent should have one clear purpose
2. **Error Resilience**: Implement comprehensive error handling
3. **Resource Management**: Properly manage memory and connections
4. **Documentation**: Document all agent capabilities and limitations

### Usage Guidelines
1. **Query Optimization**: Structure queries for best results
2. **Resource Conservation**: Use caching to reduce external calls
3. **Security First**: Always validate inputs and outputs
4. **Performance Monitoring**: Track agent performance metrics

### Troubleshooting
1. **Check Logs**: Agent logs provide detailed error information
2. **Test Connectivity**: Verify network access for web agents
3. **Validate Permissions**: Ensure proper system permissions
4. **Resource Limits**: Monitor CPU and memory usage

---

**Note**: Helper agents are designed to augment AutoBot's capabilities while maintaining security and performance. They work together to provide comprehensive assistance across various domains, from web research to system administration.
