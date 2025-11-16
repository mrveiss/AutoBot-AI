# LangChain MCP Integration Guide

**Author**: mrveiss
**Version**: 1.0.0
**Date**: 2025-11-15
**Issue**: #48 - LangChain Agent Integration Examples for MCP Tools

## Overview

This guide explains how to integrate AutoBot's Model Context Protocol (MCP) bridges with LangChain agents to enable autonomous multi-step workflows. AutoBot provides 5 MCP bridges with 25+ tools that can be used by LangChain agents for tasks ranging from knowledge retrieval to file operations.

## AutoBot MCP Architecture

### Available MCP Bridges

| Bridge | Purpose | Tools Count |
|--------|---------|-------------|
| `knowledge_mcp` | Knowledge base operations via LlamaIndex + Redis vectors | 4 tools |
| `vnc_mcp` | VNC observation and browser context monitoring | 3 tools |
| `sequential_thinking_mcp` | Dynamic problem-solving with revision and branching | 4 tools |
| `structured_thinking_mcp` | 5-stage cognitive framework for organized thinking | 4 tools |
| `filesystem_mcp` | Secure file operations with whitelist access control | 13 tools |

**Total**: 25+ tools available for LangChain agents

### API Endpoints

All MCP tools are accessible via REST API:
- **Tool Discovery**: `GET /api/{bridge_name}/mcp/tools`
- **Tool Execution**: `POST /api/{bridge_name}/mcp/{tool_name}`
- **Registry Overview**: `GET /api/mcp/tools` (aggregated)

## Quick Start

### 1. Basic Setup

```python
"""Basic LangChain + AutoBot MCP Integration"""

import aiohttp
from typing import Any, Dict
from langchain.agents import initialize_agent, AgentType
from langchain.tools import Tool, StructuredTool
from langchain_anthropic import ChatAnthropic

# AutoBot backend configuration
AUTOBOT_BACKEND_URL = "http://172.16.168.20:8001"


async def call_mcp_tool(
    bridge_name: str,
    tool_name: str,
    params: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Call an AutoBot MCP tool via HTTP API.

    Args:
        bridge_name: MCP bridge name (e.g., 'filesystem_mcp')
        tool_name: Tool name within the bridge
        params: Tool parameters

    Returns:
        Tool execution result
    """
    url = f"{AUTOBOT_BACKEND_URL}/api/{bridge_name.replace('_mcp', '')}/mcp/{tool_name}"

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=params) as response:
            if response.status == 200:
                return await response.json()
            else:
                error_text = await response.text()
                raise Exception(f"MCP tool call failed: {response.status} - {error_text}")


def create_mcp_tool_sync(bridge_name: str, tool_name: str, description: str):
    """Create a synchronous LangChain tool from MCP tool"""
    import asyncio

    def tool_func(params_str: str) -> str:
        import json
        params = json.loads(params_str) if params_str else {}
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(call_mcp_tool(bridge_name, tool_name, params))
        return json.dumps(result, indent=2)

    return Tool(
        name=f"{bridge_name}_{tool_name}",
        func=tool_func,
        description=description
    )
```

### 2. Register All MCP Tools

