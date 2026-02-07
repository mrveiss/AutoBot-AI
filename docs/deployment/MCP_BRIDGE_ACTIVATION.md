# MCP Bridge Activation Procedure

**Status:** ✅ Complete
**Version:** 1.0.0
**Date:** 2025-11-15
**Issue:** #51 - Backend Activation Procedure for New MCP Bridges

## Overview

This document provides the standardized procedure for activating new MCP (Model Context Protocol) bridges in the AutoBot backend. When new MCP bridges are implemented, they require backend registration and verification to become operational.

## Current MCP Bridges (5 Total)

| Bridge | Status | Tools | Description |
|--------|--------|-------|-------------|
| `knowledge_mcp` | ✅ Active | 4 | Knowledge base operations (LlamaIndex + Redis) |
| `vnc_mcp` | ✅ Active | 3 | VNC observation and browser context |
| `sequential_thinking_mcp` | ✅ Active | 1 | Dynamic problem-solving framework |
| `structured_thinking_mcp` | ✅ Active | 4 | 5-stage cognitive framework |
| `filesystem_mcp` | ✅ Active | 13 | Secure file and directory operations |

**Total Tools Available:** 25 MCP tools

## Prerequisites

Before activating a new MCP bridge, ensure:

1. **Implementation Complete**
   - Bridge file created: `autobot-user-backend/api/{bridge_name}_mcp.py`
   - Follows standard MCP bridge pattern (see template below)
   - Has `GET /mcp/tools` endpoint returning tool definitions
   - Has `POST /mcp/{tool_name}` endpoints for each tool

2. **Router Registration**
   - Router imported in `backend/app_factory.py`
   - Router added to `ROUTERS` list with correct prefix and tags
   - Example:
     ```python
     from backend.api.{bridge_name}_mcp import router as {bridge_name}_mcp_router

     # In ROUTERS list:
     ({bridge_name}_mcp_router, "/{bridge_name}", ["{bridge_name}_mcp", "mcp"], "{bridge_name}_mcp"),
     ```

3. **MCP Registry Entry**
   - Bridge added to `MCP_BRIDGES` list in `autobot-user-backend/api/mcp_registry.py`
   - Entry format:
     ```python
     (
         "{bridge_name}_mcp",
         "Description of bridge functionality",
         "/api/{bridge_name}/mcp/tools",
         ["feature1", "feature2", "feature3"],
     ),
     ```

4. **Unit Tests Passing**
   - All tests pass: `pytest tests/ -k {bridge_name}`
   - No import errors
   - No runtime exceptions

## Activation Procedure

### Step 1: Verify Implementation Files

```bash
# Check bridge implementation file exists
ls -la autobot-user-backend/api/{bridge_name}_mcp.py

# Verify imports work
python -c "from backend.api.{bridge_name}_mcp import router; print('✅ Import successful')"

# Check router registration
grep -n "{bridge_name}_mcp" backend/app_factory.py

# Check MCP Registry entry
grep -n "{bridge_name}_mcp" autobot-user-backend/api/mcp_registry.py
```

### Step 2: Check Current Backend Status

```bash
# Check if backend is running
curl -s http://localhost:8001/api/health | jq

# Check current MCP bridges count
curl -s http://localhost:8001/api/mcp/bridges | jq '.total_bridges'

# Check current tool count
curl -s http://localhost:8001/api/mcp/tools | jq '.total_tools'
```

### Step 3: Graceful Backend Restart

```bash
# Option 1: Use run_autobot.sh (recommended)
bash run_autobot.sh --restart --dev

# Option 2: Use --verify-mcp flag for automatic verification
bash run_autobot.sh --restart --dev --verify-mcp

# Option 3: Manual restart
pkill -f "uvicorn backend.app:app"
sleep 2
bash run_autobot.sh --dev
```

### Step 4: Verify New Bridge Registration

```bash
# Wait for backend to fully start (5-10 seconds)
sleep 10

# Check backend health
curl -s http://localhost:8001/api/health | jq '.status'

# Verify new bridge appears in registry
curl -s http://localhost:8001/api/mcp/bridges | jq '.bridges[] | select(.name == "{bridge_name}_mcp")'

# Check bridge health status
curl -s http://localhost:8001/api/mcp/bridges | jq '.bridges[] | select(.name == "{bridge_name}_mcp") | .status'
```

### Step 5: Test Bridge Endpoints

