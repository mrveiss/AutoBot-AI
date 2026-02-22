# MCP Agent Workflow Examples

Reusable workflow examples demonstrating AutoBot MCP tool integration for autonomous multi-step tasks.

**Issue**: #48 - LangChain Agent Integration Examples for MCP Tools

## Architecture

```
mcp_agent_workflows/
├── __init__.py          # Package exports (all shared utilities)
├── base.py              # Shared base module (MCPClient, WorkflowResult, utilities)
├── research_workflow.py # Knowledge base research example
├── code_analysis.py     # Sequential thinking code analysis example
└── vnc_monitoring.py    # VNC desktop monitoring example
```

## Key Features

- **No Code Duplication**: All shared functionality in `base.py`
- **No Hardcoded Values**: Uses `NetworkConstants` with environment variable fallback
- **Proper Error Handling**: `MCPToolError` with retry logic and backoff
- **Workflow Tracking**: `WorkflowResult` container for step-by-step results
- **Reusable Utilities**: Common file operations and timestamp formatting

## Quick Start

```python
# Import from package
from examples.mcp_agent_workflows import (
    MCPClient,
    call_mcp_tool,
    WorkflowResult,
    ensure_directory_exists,
)

# Use default client
result = await call_mcp_tool("filesystem_mcp", "list_directory", {"path": "/tmp"})

# Or create custom client
client = MCPClient(timeout_seconds=60, max_retries=5)
result = await client.call_tool("knowledge_mcp", "search_knowledge_base", {"query": "Python"})

# Track workflow progress
workflow = WorkflowResult("my_workflow")
workflow.add_step("step1", "success", {"data": "result"})
workflow.complete()
print(workflow.to_json())
```

## Configuration

### Using NetworkConstants (Recommended)

The base module automatically uses `NetworkConstants` from AutoBot:

```python
from src.utils.network_constants import NetworkConstants

AUTOBOT_BACKEND_URL = f"http://{NetworkConstants.MAIN_MACHINE_IP}:{NetworkConstants.BACKEND_PORT}"
```

### Environment Variable Override

Set `AUTOBOT_BACKEND_URL` for standalone usage:

```bash
export AUTOBOT_BACKEND_URL="https://172.16.168.20:8443"
python -m examples.mcp_agent_workflows.research_workflow
```

### Custom Client Configuration

```python
client = MCPClient(
    backend_url="http://custom-host:8001",  # Override URL
    timeout_seconds=30,                      # Request timeout
    max_retries=3,                           # Retry on server errors
    log_requests=True,                       # Enable request logging
)
```

## Available Workflows

### 1. Research Workflow

Uses knowledge base search and structured thinking to research topics:

```bash
python -m examples.mcp_agent_workflows.research_workflow
```

**MCP Tools Used**:
- `knowledge_mcp.search_knowledge_base` - Vector similarity search
- `structured_thinking_mcp.process_thought` - 5-stage cognitive framework
- `structured_thinking_mcp.generate_summary` - Summary generation
- `filesystem_mcp.write_file` - Report file output

### 2. Code Analysis Workflow

Analyzes codebase structure using sequential thinking:

```bash
python -m examples.mcp_agent_workflows.code_analysis
```

**MCP Tools Used**:
- `filesystem_mcp.search_files` - Pattern-based file search
- `filesystem_mcp.read_text_file` - File content reading
- `sequential_thinking_mcp.sequential_thinking` - Step-by-step analysis
- `knowledge_mcp.add_documents` - Knowledge base updates

### 3. VNC Monitoring Workflow

Monitors desktop activity and browser context:

```bash
python -m examples.mcp_agent_workflows.vnc_monitoring
```

**MCP Tools Used**:
- `vnc_mcp.vnc_status` - Desktop status check
- `vnc_mcp.observe_activity` - Activity capture
- `vnc_mcp.browser_context` - Browser state monitoring
- `filesystem_mcp.write_file` - Activity log output

## Shared Utilities

### MCPClient

Reusable client with retry logic and error handling:

```python
from examples.mcp_agent_workflows import MCPClient

client = MCPClient()

# Raises MCPToolError on failure
result = await client.call_tool("bridge", "tool", {"params": "value"})

# Returns error dict instead of raising
result = await client.call_tool_safe("bridge", "tool", {})
if "error" in result:
    print(f"Failed: {result['message']}")
```

### WorkflowResult

Container for tracking multi-step workflows:

```python
from examples.mcp_agent_workflows import WorkflowResult

workflow = WorkflowResult("my_workflow")
workflow.add_step("step1", "success", {"key": "value"})
workflow.add_step("step2", "error", error="Something failed")
workflow.complete()

# Get summary
print(f"Success: {workflow.success}")
print(f"Steps: {workflow.to_dict()}")
```

### File Operations

Safe file operations with error handling:

```python
from examples.mcp_agent_workflows import ensure_directory_exists, write_file_safe, read_file_safe

await ensure_directory_exists("/tmp/autobot")
await write_file_safe("/tmp/autobot/output.txt", "content")
content = await read_file_safe("/tmp/autobot/output.txt")
```

### Timestamp Utilities

```python
from examples.mcp_agent_workflows import format_timestamp, format_iso_timestamp, generate_session_id

print(format_timestamp())        # 2025-01-16 14:30:45
print(format_iso_timestamp())    # 2025-01-16T14:30:45.123456
print(generate_session_id())     # session_20250116_143045
```

## Error Handling

The base module provides structured error handling:

```python
from examples.mcp_agent_workflows import MCPToolError, call_mcp_tool

try:
    result = await call_mcp_tool("bridge", "tool", {})
except MCPToolError as e:
    print(f"Bridge: {e.bridge}")
    print(f"Tool: {e.tool}")
    print(f"Status: {e.status}")
    print(f"Message: {e.message}")
```

Error types:
- **400**: Validation error (no retry)
- **403**: Access denied (no retry)
- **404**: Tool not found (no retry)
- **422**: Invalid request (no retry)
- **5xx**: Server error (retries with exponential backoff)
- **Timeout**: Request timeout (retries with backoff)
- **Connection**: Network error (retries with backoff)

## Integration with LangChain

See the main integration guide: [`docs/developer/LANGCHAIN_MCP_INTEGRATION.md`](../../docs/developer/LANGCHAIN_MCP_INTEGRATION.md)

---

*Author: mrveiss*
*Generated for AutoBot MCP Agent Workflows*