```python
"""Register all AutoBot MCP tools with LangChain"""

def get_all_mcp_tools():
    """Get all AutoBot MCP tools as LangChain tools"""

    tools = []

    # Knowledge MCP Tools
    tools.append(create_mcp_tool_sync(
        "knowledge_mcp",
        "search_knowledge_base",
        "Search AutoBot knowledge base using vector similarity. Input: JSON with 'query' (string) and optional 'top_k' (int, default 5)"
    ))

    tools.append(create_mcp_tool_sync(
        "knowledge_mcp",
        "add_documents",
        "Add documents to knowledge base. Input: JSON with 'documents' (list of strings) and 'metadata' (dict)"
    ))

    tools.append(create_mcp_tool_sync(
        "knowledge_mcp",
        "vector_similarity",
        "Get vector similarity scores between texts. Input: JSON with 'text1' and 'text2'"
    ))

    tools.append(create_mcp_tool_sync(
        "knowledge_mcp",
        "statistics",
        "Get knowledge base statistics. Input: empty JSON {}"
    ))

    # VNC MCP Tools
    tools.append(create_mcp_tool_sync(
        "vnc_mcp",
        "vnc_status",
        "Get VNC desktop streaming status. Input: empty JSON {}"
    ))

    tools.append(create_mcp_tool_sync(
        "vnc_mcp",
        "observe_activity",
        "Observe current desktop activity. Input: empty JSON {}"
    ))

    tools.append(create_mcp_tool_sync(
        "vnc_mcp",
        "browser_context",
        "Get current browser context and state. Input: empty JSON {}"
    ))

    # Sequential Thinking MCP Tools
    tools.append(create_mcp_tool_sync(
        "sequential_thinking_mcp",
        "sequential_thinking",
        "Dynamic problem-solving through structured thinking. Input: JSON with 'thought' (string), 'thought_number' (int), 'total_thoughts' (int), 'next_thought_needed' (bool)"
    ))

    # Structured Thinking MCP Tools
    tools.append(create_mcp_tool_sync(
        "structured_thinking_mcp",
        "process_thought",
        "Process thought in 5-stage cognitive framework. Input: JSON with 'stage' (string: problem_definition|research|analysis|synthesis|conclusion) and 'thought' (string)"
    ))

    tools.append(create_mcp_tool_sync(
        "structured_thinking_mcp",
        "generate_summary",
        "Generate summary of thinking session. Input: JSON with 'session_id' (string)"
    ))

    tools.append(create_mcp_tool_sync(
        "structured_thinking_mcp",
        "clear_history",
        "Clear thinking history for session. Input: JSON with 'session_id' (string)"
    ))

    # Filesystem MCP Tools (Core Operations)
    tools.append(create_mcp_tool_sync(
        "filesystem_mcp",
        "read_text_file",
        "Read text file from allowed directories. Input: JSON with 'path' (string). Allowed: /home/kali/Desktop/AutoBot/, /tmp/autobot/, /home/kali/Desktop/"
    ))

    tools.append(create_mcp_tool_sync(
        "filesystem_mcp",
        "write_file",
        "Write content to file in allowed directories. Input: JSON with 'path' (string) and 'content' (string)"
    ))

    tools.append(create_mcp_tool_sync(
        "filesystem_mcp",
        "edit_file",
        "Edit file with find/replace. Input: JSON with 'path' (string), 'old_text' (string), 'new_text' (string)"
    ))

    tools.append(create_mcp_tool_sync(
        "filesystem_mcp",
        "list_directory",
        "List directory contents. Input: JSON with 'path' (string)"
    ))

    tools.append(create_mcp_tool_sync(
        "filesystem_mcp",
        "search_files",
        "Search for files by pattern. Input: JSON with 'path' (string) and 'pattern' (string)"
    ))

    tools.append(create_mcp_tool_sync(
        "filesystem_mcp",
        "directory_tree",
        "Get directory tree structure. Input: JSON with 'path' (string)"
    ))

    tools.append(create_mcp_tool_sync(
        "filesystem_mcp",
        "create_directory",
        "Create directory. Input: JSON with 'path' (string)"
    ))

    tools.append(create_mcp_tool_sync(
        "filesystem_mcp",
        "move_file",
        "Move/rename file. Input: JSON with 'source' (string) and 'destination' (string)"
    ))

    tools.append(create_mcp_tool_sync(
        "filesystem_mcp",
        "get_file_info",
        "Get file metadata. Input: JSON with 'path' (string)"
    ))

    tools.append(create_mcp_tool_sync(
        "filesystem_mcp",
        "read_multiple_files",
        "Read multiple files at once. Input: JSON with 'paths' (list of strings)"
    ))

    tools.append(create_mcp_tool_sync(
        "filesystem_mcp",
        "list_directory_with_sizes",
        "List directory with file sizes. Input: JSON with 'path' (string) and optional 'sort_by' (string: 'name' or 'size')"
    ))

    tools.append(create_mcp_tool_sync(
        "filesystem_mcp",
        "read_media_file",
        "Read image/audio file. Input: JSON with 'path' (string)"
    ))

    tools.append(create_mcp_tool_sync(
        "filesystem_mcp",
        "list_allowed_directories",
        "List all allowed directories. Input: empty JSON {}"
    ))

    return tools
```