```bash
# Get list of tools from new bridge
curl -s http://localhost:8001/api/{bridge_name}/mcp/tools | jq

# Count tools
TOOL_COUNT=$(curl -s http://localhost:8001/api/{bridge_name}/mcp/tools | jq 'length')
echo "✅ {bridge_name}_mcp: ${TOOL_COUNT} tools available"

# Test specific tool (if applicable)
curl -X POST http://localhost:8001/api/{bridge_name}/mcp/{tool_name} \
  -H "Content-Type: application/json" \
  -d '{"param": "value"}' | jq
```

### Step 6: Verify MCP Registry Aggregation

```bash
# Check total bridges increased
NEW_BRIDGE_COUNT=$(curl -s http://localhost:8001/api/mcp/bridges | jq '.total_bridges')
echo "Total Bridges: ${NEW_BRIDGE_COUNT}"

# Check total tools increased
NEW_TOOL_COUNT=$(curl -s http://localhost:8001/api/mcp/tools | jq '.total_tools')
echo "Total Tools: ${NEW_TOOL_COUNT}"

# Verify new bridge tools included in aggregation
curl -s http://localhost:8001/api/mcp/tools | jq '.tools[] | select(.bridge == "{bridge_name}_mcp") | .name'

# Check registry health
curl -s http://localhost:8001/api/mcp/health | jq
```

### Step 7: Frontend Verification

1. Navigate to: `http://localhost:5173/tools/mcp` (or Frontend VM IP)
2. Verify new bridge appears in MCP Manager UI
3. Check tool count matches expected number
4. Test tool execution from frontend (if applicable)

## Automated Activation Script

Use the provided script for automated activation and verification:

```bash
# Make script executable (first time only)
chmod +x scripts/utilities/activate-mcp-bridges.sh

# Run activation
bash scripts/utilities/activate-mcp-bridges.sh
```

**Script Features:**
- Verifies all bridge files exist
- Restarts backend gracefully
- Checks health of all bridges
- Validates tool counts
- Reports success/failure status

## Rollback Procedure

If activation fails or causes issues:

### Step 1: Identify Problem

```bash
# Check backend logs
tail -100 logs/backend.log

# Check for import errors
grep -i "error\|exception\|failed" logs/backend.log | tail -20

# Check specific bridge status
curl -s http://localhost:8001/api/mcp/bridges | jq '.bridges[] | select(.status != "healthy")'
```

### Step 2: Rollback Code Changes

```bash
# View recent commits
git log --oneline -10

# Revert specific commit
git revert <commit-hash>

# Or reset to previous state
git reset --hard HEAD~1
```

### Step 3: Restart Backend

```bash
bash run_autobot.sh --restart --dev
```

### Step 4: Verify Rollback

```bash
# Confirm old bridge count restored
curl -s http://localhost:8001/api/mcp/bridges | jq '.total_bridges'

# Confirm backend healthy
curl -s http://localhost:8001/api/health | jq '.status'
```

## Troubleshooting

### Issue: Bridge Not Appearing in `/api/mcp/bridges`

**Symptoms:**
- Bridge not in registry list
- Total bridge count unchanged

**Causes & Solutions:**

1. **Missing Router Registration**
   ```bash
   # Check app_factory.py
   grep "{bridge_name}_mcp_router" backend/app_factory.py
   ```
   **Solution:** Add router import and registration

2. **Missing MCP Registry Entry**
   ```bash
   # Check mcp_registry.py
   grep '"{bridge_name}_mcp"' autobot-user-backend/api/mcp_registry.py
   ```
   **Solution:** Add entry to MCP_BRIDGES list

3. **Backend Not Restarted**
   ```bash
   bash run_autobot.sh --restart
   ```

### Issue: 404 on Bridge Endpoint

**Symptoms:**
- `GET /api/{bridge_name}/mcp/tools` returns 404
- Bridge not accessible

**Causes & Solutions:**

1. **Wrong Router Prefix**
   ```python
   # Check app_factory.py - prefix should match endpoint
   ({bridge_name}_mcp_router, "/{bridge_name}", ...)
   ```
   **Solution:** Correct the prefix in ROUTERS list

2. **Router Not Mounting**
   ```bash
   # Check for import errors
   python -c "from backend.app_factory import create_app; app = create_app()"
   ```
   **Solution:** Fix import/syntax errors in bridge file

### Issue: Tools Not Aggregating

**Symptoms:**
- Bridge appears healthy
- Tools not in `/api/mcp/tools` response

**Causes & Solutions:**

1. **Incorrect Endpoint Path in Registry**
   ```python
   # Check MCP_BRIDGES entry - endpoint must match
   "/api/{bridge_name}/mcp/tools"  # Must be exact
   ```
   **Solution:** Correct endpoint path in MCP_BRIDGES

