# MCP Knowledge Base Integration

## Overview

AutoBot provides MCP (Model Context Protocol) tools that allow the LLM to directly access the knowledge base through the full technology stack: LangChain for orchestration, LlamaIndex for indexing, and Redis for vector storage.

## Architecture

```
LLM → MCP Tools → Knowledge Base API → LangChain Orchestrator
                                      ↓
                                   LlamaIndex
                                      ↓
                              Redis Vector Store (DB 8)
```

## Technology Stack

1. **LangChain**: Agent orchestration, QA chains, and tool management
2. **LlamaIndex**: Document indexing, embedding generation, and retrieval
3. **Redis**: Vector storage with similarity search capabilities
4. **Ollama**: Local LLM for embeddings and text generation

## Available MCP Tools

### 1. search_knowledge_base
Search the AutoBot knowledge base using LlamaIndex and Redis vector store.

**Input Schema:**
```json
{
  "query": "string (required)",
  "top_k": "integer (default: 5)",
  "filters": "object (optional)"
}
```

**Example:**
```json
{
  "tool": "search_knowledge_base",
  "input": {
    "query": "How to configure Redis in AutoBot",
    "top_k": 3
  }
}
```

### 2. add_to_knowledge_base
Add new information to the AutoBot knowledge base (stored in Redis vectors).

### 3. vector_similarity_search
Perform vector similarity search in Redis using embeddings.

**Input Schema:**
```json
{
  "query": "string (required)",
  "top_k": "integer (default: 10)",
  "threshold": "number (default: 0.7)"
}
```

### 4. langchain_qa_chain
Use LangChain QA chain for comprehensive answers from knowledge base.

**Input Schema:**
```json
{
  "question": "string (required)",
  "context_size": "integer (default: 3)"
}
```

### 5. redis_vector_operations
Direct Redis vector store operations (advanced).

**Input Schema:**
```json
{
  "operation": "string (required) - one of: info, flush, reindex, backup",
  "params": "object (optional)"
}
```

**Input Schema:**
```json
{
  "content": "string (required)",
  "metadata": "object (optional)",
  "source": "string (optional)"
}
```

**Example:**
```json
{
  "tool": "add_to_knowledge_base",
  "input": {
    "content": "Redis configuration requires setting REDIS_HOST and REDIS_PORT environment variables",
    "metadata": {"category": "configuration", "component": "redis"},
    "source": "user_documentation"
  }
}
```

### 6. get_knowledge_stats
Get statistics about the AutoBot knowledge base and Redis vector store.

**Input Schema:**
```json
{
  "include_details": "boolean (default: false)"
}
```

### 7. summarize_knowledge_topic
Get a summary of knowledge on a specific topic using LangChain.

**Input Schema:**
```json
{
  "topic": "string (required)",
  "max_length": "integer (default: 500)"
}
```

## API Endpoints

- `GET /api/knowledge/mcp/tools` - List all available MCP tools
- `POST /api/knowledge/mcp/search_knowledge_base` - Execute search
- `POST /api/knowledge/mcp/add_to_knowledge_base` - Add document
- `POST /api/knowledge/mcp/get_knowledge_stats` - Get statistics
- `POST /api/knowledge/mcp/summarize_knowledge_topic` - Summarize topic
- `GET /api/knowledge/mcp/schema` - Get complete MCP schema
- `GET /api/knowledge/mcp/health` - Check MCP bridge health

## Integration with LLM

The LLM can now directly call these MCP tools instead of relying on the KB Librarian Agent. This provides:

1. **Direct Access**: LLM can query knowledge base without intermediate agents
2. **Structured Interface**: Type-safe tool definitions with schemas
3. **Async Operations**: Non-blocking knowledge base access
4. **Error Handling**: Graceful error responses for failed operations

## Example LLM Usage

When the LLM needs to search for information:

```python
# Instead of calling Python code:
# kb_agent.search("Redis configuration")

# The LLM can use MCP:
{
  "action": "use_tool",
  "tool_name": "search_knowledge_base",
  "tool_input": {
    "query": "Redis configuration",
    "top_k": 5
  }
}
```

## Benefits

1. **Performance**: Direct access without agent orchestration overhead
2. **Reliability**: MCP tools are stateless and can be retried
3. **Flexibility**: LLM can combine multiple knowledge operations
4. **Transparency**: Clear tool definitions and schemas
5. **Compatibility**: Works alongside existing agent-based system

## Migration Path

The MCP tools work alongside the existing KB Librarian Agent, allowing for:
- Gradual migration of functionality
- Backward compatibility with existing workflows
- A/B testing of direct vs agent-mediated access
- Fallback options if MCP tools are unavailable

## Configuration

Enable MCP knowledge base tools in the API registry:

```python
# backend/api/registry.py
"knowledge_mcp": RouterConfig(
    name="knowledge_mcp",
    module_path="backend.api.knowledge_mcp",
    prefix="/api/knowledge",
    tags=["knowledge", "mcp", "llm"],
    status=RouterStatus.ENABLED,
    description="MCP bridge for LLM access to knowledge base via LlamaIndex"
)
```

The knowledge base will automatically expose MCP-compatible methods that wrap the existing LlamaIndex functionality.