### 3. Initialize LangChain Agent

```python
"""Initialize LangChain agent with MCP tools"""

def create_autobot_agent():
    """Create LangChain agent configured with all AutoBot MCP tools"""

    # Get all MCP tools
    mcp_tools = get_all_mcp_tools()

    # Initialize LLM (using Anthropic Claude)
    llm = ChatAnthropic(
        model="claude-sonnet-4-5-20250929",
        temperature=0,
        anthropic_api_key="your-api-key"
    )

    # Initialize agent with REACT description
    agent = initialize_agent(
        tools=mcp_tools,
        llm=llm,
        agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
        verbose=True,
        max_iterations=10,
        early_stopping_method="generate"
    )

    return agent


# Usage Example
if __name__ == "__main__":
    agent = create_autobot_agent()

    # Example task
    result = agent.run(
        "Search the knowledge base for information about error handling patterns, "
        "then list the backend/api/ directory to find related files."
    )

    print(f"Agent Result: {result}")
```

## Advanced Usage

### Structured Tools with Pydantic Models

```python
"""Using StructuredTool for better type safety"""

from pydantic import BaseModel, Field
from langchain.tools import StructuredTool


class SearchKnowledgeInput(BaseModel):
    """Input for knowledge base search"""
    query: str = Field(..., description="Search query string")
    top_k: int = Field(default=5, description="Number of results to return")


class FileReadInput(BaseModel):
    """Input for file reading"""
    path: str = Field(..., description="Absolute path to file within allowed directories")


def search_knowledge_structured(query: str, top_k: int = 5) -> str:
    """Search knowledge base with structured input"""
    import asyncio
    import json

    params = {"query": query, "top_k": top_k}
    loop = asyncio.get_event_loop()
    result = loop.run_until_complete(
        call_mcp_tool("knowledge_mcp", "search_knowledge_base", params)
    )
    return json.dumps(result, indent=2)


def read_file_structured(path: str) -> str:
    """Read file with structured input"""
    import asyncio
    import json

    params = {"path": path}
    loop = asyncio.get_event_loop()
    result = loop.run_until_complete(
        call_mcp_tool("filesystem_mcp", "read_text_file", params)
    )
    return json.dumps(result, indent=2)


# Create structured tools
search_tool = StructuredTool.from_function(
    func=search_knowledge_structured,
    name="search_knowledge",
    description="Search AutoBot knowledge base using vector similarity",
    args_schema=SearchKnowledgeInput
)

read_tool = StructuredTool.from_function(
    func=read_file_structured,
    name="read_file",
    description="Read text file from allowed directories",
    args_schema=FileReadInput
)
```

### Asynchronous Agent Execution