2. **Bridge Health Check Failing**
   ```bash
   curl -s http://localhost:8001/api/mcp/health | jq '.checks[] | select(.bridge == "{bridge_name}_mcp")'
   ```
   **Solution:** Fix bridge implementation errors

### Issue: Health Check Timeout

**Symptoms:**
- Bridge status shows "unavailable"
- 3-second timeout exceeded

**Causes & Solutions:**

1. **Bridge Endpoint Too Slow**
   - Check bridge `/mcp/tools` endpoint performance
   - Optimize if taking >3 seconds

2. **Bridge Has Runtime Errors**
   ```bash
   tail -f logs/backend.log | grep "{bridge_name}"
   ```
   **Solution:** Fix implementation errors

## MCP Bridge Implementation Template

Use this template when creating new MCP bridges:

```python
"""
{Bridge Name} MCP Bridge
{Description of functionality}
"""

import logging
from datetime import datetime
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.utils.error_boundaries import ErrorCategory, with_error_handling

logger = logging.getLogger(__name__)
router = APIRouter(tags=["{bridge_name}_mcp", "mcp"])


class MCPTool(BaseModel):
    """Standard MCP tool definition"""
    name: str
    description: str
    input_schema: Dict[str, Any]


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_{bridge_name}_mcp_tools",
    error_code_prefix="{BRIDGE_NAME}_MCP",
)
@router.get("/mcp/tools")
async def get_{bridge_name}_mcp_tools() -> List[MCPTool]:
    """Get available MCP tools for {bridge_name}"""
    tools = [
        MCPTool(
            name="tool_name",
            description="Tool description",
            input_schema={
                "type": "object",
                "properties": {
                    "param": {
                        "type": "string",
                        "description": "Parameter description"
                    }
                },
                "required": ["param"]
            }
        )
    ]
    return tools


# Tool implementations below...
@with_error_handling(...)
@router.post("/mcp/tool_name")
async def tool_name(...):
    pass
```

## Checklist for New MCP Bridge

**Implementation:**
- [ ] Bridge file created: `autobot-user-backend/api/{bridge_name}_mcp.py`
- [ ] Follows standard MCP pattern
- [ ] Has `GET /mcp/tools` endpoint
- [ ] Has tool execution endpoints
- [ ] Uses `@with_error_handling` decorator
- [ ] Proper logging implemented
- [ ] Input validation with Pydantic models

**Registration:**
- [ ] Router imported in `app_factory.py`
- [ ] Router added to ROUTERS list
- [ ] Entry added to MCP_BRIDGES in `mcp_registry.py`
- [ ] Prefix matches expected endpoint path

**Testing:**
- [ ] Unit tests written
- [ ] Import test passes
- [ ] Tool endpoints return valid responses
- [ ] Error handling works correctly

**Activation:**
- [ ] Backend restarted
- [ ] Bridge appears in registry
- [ ] Health check passes
- [ ] Tools aggregated correctly
- [ ] Frontend displays bridge

**Documentation:**
- [ ] Bridge functionality documented
- [ ] API endpoints documented
- [ ] Usage examples provided

## Monitoring Active Bridges

### Health Check Command

```bash
# Quick health status
curl -s http://localhost:8001/api/mcp/health | jq '.checks[] | {bridge: .bridge, status: .status, response_time_ms: .response_time_ms}'
```

### Performance Monitoring

```bash
# Check response times
curl -s http://localhost:8001/api/mcp/health | jq '.checks | sort_by(.response_time_ms) | reverse | .[:3]'

# Check for degraded/unavailable bridges
curl -s http://localhost:8001/api/mcp/health | jq '.checks[] | select(.status != "healthy")'
```

### Registry Statistics

```bash
# Get overall stats
curl -s http://localhost:8001/api/mcp/stats | jq

# Tools per bridge
curl -s http://localhost:8001/api/mcp/stats | jq '.tools_by_bridge'

# Available features
curl -s http://localhost:8001/api/mcp/stats | jq '.available_features'
```

## Related Documentation

- **MCP Registry API:** `autobot-user-backend/api/mcp_registry.py`
- **App Factory:** `backend/app_factory.py`
- **Security Testing:** `docs/security/MCP_SECURITY_TESTING.md`
- **Comprehensive API Docs:** `docs/api/COMPREHENSIVE_API_DOCUMENTATION.md`
- **System State:** `docs/system-state.md`

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2025-11-15 | Initial documentation (Issue #51) |

## References

- **GitHub Issue:** #51 - Backend Activation Procedure for New MCP Bridges
- **Related Issues:**
  - #45 - Sequential & Structured Thinking MCPs
  - #46 - Filesystem MCP
  - #44 - MCP Management
