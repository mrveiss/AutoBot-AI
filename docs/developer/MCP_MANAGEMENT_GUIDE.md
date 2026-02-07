# MCP Management Guide

**Date**: 2025-11-15
**Issue**: [#44](https://github.com/mrveiss/AutoBot-AI/issues/44)
**Purpose**: Comprehensive guide to managing AutoBot's Model Context Protocol (MCP) tools and bridges

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Backend MCP Registry API](#backend-mcp-registry-api)
4. [Frontend MCP Manager](#frontend-mcp-manager)
5. [Adding New MCP Bridges](#adding-new-mcp-bridges)
6. [Troubleshooting](#troubleshooting)

---

## Overview

### What is the MCP Registry?

The MCP Registry is a **centralized management system** for all AutoBot MCP tools and bridges. It provides:

- **Unified Discovery** - Browse all available MCP tools across all bridges
- **Health Monitoring** - Real-time status of each MCP bridge
- **Tool Documentation** - View schemas and usage information
- **Frontend Management** - Visual interface for developers

### Key Concepts

**MCP Bridge**: A module that exposes capabilities as MCP tools (e.g., `knowledge_mcp.py`, `vnc_mcp.py`)

**MCP Tool**: A specific capability exposed by a bridge (e.g., `search_knowledge_base`, `check_vnc_status`)

**MCP Registry**: The aggregator that collects and manages all MCP bridges

### Important Distinction

⚠️ **AutoBot's MCP vs Claude's MCP**

- **AutoBot's MCP** (`autobot-user-backend/api/*_mcp.py`) - Tools for AutoBot's LLM agents
- **Claude's MCP** (`.mcp/` folder) - Tools for Claude Code building AutoBot

This guide covers **AutoBot's MCP** only.

---

## Architecture

### System Overview

```
┌──────────────────────────────────────────────────┐
│         Frontend MCP Manager UI                   │
│         (MCPManager.vue)                          │
│                                                   │
│  Tabs: [Bridges] [Tools] [Health]                │
└───────────────────┬──────────────────────────────┘
                    │
                    │ HTTP REST API
                    ↓
┌──────────────────────────────────────────────────┐
│         Backend MCP Registry                      │
│         (mcp_registry.py)                         │
│                                                   │
│  Routes:                                          │
│  - GET /api/mcp/tools                             │
│  - GET /api/mcp/bridges                           │
│  - GET /api/mcp/health                            │
│  - GET /api/mcp/stats                             │
└───────────────────┬──────────────────────────────┘
                    │
        ┌───────────┼───────────┐
        │           │           │
        ↓           ↓           ↓
┌──────────┐ ┌──────────┐ ┌──────────┐
│knowledge │ │   vnc    │ │  future  │
│   _mcp   │ │   _mcp   │ │   _mcp   │
└──────────┘ └──────────┘ └──────────┘
```

### Component Responsibilities

| Component | File | Responsibility |
|-----------|------|---------------|
| **MCP Registry** | `autobot-user-backend/api/mcp_registry.py` | Aggregate all MCP bridges, provide unified API |
| **Knowledge MCP** | `autobot-user-backend/api/knowledge_mcp.py` | Expose knowledge base operations (search, add, vectors) |
| **VNC MCP** | `autobot-user-backend/api/vnc_mcp.py` | Expose VNC observation tools (status, activity, context) |
| **MCP Manager UI** | `autobot-user-frontend/src/components/developer/MCPManager.vue` | Visual management interface |

---

## Backend MCP Registry API

### Endpoints

#### `GET /api/mcp/tools`

**Purpose**: List all available MCP tools from all bridges

**Response**:
```json
{
  "status": "success",
  "total_tools": 8,
  "total_bridges": 2,
  "healthy_bridges": 2,
  "tools": [
    {
      "name": "search_knowledge_base",
      "description": "Search the AutoBot knowledge base...",
      "bridge": "knowledge_mcp",
      "bridge_description": "Knowledge Base Operations...",
      "endpoint": "/api/knowledge/mcp/search_knowledge_base",
      "input_schema": { /* JSON Schema */ },
      "features": ["search", "add_documents", "vector_similarity"]
    },
    {
      "name": "check_vnc_status",
      "description": "Check if VNC connection is active...",
      "bridge": "vnc_mcp",
      "endpoint": "/api/vnc/mcp/check_vnc_status",
      "input_schema": { /* JSON Schema */ }
    }
  ],
  "last_updated": "2025-11-15T10:30:00.000Z"
}
```

#### `GET /api/mcp/bridges`

**Purpose**: Get information about all MCP bridges

**Response**:
```json
{
  "status": "success",
  "total_bridges": 2,
  "healthy_bridges": 2,
  "bridges": [
    {
      "name": "knowledge_mcp",
      "description": "Knowledge Base Operations (LlamaIndex + Redis Vectors)",
      "endpoint": "/api/knowledge/mcp/tools",
      "features": ["search", "add_documents", "vector_similarity", "statistics"],
      "status": "healthy",
      "tool_count": 5
    },
    {
      "name": "vnc_mcp",
      "description": "VNC Observation and Browser Context",
      "endpoint": "/api/vnc/mcp/tools",
      "features": ["vnc_status", "observe_activity", "browser_context"],
      "status": "healthy",
      "tool_count": 3
    }
  ],
  "last_checked": "2025-11-15T10:30:00.000Z"
}
```

#### `GET /api/mcp/health`

**Purpose**: Get health status of all MCP bridges

**Response**:
```json
{
  "status": "healthy",
  "total_bridges": 2,
  "healthy_bridges": 2,
  "checks": [
    {
      "bridge": "knowledge_mcp",
      "status": "healthy",
      "response_time_ms": 42.5,
      "tool_count": 5
    },
    {
      "bridge": "vnc_mcp",
      "status": "healthy",
      "response_time_ms": 38.2,
      "tool_count": 3
    }
  ],
  "timestamp": "2025-11-15T10:30:00.000Z"
}
```

#### `GET /api/mcp/stats`

**Purpose**: Get usage statistics for MCP registry

**Response**:
```json
{
  "status": "success",
  "overview": {
    "total_tools": 8,
    "total_bridges": 2,
    "healthy_bridges": 2
  },
  "tools_by_bridge": {
    "knowledge_mcp": 5,
    "vnc_mcp": 3
  },
  "bridge_health": {
    "knowledge_mcp": "healthy",
    "vnc_mcp": "healthy"
  },
  "available_features": [
    "search", "add_documents", "vector_similarity",
    "vnc_status", "observe_activity", "browser_context"
  ],
  "timestamp": "2025-11-15T10:30:00.000Z"
}
```

#### `GET /api/mcp/tools/{bridge_name}/{tool_name}`

**Purpose**: Get detailed information about a specific MCP tool

**Example**: `GET /api/mcp/tools/knowledge_mcp/search_knowledge_base`

**Response**:
```json
{
  "status": "success",
  "tool": {
    "name": "search_knowledge_base",
    "description": "Search the AutoBot knowledge base using LlamaIndex and Redis vector store",
    "bridge": "knowledge_mcp",
    "bridge_description": "Knowledge Base Operations (LlamaIndex + Redis Vectors)",
    "endpoint": "/api/knowledge/mcp/search_knowledge_base",
    "input_schema": {
      "type": "object",
      "properties": {
        "query": {
          "type": "string",
          "description": "Search query"
        },
        "top_k": {
          "type": "integer",
          "description": "Number of results to return",
          "default": 5
        }
      },
      "required": ["query"]
    }
  }
}
```

---

## Frontend MCP Manager

### Location

**Component**: `autobot-user-frontend/src/components/developer/MCPManager.vue`

### Features

#### Overview Dashboard

Three cards showing:
- **Total MCP Tools** - Count across all bridges
- **Healthy Bridges** - Health ratio (e.g., 2/2)
- **Last Updated** - Time since last refresh + Refresh button

#### Bridges Tab

View all MCP bridges with:
- Bridge name and description
- Health status badge (healthy/degraded/unavailable)
- Tool count and feature count
- Features list (tags)
- API endpoint
- Error messages (if unhealthy)

#### Tools Tab

Browse and search all MCP tools:
- Search filter (by name, description, or bridge)
- Tool cards showing:
  - Tool name and description
  - Bridge information
  - API endpoint
  - Expandable JSON schema

#### Health Tab

Monitor system health:
- Overall MCP system status
- Per-bridge health checks showing:
  - Health status
  - Response time (ms)
  - Tool count
  - Error messages (if any)

### Auto-Refresh

The component automatically refreshes data every **30 seconds** to keep information current.

### Usage

**Access the MCP Manager:**

1. Navigate to **Developer Tools** section (or add to navigation)
2. Click **MCP Manager**
3. View bridges, tools, or health status
4. Use search to find specific tools
5. Expand tool schemas for documentation

---

## Adding New MCP Bridges

### Step 1: Create MCP Bridge Module

**File**: `autobot-user-backend/api/your_feature_mcp.py`

```python
"""
Your Feature MCP Bridge
Exposes your feature capabilities as MCP tools
"""

import logging
from typing import Any, Dict, List

from fastapi import APIRouter
from pydantic import BaseModel, Field

from src.utils.error_boundaries import ErrorCategory, with_error_handling

logger = logging.getLogger(__name__)
router = APIRouter(tags=["your_feature_mcp", "mcp"])


class MCPTool(BaseModel):
    """Standard MCP tool definition"""
    name: str
    description: str
    input_schema: Dict[str, Any]


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_your_feature_mcp_tools",
    error_code_prefix="YOUR_FEATURE_MCP",
)
@router.get("/mcp/tools")
async def get_your_feature_mcp_tools() -> List[MCPTool]:
    """Get available MCP tools for your feature"""
    tools = [
        MCPTool(
            name="your_tool_name",
            description="Description of what this tool does",
            input_schema={
                "type": "object",
                "properties": {
                    "param1": {
                        "type": "string",
                        "description": "Parameter description"
                    }
                },
                "required": ["param1"],
            },
        ),
    ]
    return tools


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="your_tool_name_mcp",
    error_code_prefix="YOUR_FEATURE_MCP",
)
@router.post("/mcp/your_tool_name")
async def your_tool_name_mcp(request: YourRequestModel) -> Dict[str, Any]:
    """MCP tool implementation: your_tool_name"""
    # Implementation here
    return {
        "success": True,
        "result": "Tool execution result"
    }
```

### Step 2: Register Router

**File**: `backend/app_factory.py`

```python
# Add import
from backend.api.your_feature_mcp import router as your_feature_mcp_router

# Add to core_routers list
core_routers = [
    # ... existing routers ...
    (your_feature_mcp_router, "/your_feature", ["your_feature", "mcp"], "your_feature_mcp"),
]
```

### Step 3: Add to MCP Registry

**File**: `autobot-user-backend/api/mcp_registry.py`

```python
# Add to MCP_BRIDGES list
MCP_BRIDGES = [
    # ... existing bridges ...
    (
        "your_feature_mcp",
        "Your Feature Description",
        "/api/your_feature/mcp/tools",
        ["feature1", "feature2", "feature3"],
    ),
]
```

### Step 4: Restart Backend

```bash
# Stop backend
pkill -f "uvicorn backend.app_factory"

# Start backend
bash run_autobot.sh --dev
```

### Step 5: Verify in UI

1. Open **MCP Manager** in frontend
2. Check **Bridges** tab - Your bridge should appear
3. Check **Tools** tab - Your tools should be listed
4. Check **Health** tab - Should show "healthy" status

---

## Troubleshooting

### Bridge Shows as "Unavailable"

**Symptom**: Bridge status is "unavailable" in MCP Manager

**Causes & Solutions**:

1. **Backend not restarted**
   - Solution: Restart backend to load new router
   - Command: `bash run_autobot.sh --dev`

2. **Router not registered**
   - Solution: Check `app_factory.py` includes your router in `core_routers`

3. **Endpoint incorrect**
   - Solution: Verify endpoint in `MCP_BRIDGES` matches actual router path
   - Check: `GET http://localhost:8001/api/your_feature/mcp/tools`

4. **Network issue**
   - Solution: Check backend is accessible on port 8001
   - Command: `curl http://localhost:8001/api/mcp/health`

### Tools Not Appearing

**Symptom**: Bridge is healthy but no tools shown

**Causes & Solutions**:

1. **Empty tools list**
   - Solution: Verify `/mcp/tools` endpoint returns non-empty array
   - Check: `curl http://localhost:8001/api/your_feature/mcp/tools`

2. **Wrong response format**
   - Solution: Tools must be array of `MCPTool` objects with `name`, `description`, `input_schema`

3. **Frontend not refreshed**
   - Solution: Click "Refresh Now" button or wait for auto-refresh (30s)

### Health Check Timeouts

**Symptom**: Health check shows "timeout" error

**Causes & Solutions**:

1. **Slow endpoint**
   - Solution: Optimize `/mcp/tools` endpoint response time
   - Target: < 3 seconds (timeout limit)

2. **Backend overloaded**
   - Solution: Check backend logs for performance issues
   - Command: `tail -f logs/backend.log`

3. **Network latency**
   - Solution: Check network connectivity between frontend and backend

### Frontend Component Not Found

**Symptom**: Cannot find MCP Manager in navigation

**Current Status**: Component created but not yet added to navigation

**Solution** (Pending):
1. Add to Developer Settings menu
2. Or add to System Monitor dashboard
3. Or create dedicated "Tools" menu section

---

## API Integration Examples

### Using MCP Registry in Python

```python
import aiohttp

async def list_all_mcp_tools():
    """Get all MCP tools from registry"""
    async with aiohttp.ClientSession() as session:
        async with session.get(
            "http://172.16.168.20:8001/api/mcp/tools"
        ) as response:
            data = await response.json()
            return data["tools"]

async def check_mcp_health():
    """Check health of all MCP bridges"""
    async with aiohttp.ClientSession() as session:
        async with session.get(
            "http://172.16.168.20:8001/api/mcp/health"
        ) as response:
            data = await response.json()
            return data["status"] == "healthy"
```

### Using MCP Registry in JavaScript

```javascript
// Fetch all MCP tools
async function fetchMCPTools() {
  const url = await AppConfig.getServiceUrl('backend');
  const response = await fetch(`${url}/api/mcp/tools`);
  const data = await response.json();
  return data.tools;
}

// Check specific bridge health
async function checkBridgeHealth(bridgeName) {
  const url = await AppConfig.getServiceUrl('backend');
  const response = await fetch(`${url}/api/mcp/health`);
  const data = await response.json();

  const bridge = data.checks.find(c => c.bridge === bridgeName);
  return bridge?.status === 'healthy';
}
```

---

## Best Practices

### MCP Bridge Development

1. **Use Standard MCPTool Model** - Always use the `MCPTool` BaseModel for consistency
2. **Descriptive Tool Names** - Use clear, action-oriented names (e.g., `search_knowledge_base`)
3. **Complete Schemas** - Provide full JSON schemas with descriptions and examples
4. **Error Handling** - Use `@with_error_handling` decorator on all endpoints
5. **Logging** - Log tool usage for debugging and monitoring

### Performance

1. **Fast Tools Endpoint** - `/mcp/tools` should respond in < 1 second
2. **Efficient Tool Execution** - Actual tool execution can be slower, but tools list must be fast
3. **Caching** - Consider caching tool definitions (they rarely change)

### Documentation

1. **Tool Descriptions** - Write clear, concise descriptions
2. **Schema Docs** - Document all parameters with descriptions and defaults
3. **Examples** - Provide usage examples in bridge module docstrings

---

## Related Documentation

- **VNC MCP Architecture**: `docs/developer/VNC_MCP_ARCHITECTURE.md`
- **Knowledge Base MCP**: `autobot-user-backend/api/knowledge_mcp.py` (inline docs)
- **AutoBot vs Claude MCP**: `CLAUDE.md` (MCP distinction)

---

## Summary

The MCP Management system provides:

- ✅ **Centralized Registry** - Single source of truth for all MCP capabilities
- ✅ **Visual Management** - User-friendly interface for developers
- ✅ **Health Monitoring** - Real-time status of all MCP bridges
- ✅ **Easy Discovery** - Browse and search all available tools
- ✅ **Extensible** - Simple process to add new MCP bridges

**Current MCP Bridges**:
- `knowledge_mcp` - Knowledge base operations
- `vnc_mcp` - VNC observation and browser context

**Future Growth**: New capabilities can be added as MCP bridges following the pattern above.

---

**Document Version**: 1.0
**Last Updated**: 2025-11-15
**GitHub Issue**: [#44](https://github.com/mrveiss/AutoBot-AI/issues/44)