```python
"""Async agent execution for better performance"""

import asyncio
from langchain.agents import AgentExecutor
from langchain.tools import StructuredTool
from langchain_anthropic import ChatAnthropic


async def create_async_mcp_tool(
    bridge_name: str,
    tool_name: str,
    description: str
):
    """Create async LangChain tool from MCP tool"""

    async def async_tool_func(**kwargs) -> str:
        import json
        result = await call_mcp_tool(bridge_name, tool_name, kwargs)
        return json.dumps(result, indent=2)

    return StructuredTool.from_function(
        coroutine=async_tool_func,
        name=f"{bridge_name}_{tool_name}",
        description=description
    )


async def run_async_agent():
    """Run agent with async tool execution"""

    # Create async tools
    tools = [
        await create_async_mcp_tool(
            "filesystem_mcp",
            "list_directory",
            "List directory contents"
        ),
        await create_async_mcp_tool(
            "filesystem_mcp",
            "read_text_file",
            "Read text file"
        ),
    ]

    llm = ChatAnthropic(model="claude-sonnet-4-5-20250929", temperature=0)

    agent = initialize_agent(
        tools=tools,
        llm=llm,
        agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
        verbose=True
    )

    result = await agent.arun(
        "List the docs/ directory and read the README.md file"
    )

    return result


# Run async agent
if __name__ == "__main__":
    result = asyncio.run(run_async_agent())
    print(f"Async Agent Result: {result}")
```

### Error Handling Best Practices

```python
"""Robust error handling for MCP tool calls"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


async def call_mcp_tool_safe(
    bridge_name: str,
    tool_name: str,
    params: Dict[str, Any],
    timeout: int = 30,
    retry_count: int = 3
) -> Dict[str, Any]:
    """
    Call MCP tool with error handling, timeouts, and retries.

    Args:
        bridge_name: MCP bridge name
        tool_name: Tool name
        params: Tool parameters
        timeout: Request timeout in seconds
        retry_count: Number of retry attempts

    Returns:
        Tool result or error information
    """
    url = f"{AUTOBOT_BACKEND_URL}/api/{bridge_name.replace('_mcp', '')}/mcp/{tool_name}"

    for attempt in range(retry_count):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=params,
                    timeout=aiohttp.ClientTimeout(total=timeout)
                ) as response:

                    if response.status == 200:
                        return await response.json()

                    elif response.status == 400:
                        # Validation error - don't retry
                        error_text = await response.text()
                        logger.error(f"Validation error: {error_text}")
                        return {"error": "validation_error", "message": error_text}

                    elif response.status == 403:
                        # Access denied - don't retry
                        logger.error(f"Access denied for {tool_name}")
                        return {"error": "access_denied", "message": "Operation not permitted"}

                    elif response.status == 404:
                        # Tool not found - don't retry
                        logger.error(f"Tool {tool_name} not found")
                        return {"error": "not_found", "message": f"Tool {tool_name} not found"}

                    elif response.status >= 500:
                        # Server error - retry
                        if attempt < retry_count - 1:
                            logger.warning(f"Server error, retrying... (attempt {attempt + 1})")
                            await asyncio.sleep(2 ** attempt)  # Exponential backoff
                            continue

                        error_text = await response.text()
                        return {"error": "server_error", "message": error_text}

                    else:
                        error_text = await response.text()
                        return {"error": "unknown_error", "message": error_text}

        except asyncio.TimeoutError:
            if attempt < retry_count - 1:
                logger.warning(f"Timeout, retrying... (attempt {attempt + 1})")
                continue
            return {"error": "timeout", "message": f"Request timed out after {timeout}s"}

        except aiohttp.ClientError as e:
            if attempt < retry_count - 1:
                logger.warning(f"Connection error, retrying... (attempt {attempt + 1})")
                await asyncio.sleep(2 ** attempt)
                continue
            return {"error": "connection_error", "message": str(e)}

        except Exception as e:
            logger.exception(f"Unexpected error calling {tool_name}")
            return {"error": "unexpected_error", "message": str(e)}

    return {"error": "max_retries", "message": "Max retries exceeded"}


def create_mcp_tool_with_error_handling(
    bridge_name: str,
    tool_name: str,
    description: str
):
    """Create LangChain tool with robust error handling"""
    import asyncio
    import json

    def tool_func(params_str: str) -> str:
        params = json.loads(params_str) if params_str else {}
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(
            call_mcp_tool_safe(bridge_name, tool_name, params)
        )

        # Check for errors
        if "error" in result:
            error_msg = f"Tool error: {result['error']} - {result.get('message', 'Unknown error')}"
            logger.error(error_msg)
            return error_msg

        return json.dumps(result, indent=2)

    return Tool(
        name=f"{bridge_name}_{tool_name}",
        func=tool_func,
        description=description
    )
```

