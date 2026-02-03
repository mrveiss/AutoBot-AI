# AutoBot Multi-Agent Architecture

## Overview

AutoBot implements a sophisticated multi-agent architecture that distributes tasks across specialized agents, each optimized for specific types of requests. This approach maximizes efficiency while minimizing resource usage by using appropriately sized models for different complexity levels.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                      Agent Orchestrator                        │
│                   (Llama 3.2 3B Instruct)                     │
│                                                                 │
│  • Request routing and coordination                            │
│  • Multi-agent workflow orchestration                         │
│  • Response synthesis and optimization                        │
└─────────────────┬───────────────────────────────────────────────┘
                  │
         ┌────────┴────────┐
         │   Route Request │
         └────────┬────────┘
                  │
    ┌─────────────┼─────────────┐
    │             │             │
    ▼             ▼             ▼
┌─────────┐  ┌─────────┐  ┌─────────┐
│ Chat    │  │System   │  │   RAG   │
│ Agent   │  │Commands │  │ Agent   │
│ (1B)    │  │Agent(1B)│  │ (3B)    │
└─────────┘  └─────────┘  └─────────┘
    ▼             ▼             ▼
┌─────────┐  ┌─────────┐  ┌─────────┐
│Knowledge│  │Research │  │GUI Ctrl │
│Retrieval│  │ Agent   │  │ Agent   │
│ (1B)    │  │(3B+Web) │  │ (TBD)   │
└─────────┘  └─────────┘  └─────────┘
```

## Agent Specifications

### 1. Agent Orchestrator
- **Model**: Llama 3.2 3B Instruct (Q4_K_M)
- **Role**: Central coordinator and router
- **Responsibilities**:
  - Analyze incoming requests
  - Route to appropriate specialized agents
  - Coordinate multi-agent workflows
  - Synthesize responses from multiple agents
  - Handle complex multi-step reasoning

**File**: `src/agents/agent_orchestrator.py`

### 2. Chat Agent
- **Model**: Llama 3.2 1B Instruct (Q4_K_M)
- **Role**: Conversational interactions specialist
- **Responsibilities**:
  - Handle greetings, small talk, simple Q&A
  - Provide quick, natural responses
  - Manage casual conversation flow
  - Basic explanation and clarification

**Strengths**:
- Very fast response times
- Low resource usage
- Natural conversation flow
- Good for simple interactions

**Limitations**:
- Cannot handle complex reasoning
- Limited technical analysis capability
- No multi-step task coordination

**File**: `src/agents/chat_agent.py`

### 3. Enhanced System Commands Agent
- **Model**: Llama 3.2 1B Instruct (Q4_K_M)
- **Role**: System command generation and validation
- **Responsibilities**:
  - Generate shell commands from natural language
  - Validate command safety and security
  - Explain command functionality
  - Provide command alternatives

**Security Features**:
- Whitelist of allowed commands
- Dangerous pattern detection
- Command syntax validation
- Security-focused prompting

**Strengths**:
- Fast command generation
- Strong security validation
- Clear command explanations
- Resource efficient

**Limitations**:
- Cannot handle complex system analysis
- Limited to single-system operations
- No multi-server orchestration

**File**: `src/agents/enhanced_system_commands_agent.py`

### 4. RAG Agent (Retrieval-Augmented Generation)
- **Model**: Llama 3.2 3B Instruct (Q4_K_M)
- **Role**: Document synthesis and analysis specialist
- **Responsibilities**:
  - Synthesize information from multiple documents
  - Perform query reformulation for better retrieval
  - Rank documents by relevance
  - Create comprehensive analysis from retrieved content

**Strengths**:
- Excellent document synthesis
- Complex information integration
- Query optimization
- Context-aware responses

**Limitations**:
- Requires pre-retrieved documents
- No real-time data access
- Higher resource usage

**File**: `src/agents/rag_agent.py`

### 5. Knowledge Retrieval Agent
- **Model**: Llama 3.2 1B Instruct (Q4_K_M) 
- **Role**: Fast fact lookup and simple retrieval
- **Responsibilities**:
  - Quick knowledge base searches
  - Simple fact retrieval
  - Basic question answering from KB
  - Vector database queries

**Strengths**:
- Very fast retrieval
- Low latency responses
- Efficient for simple lookups
- Good for factual queries

**Limitations**:
- Limited synthesis capability
- Cannot handle complex analysis
- No cross-document reasoning

**File**: `src/agents/kb_librarian_agent.py` (Enhanced)

### 6. Research Agent
- **Model**: Llama 3.2 3B Instruct (Q4_K_M) + Playwright
- **Role**: Web research and information gathering
- **Responsibilities**:
  - Coordinate multi-step web research
  - Extract and validate web information
  - Manage web scraping workflows
  - Store high-quality information back to KB

**Strengths**:
- Access to current information
- Multi-source research capability
- Quality assessment of sources
- Automated knowledge base updates

**Limitations**:
- Higher resource usage
- Requires internet connectivity
- Cannot access private/authenticated content

**File**: `src/agents/containerized_librarian_assistant.py`

## Request Routing Logic

### Routing Strategies

1. **Single Agent Routing**
   - Simple requests handled by one specialized agent
   - Fast, efficient processing
   - Used for: greetings, simple commands, basic questions

2. **Multi-Agent Coordination**
   - Complex requests requiring multiple capabilities
   - Primary agent handles main task
   - Secondary agents provide additional information
   - Used for: research + synthesis, command + analysis

3. **Orchestrator Fallback**
   - Complex reasoning tasks requiring 3B model
   - Multi-step problem solving
   - Used when no single agent is sufficient

### Routing Decision Matrix

| Request Type | Primary Agent | Secondary Agents | Strategy |
|-------------|--------------|------------------|----------|
| Greetings | Chat | - | Single |
| Simple Q&A | Chat | - | Single |
| System Commands | System Commands | - | Single |
| Fact Lookup | Knowledge Retrieval | - | Single |
| Document Analysis | RAG | Knowledge Retrieval | Multi |
| Web Research | Research | RAG | Multi |
| Complex Reasoning | Orchestrator | Various | Orchestrator |

## Configuration

### Model Assignment Configuration

The system uses the `get_task_specific_model()` function from `src/config.py`:

```python
agent_models = {
    "orchestrator": "llama3.2:3b-instruct-q4_K_M",
    "chat": "llama3.2:1b-instruct-q4_K_M", 
    "system_commands": "llama3.2:1b-instruct-q4_K_M",
    "rag": "llama3.2:3b-instruct-q4_K_M",
    "knowledge_retrieval": "llama3.2:1b-instruct-q4_K_M",
    "research": "llama3.2:3b-instruct-q4_K_M",
}
```

### Environment Variables

Override specific agent models:
```bash
export AUTOBOT_MODEL_CHAT="llama3.2:1b-instruct-q4_K_M"
export AUTOBOT_MODEL_SYSTEM_COMMANDS="codellama:7b-instruct"
export AUTOBOT_MODEL_RAG="llama3.2:3b-instruct-q4_K_M"
```

## Resource Usage

### Memory Requirements (Approximate)

| Agent | Model Size | RAM Usage | VRAM Usage |
|-------|------------|-----------|------------|
| Chat Agent | 1B | 1.2 GB | 0.8 GB |
| System Commands | 1B | 1.2 GB | 0.8 GB |
| Knowledge Retrieval | 1B | 1.2 GB | 0.8 GB |
| RAG Agent | 3B | 3.5 GB | 2.2 GB |
| Research Agent | 3B | 3.5 GB | 2.2 GB |
| Orchestrator | 3B | 3.5 GB | 2.2 GB |

**Note**: Models are loaded on-demand and can share memory when using the same base model.

## Performance Characteristics

### Response Times (Typical)

| Agent | Cold Start | Warm Response | Throughput |
|-------|------------|---------------|------------|
| Chat Agent | 2-3s | 200-500ms | High |
| System Commands | 2-3s | 300-600ms | High |
| Knowledge Retrieval | 1-2s | 100-300ms | Very High |
| RAG Agent | 3-4s | 800-1500ms | Medium |
| Research Agent | 5-10s | 2-5s | Low |

### Resource Efficiency

- **1B agents**: Optimized for speed and low resource usage
- **3B agents**: Balance between capability and efficiency
- **Orchestrator**: Smart routing minimizes unnecessary 3B model usage

## Integration Points

### Frontend Integration

The multi-agent system integrates with the existing frontend through:

1. **Chat Interface** (`backend/api/chat.py`)
   - Routes requests to Agent Orchestrator
   - Handles agent-specific metadata
   - Displays agent attribution in responses

2. **Settings Panel** (To be implemented)
   - Agent-specific configuration options
   - Model selection per agent
   - Performance monitoring

### Backend Services

- **LLM Interface** (`src/llm_interface.py`)
  - Manages model-specific requests
  - Handles different agent requirements
  - Provides usage analytics

- **Knowledge Base** (`src/knowledge_base.py`)
  - Shared across multiple agents
  - Provides document retrieval services
  - Manages vector embeddings

## Development Guidelines

### Adding New Agents

1. **Create Agent Class**
   ```python
   class NewAgent:
       def __init__(self):
           self.model_name = global_config_manager.get_task_specific_model("new_agent")
           
       async def process_request(self, request, context=None):
           # Implementation
   ```

2. **Update Configuration**
   - Add model mapping in `src/config.py`
   - Define capability characteristics
   - Set resource requirements

3. **Register with Orchestrator**
   - Add to `AgentType` enum
   - Update routing logic
   - Add capability mapping

4. **Update Package Exports**
   - Add to `src/agents/__init__.py`
   - Create singleton getter function

### Testing

```python
# Test individual agents
from src.agents import get_chat_agent, get_rag_agent

