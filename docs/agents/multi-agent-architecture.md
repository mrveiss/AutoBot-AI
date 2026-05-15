# AutoBot Multi-Agent Architecture

## Overview

AutoBot implements a sophisticated multi-agent architecture that distributes tasks across specialized agents, each optimized for specific types of requests. The system uses a 6-tier model routing architecture (#2553) that assigns appropriately sized models for different complexity levels.

## Architecture Diagram

```
+-------------------------------------------------------------------+
|                      Agent Orchestrator                            |
|                      (llama3.2:1b - Routing tier)                 |
|                                                                    |
|  - Request routing and coordination                               |
|  - Multi-agent workflow orchestration                             |
|  - Response synthesis and optimization                            |
+-------------------+-----------------------------------------------+
                    |
           +--------+--------+
           |   Route Request  |
           +--------+--------+
                    |
    +---------------+---------------+
    |               |               |
    v               v               v
+---------+  +---------+  +---------+
| Chat    |  |System   |  |   RAG   |
| Agent   |  |Commands |  | Agent   |
|(Quality)|  |(System) |  |(Instr.) |
+---------+  +---------+  +---------+
    v               v               v
+---------+  +---------+  +---------+
|Knowledge|  |Research |  |GUI Ctrl |
|Retrieval|  | Agent   |  | Agent   |
|(Classif)|  |(Quality)|  | (TBD)   |
+---------+  +---------+  +---------+
```

## 6-Tier Model Architecture

| Tier | Model | Purpose |
|------|-------|---------|
| **Routing** | `llama3.2:1b` | Orchestrator, request routing |
| **Classification** | `gemma2:2b` | Intent detection, category assignment |
| **Light Processing** | `phi3:mini` | Extraction, formatting |
| **Instruction** | `mistral:7b-instruct` | RAG, step execution |
| **System** | `dolphin-llama3:8b` | Commands, security |
| **Quality** | `qwen3.5:9b` | Chat, research, code |

## Agent Specifications

### 1. Agent Orchestrator
- **Model**: llama3.2:1b (Routing tier)
- **Role**: Central coordinator and router
- **Responsibilities**:
  - Analyze incoming requests
  - Route to appropriate specialized agents
  - Coordinate multi-agent workflows
  - Synthesize responses from multiple agents
  - Handle complex multi-step reasoning

**File**: `autobot-backend/agents/agent_orchestrator.py`

### 2. Chat Agent
- **Model**: qwen3.5:9b (Quality tier)
- **Role**: Conversational interactions specialist
- **Responsibilities**:
  - Handle greetings, small talk, simple Q&A
  - Provide quick, natural responses
  - Manage casual conversation flow
  - Basic explanation and clarification

**Strengths**:
- High-quality conversational responses
- Natural conversation flow
- Good for complex interactions
- Strong reasoning capabilities

**Limitations**:
- Higher resource usage than routing tier
- Cannot handle system-level operations

**File**: `autobot-backend/agents/chat_agent.py`

### 3. Enhanced System Commands Agent
- **Model**: dolphin-llama3:8b (System tier)
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
- Unrestricted command generation
- Strong security validation
- Clear command explanations

**Limitations**:
- Cannot handle complex system analysis
- Limited to single-system operations
- No multi-server orchestration

**File**: `autobot-backend/agents/enhanced_system_commands_agent.py`

### 4. RAG Agent (Retrieval-Augmented Generation)
- **Model**: mistral:7b-instruct (Instruction tier)
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

**File**: `autobot-backend/agents/rag_agent.py`

### 5. Knowledge Retrieval Agent
- **Model**: gemma2:2b (Classification tier)
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

**File**: `autobot-backend/agents/kb_librarian_agent.py` (Enhanced)

### 6. Research Agent
- **Model**: qwen3.5:9b (Quality tier) + Playwright
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

**File**: `autobot-backend/agents/containerized_librarian_assistant.py`

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
   - Complex reasoning tasks requiring higher-tier models
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

### Model Assignment Configuration (6-Tier)

The system uses the `get_task_specific_model()` function from `src/config.py`:

```python
agent_models = {
    "orchestrator": "llama3.2:1b",           # Routing tier
    "classification": "gemma2:2b",            # Classification tier
    "extraction": "phi3:mini",                # Light Processing tier
    "rag": "mistral:7b-instruct",            # Instruction tier
    "system_commands": "dolphin-llama3:8b",   # System tier
    "chat": "qwen3.5:9b",                    # Quality tier
    "research": "qwen3.5:9b",                # Quality tier
    "knowledge_retrieval": "gemma2:2b",       # Classification tier
}
```

### Environment Variables

Override specific agent models:
```bash
export AUTOBOT_MODEL_TIER_ROUTING="llama3.2:1b"
export AUTOBOT_MODEL_TIER_CLASSIFICATION="gemma2:2b"
export AUTOBOT_MODEL_TIER_LIGHT="phi3:mini"
export AUTOBOT_MODEL_TIER_INSTRUCTION="mistral:7b-instruct"
export AUTOBOT_MODEL_TIER_SYSTEM="dolphin-llama3:8b"
export AUTOBOT_MODEL_TIER_QUALITY="qwen3.5:9b"
```

## Resource Usage

### Memory Requirements (Approximate)

| Agent | Model | Tier | RAM Usage | VRAM Usage |
|-------|-------|------|-----------|------------|
| Orchestrator | llama3.2:1b | Routing | 1.2 GB | 0.8 GB |
| Classification | gemma2:2b | Classification | 1.8 GB | 1.2 GB |
| Knowledge Retrieval | gemma2:2b | Classification | 1.8 GB | 1.2 GB |
| RAG Agent | mistral:7b-instruct | Instruction | 4.1 GB | 3.5 GB |
| System Commands | dolphin-llama3:8b | System | 4.7 GB | 4.0 GB |
| Chat Agent | qwen3.5:9b | Quality | 5.5 GB | 4.5 GB |
| Research Agent | qwen3.5:9b | Quality | 5.5 GB | 4.5 GB |

**Note**: Models are loaded on-demand and can share memory when using the same base model.

## Performance Characteristics

### Response Times (Typical)

| Agent | Cold Start | Warm Response | Throughput |
|-------|------------|---------------|------------|
| Orchestrator | 1-2s | 80-200ms | Very High |
| Classification | 1-2s | 150-300ms | High |
| Knowledge Retrieval | 1-2s | 100-300ms | Very High |
| RAG Agent | 3-4s | 800-1500ms | Medium |
| System Commands | 3-4s | 400-800ms | Medium |
| Chat Agent | 3-5s | 500-1500ms | Medium |
| Research Agent | 5-10s | 2-5s | Low |

### Resource Efficiency

- **Routing/Classification tier agents**: Optimized for speed and low resource usage
- **Instruction/System tier agents**: Balance between capability and efficiency
- **Quality tier agents**: Maximum capability for complex tasks
- **Orchestrator**: Smart routing minimizes unnecessary large model usage

## Integration Points

### Frontend Integration

The multi-agent system integrates with the existing frontend through:

1. **Chat Interface** (`autobot-backend/api/chat.py`)
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
   - Add to `autobot-backend/agents/__init__.py`
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

   # Pull required 6-tier models
   ollama pull llama3.2:1b
   ollama pull gemma2:2b
   ollama pull phi3:mini
   ollama pull mistral:7b-instruct
   ollama pull dolphin-llama3:8b
   ollama pull qwen3.5:9b
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

This multi-agent architecture provides a robust foundation for efficient, specialized AI assistance while maintaining resource efficiency and response quality through the 6-tier model routing system.