## Security Considerations

### Filesystem Access Control

AutoBot's filesystem MCP implements strict whitelist-based access control:

**Allowed Directories:**
- `/home/kali/Desktop/AutoBot/` - Project directory
- `/tmp/autobot/` - Temporary files
- `/home/kali/Desktop/` - User desktop

**Security Features:**
- Path traversal prevention (`../` blocked)
- Symlink resolution and validation
- Read-only for sensitive areas
- File size limits

**Agent Best Practices:**
```python
# Always validate paths before operations
def validate_path(path: str) -> bool:
    """Validate path is within allowed directories"""
    allowed = [
        "/home/kali/Desktop/AutoBot/",
        "/tmp/autobot/",
        "/home/kali/Desktop/",
    ]
    return any(path.startswith(d) for d in allowed)


# Example: Safe file reading
def read_file_safe(path: str) -> str:
    if not validate_path(path):
        return f"Error: Path {path} is not in allowed directories"

    # Proceed with MCP call
    return read_file_structured(path)
```

### API Rate Limiting

Implement rate limiting for agent workflows to prevent excessive API calls:

```python
import time
from collections import defaultdict

class RateLimiter:
    """Rate limiter for MCP tool calls"""

    def __init__(self, max_calls: int = 60, window_seconds: int = 60):
        self.max_calls = max_calls
        self.window = window_seconds
        self.calls = defaultdict(list)

    def can_call(self, tool_name: str) -> bool:
        """Check if tool can be called within rate limit"""
        now = time.time()

        # Remove old calls outside window
        self.calls[tool_name] = [
            t for t in self.calls[tool_name]
            if now - t < self.window
        ]

        if len(self.calls[tool_name]) >= self.max_calls:
            return False

        self.calls[tool_name].append(now)
        return True


rate_limiter = RateLimiter(max_calls=60, window_seconds=60)
```

## Testing and Debugging

### Test MCP Tool Connectivity

```python
"""Test MCP bridge connectivity"""

async def test_mcp_connectivity():
    """Test all MCP bridges are accessible"""

    bridges = [
        ("knowledge", "statistics"),
        ("vnc", "vnc_status"),
        ("sequential_thinking", "sequential_thinking"),
        ("structured_thinking", "generate_summary"),
        ("filesystem", "list_allowed_directories"),
    ]

    results = {}

    for bridge_short, tool in bridges:
        try:
            result = await call_mcp_tool(f"{bridge_short}_mcp", tool, {})
            results[bridge_short] = "OK"
        except Exception as e:
            results[bridge_short] = f"FAILED: {str(e)}"

    return results


if __name__ == "__main__":
    import asyncio
    results = asyncio.run(test_mcp_connectivity())

    for bridge, status in results.items():
        print(f"{bridge}: {status}")
```

### Debug Agent Execution

```python
"""Enable detailed debugging for agent execution"""

import langchain
langchain.verbose = True

# Set LangChain debug mode
from langchain.globals import set_debug
set_debug(True)

# Custom callback handler for MCP tool monitoring
from langchain.callbacks.base import BaseCallbackHandler

class MCPToolCallback(BaseCallbackHandler):
    """Monitor MCP tool calls during agent execution"""

    def on_tool_start(self, serialized, input_str, **kwargs):
        print(f"\n🔧 MCP Tool Call Started:")
        print(f"  Tool: {serialized.get('name', 'unknown')}")
        print(f"  Input: {input_str}")

    def on_tool_end(self, output, **kwargs):
        print(f"\n✅ MCP Tool Call Completed:")
        print(f"  Output: {output[:200]}...")

    def on_tool_error(self, error, **kwargs):
        print(f"\n❌ MCP Tool Error: {error}")


# Use callback in agent
agent = create_autobot_agent()
result = agent.run(
    "Search knowledge base for config patterns",
    callbacks=[MCPToolCallback()]
)
```