chat_agent = get_chat_agent()
result = await chat_agent.process_chat_message("Hello!")

# Test orchestration
from src.agents import get_agent_orchestrator

orchestrator = get_agent_orchestrator()
result = await orchestrator.process_request("Analyze this document...")
```

## Monitoring and Observability

### Agent Performance Metrics

- Response times per agent
- Resource utilization
- Routing accuracy
- Error rates

### Logging Structure

```python
logger.info(f"{agent_type} Agent processing: {request[:50]}...")
logger.info(f"Routing decision: {strategy} -> {primary_agent}")
logger.error(f"Agent {agent_type} error: {error}")
```

### Health Checks

Each agent supports health checking:
```python
agent.health_check()  # Returns status and capabilities
```

## Future Enhancements

### Planned Features

1. **Dynamic Model Scaling**
   - Auto-scale models based on load
   - Intelligent model selection

2. **Agent Learning**
   - Routing optimization based on success rates
   - Performance-based model selection

3. **GUI Configuration Agent**
   - Dedicated agent for GUI automation
   - Screen understanding and interaction

4. **Specialized Code Agent**
   - CodeLlama integration
   - Advanced code analysis and generation

### Scalability Considerations

- **Horizontal Scaling**: Agents can run as separate services
- **Load Balancing**: Route requests based on agent availability
- **Caching**: Share model instances and embeddings
- **Queue Management**: Handle high-volume requests efficiently

## Troubleshooting

### Common Issues

1. **Model Loading Errors**
   ```bash
   # Check Ollama model availability
   ollama list
   
   # Pull required models
   ollama pull llama3.2:1b-instruct-q4_K_M
   ollama pull llama3.2:3b-instruct-q4_K_M
   ```

2. **Memory Issues**
   - Monitor VRAM usage
   - Implement model unloading for unused agents
   - Use smaller quantized models if needed

3. **Routing Errors**
   - Check agent initialization
   - Verify model availability
   - Review routing logic logs

### Debug Mode

Enable detailed logging:
```bash
export AUTOBOT_DEBUG_AGENTS=true
export AUTOBOT_LOG_LEVEL=DEBUG
```

---

This multi-agent architecture provides a robust foundation for efficient, specialized AI assistance while maintaining resource efficiency and response quality.