## Performance Optimization

### Parallel Tool Execution

```python
"""Execute multiple MCP tools in parallel"""

async def parallel_tool_execution():
    """Execute multiple independent tool calls in parallel"""

    tasks = [
        call_mcp_tool("filesystem_mcp", "list_directory", {"path": "/home/kali/Desktop/AutoBot/backend/"}),
        call_mcp_tool("filesystem_mcp", "list_directory", {"path": "/home/kali/Desktop/AutoBot/docs/"}),
        call_mcp_tool("knowledge_mcp", "statistics", {}),
        call_mcp_tool("vnc_mcp", "vnc_status", {}),
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    for i, result in enumerate(results):
        if isinstance(result, Exception):
            print(f"Task {i} failed: {result}")
        else:
            print(f"Task {i} succeeded: {result}")

    return results
```

### Caching Tool Results

```python
"""Cache frequently used tool results"""

from functools import lru_cache
import json


class MCPToolCache:
    """Cache for MCP tool results"""

    def __init__(self, max_size: int = 100, ttl_seconds: int = 300):
        self.cache = {}
        self.max_size = max_size
        self.ttl = ttl_seconds

    def get_cache_key(self, bridge: str, tool: str, params: dict) -> str:
        """Generate cache key"""
        params_str = json.dumps(params, sort_keys=True)
        return f"{bridge}:{tool}:{params_str}"

    def get(self, bridge: str, tool: str, params: dict):
        """Get cached result if available and not expired"""
        key = self.get_cache_key(bridge, tool, params)
        if key in self.cache:
            timestamp, result = self.cache[key]
            if time.time() - timestamp < self.ttl:
                return result
            del self.cache[key]
        return None

    def set(self, bridge: str, tool: str, params: dict, result):
        """Cache tool result"""
        if len(self.cache) >= self.max_size:
            # Remove oldest entry
            oldest_key = min(self.cache.keys(), key=lambda k: self.cache[k][0])
            del self.cache[oldest_key]

        key = self.get_cache_key(bridge, tool, params)
        self.cache[key] = (time.time(), result)


tool_cache = MCPToolCache()
```

## Related Documentation

- **MCP Tools Reference**: `docs/api/MCP_TOOLS_REFERENCE.md`
- **Agent Workflow Patterns**: `docs/developer/MCP_AGENT_PATTERNS.md`
- **Security Testing**: `docs/security/MCP_SECURITY_TESTING.md`
- **API Documentation**: `docs/api/COMPREHENSIVE_API_DOCUMENTATION.md`

## Example Workflows

See the `examples/mcp_agent_workflows/` directory for complete working examples:

1. **Research Workflow** (`research_workflow.py`)
   - Knowledge base search
   - Structured thinking organization
   - File write for documentation

2. **Code Analysis Workflow** (`code_analysis.py`)
   - File system navigation
   - Sequential thinking analysis
   - Knowledge base updates

3. **VNC Monitoring Workflow** (`vnc_monitoring.py`)
   - Desktop observation
   - Browser context extraction
   - Activity logging

## Next Steps

1. **Explore MCP Tools**: Use `GET /api/mcp/tools` to see all available tools
2. **Test Individual Tools**: Call tools directly before integrating with agents
3. **Build Custom Workflows**: Combine tools for specific use cases
4. **Monitor Performance**: Track tool call latency and success rates
5. **Implement Error Recovery**: Handle failures gracefully in agent workflows

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2025-11-15 | Initial documentation (Issue #48) |
