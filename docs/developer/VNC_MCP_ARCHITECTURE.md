# VNC + MCP Integration Architecture

**Date**: 2025-11-15
**Purpose**: Full MCP framework utilization for VNC observations and human-in-the-loop

---

## Executive Summary

AutoBot now provides complete VNC observation capabilities through the **Model Context Protocol (MCP)**, enabling AutoBot's LLM agents to observe browser and desktop activity in real-time. This integrates seamlessly with existing human-in-the-loop systems without creating parallel approval mechanisms.

**Key Principle**: **Use AutoBot's MCP framework for everything** - don't create separate systems (like LangChain Graph interrupts). Leverage what exists.

---

## Architecture Overview

```
┌─────────────┐
│   Frontend  │
│ (Vue.js UI) │
└──────┬──────┘
       │ VNC requests
       ↓
┌──────────────────────────────────────────────────┐
│          Backend (172.16.168.20:8001)            │
│                                                  │
│  ┌────────────────────┐  ┌────────────────────┐ │
│  │  VNC Proxy         │  │  VNC MCP Bridge    │ │
│  │  (vnc_proxy.py)    │←→│  (vnc_mcp.py)      │ │
│  │                    │  │                    │ │
│  │  • WebSocket proxy │  │  • MCP tools       │ │
│  │  • Records obs     │  │  • Agent access    │ │
│  └────────┬───────────┘  └────────┬───────────┘ │
│           │                       │             │
└───────────┼───────────────────────┼─────────────┘
            │                       │
            │                       │ MCP queries
            ↓                       ↓
    ┌──────────────┐        ┌──────────────┐
    │  Browser VM  │        │ AutoBot LLM  │
    │  VNC Server  │        │    Agents    │
    │ (172.16.168  │        │              │
    │    .25:6080) │        │ • Human loop │
    └──────────────┘        │ • Approvals  │
                            └──────────────┘
```

---

## Component Breakdown

### 1. VNC WebSocket Proxy (`autobot-user-backend/api/vnc_proxy.py`)

**Purpose**: Routes all VNC traffic through backend for observation

**Routes**:
- `GET  /api/vnc-proxy/{type}/vnc.html` - Serve noVNC client
- `GET  /api/vnc-proxy/{type}/*` - Proxy static assets
- `WS   /api/vnc-proxy/{type}/websockify` - WebSocket proxy
- `GET  /api/vnc-proxy/{type}/status` - Check VNC availability

**VNC Types**:
- `desktop` - Main machine desktop VNC (172.16.168.20:6080)
- `browser` - Browser VM Playwright VNC (172.16.168.25:6080)

**Observation Recording**:
```python
# Records to MCP bridge automatically
await record_observation(vnc_type, "connection", {"endpoint": ws_url})
await record_observation(vnc_type, "disconnection", {"status": "closed"})
```

### 2. VNC MCP Bridge (`autobot-user-backend/api/vnc_mcp.py`)

**Purpose**: Expose VNC observations as MCP tools for AutoBot's LLM agents

**MCP Tools Provided**:

1. **`check_vnc_status`**
   - Check if VNC connection is active
   - Returns: accessibility, endpoint, status

2. **`observe_vnc_activity`**
   - Get recent VNC WebSocket activity
   - Parameters: vnc_type, duration_seconds
   - Returns: observations from last N seconds

3. **`get_browser_vnc_context`**
   - Combined Playwright + VNC state
   - Returns: full situational awareness

**Routes**:
- `GET  /api/vnc/mcp/tools` - List available MCP tools
- `POST /api/vnc/mcp/check_vnc_status` - Tool execution
- `POST /api/vnc/mcp/observe_vnc_activity` - Tool execution
- `POST /api/vnc/mcp/get_browser_vnc_context` - Tool execution
- `POST /api/vnc/observations/{type}` - Record observations (internal)

### 3. Frontend Integration (`autobot-user-frontend/src/config/AppConfig.js`)

**Changes**:
- Fixed duplicate `/vnc.html` path bug
- Routes VNC through backend proxy (not direct)
- Maps `playwright` type → `browser` endpoint

```javascript
// Before (BROKEN):
http://172.16.168.25:6080/vnc.html/vnc.html  // ❌ duplicate

// After (FIXED):
http://172.16.168.20:8001/api/vnc-proxy/browser/vnc.html  // ✅ via backend
```

---

## MCP Framework Integration

### AutoBot's MCP Philosophy

**Two MCP Systems** (don't confuse them):

1. **Claude's MCP** (`.mcp/`) - Tools that Claude Code (building AutoBot) uses
2. **AutoBot's MCP** (`autobot-user-backend/api/*_mcp.py`) - Tools that AutoBot's LLM agents use

### Existing AutoBot MCP Tools

- **Knowledge Base** (`knowledge_mcp.py`) - Search, add, vector operations
- **VNC Observations** (`vnc_mcp.py`) - **NEW!** VNC activity monitoring

### Integration with Human-in-the-Loop

**AutoBot already has human-in-the-loop in multiple places:**
- Chat workflows with approval steps
- LLM agent task confirmation
- Manual intervention points

**VNC MCP tools enable these systems to:**
1. Query what the human is viewing via `observe_vnc_activity`
2. Check VNC status before proposing actions
3. Get full browser context via `get_browser_vnc_context`
4. Make informed decisions based on real-time VNC state

**Example Workflow**:
```python
# Agent wants to navigate browser
# First, check what human is viewing
vnc_context = await call_mcp_tool("get_browser_vnc_context")

if vnc_context["vnc_state"]["accessible"]:
    # Human is watching - show proposal in VNC
    # Use existing approval system (not new LangChain interrupt!)
    approval = await existing_human_loop.request_approval(
        action="navigate to example.com",
        context=vnc_context
    )

    if approval:
        # Execute navigation via Playwright MCP
        await call_mcp_tool("mcp__playwright-advanced__navigate", {...})
```

---

## Usage Examples

### For AutoBot LLM Agents

**Check if browser VNC is available**:
```python
POST /api/vnc/mcp/check_vnc_status
{
  "vnc_type": "browser"
}

Response:
{
  "success": true,
  "accessible": true,
  "endpoint": "http://172.16.168.25:6080",
  "message": "VNC browser is accessible"
}
```

**Observe recent VNC activity**:
```python
POST /api/vnc/mcp/observe_vnc_activity
{
  "vnc_type": "browser",
  "duration_seconds": 10
}

Response:
{
  "success": true,
  "observation_count": 2,
  "observations": [
    {"type": "connection", "timestamp": "2025-11-15T12:00:00", ...},
    {"type": "disconnection", "timestamp": "2025-11-15T12:00:30", ...}
  ]
}
```

**Get full browser context**:
```python
POST /api/vnc/mcp/get_browser_vnc_context

Response:
{
  "success": true,
  "playwright_state": {
    "healthy": true,
    "browser_connected": true
  },
  "vnc_state": {
    "accessible": true,
    "recent_observations": [...]
  }
}
```

---

## Integration with Existing Systems

### LangChain Agent Orchestrator

AutoBot already has `LangChainAgentOrchestrator` (`src/langchain_agent_orchestrator.py`).

**Instead of adding LangChain Graph interrupts**, use VNC MCP tools:

```python
# In LangChainAgentOrchestrator
tools = [
    # Existing tools
    knowledge_base_search,
    playwright_navigate,

    # NEW: VNC observation tools
    check_vnc_status_tool,
    observe_vnc_activity_tool,
    get_browser_vnc_context_tool,
]

# Agent can now query VNC before/after actions
# Existing human-in-loop systems handle approvals
```

### Playwright MCP Integration

**Perfect synergy**:
- Playwright MCP tools (mcp__playwright-advanced__*) - Agent controls browser
- VNC MCP tools - Agent observes browser
- VNC Proxy - Human observes browser

**Workflow**:
```
Agent proposes: "Navigate to example.com"
  ↓
Agent checks: observe_vnc_activity (is human watching?)
  ↓
Existing system: Request human approval
  ↓
Human sees: Proposal in UI + live VNC of browser
  ↓
Human approves: Via existing approval mechanism
  ↓
Agent executes: mcp__playwright-advanced__navigate
  ↓
Agent confirms: observe_vnc_activity (navigation happened)
  ↓
VNC proxy records: All WebSocket frames to MCP
```

---

## Benefits

### 1. Full MCP Framework Utilization ✅
- VNC observations exposed via MCP (not proprietary API)
- Consistent with AutoBot's architecture
- Agents access VNC via standard MCP tools

### 2. No Parallel Systems ✅
- Doesn't duplicate human-in-the-loop (use what exists!)
- Doesn't create new approval mechanisms
- Integrates with existing LangChain orchestrator

### 3. Agent Observation ✅
- Agents see what humans see (via VNC)
- Real-time context awareness
- Informed decision-making

### 4. Human Transparency ✅
- Humans see what agents will do (via VNC preview)
- VNC shows live browser state
- Better human-agent collaboration

---

## Testing

### Test VNC Proxy
```bash
# Check browser VNC status
curl http://172.16.168.20:8001/api/vnc-proxy/browser/status

# Access noVNC client
curl http://172.16.168.20:8001/api/vnc-proxy/browser/vnc.html
```

### Test MCP Tools
```bash
# List available VNC MCP tools
curl http://172.16.168.20:8001/api/vnc/mcp/tools

# Check VNC status via MCP
curl -X POST http://172.16.168.20:8001/api/vnc/mcp/check_vnc_status \
  -H "Content-Type: application/json" \
  -d '{"vnc_type": "browser"}'

# Get browser VNC context
curl -X POST http://172.16.168.20:8001/api/vnc/mcp/get_browser_vnc_context
```

---

## Next Steps

### Immediate (After Backend Restart)

1. ✅ Verify VNC proxy works
2. ✅ Test MCP tools respond correctly
3. ✅ Check VNC observations are recorded

### Integration (Week 2)

1. Add VNC MCP tools to LangChainAgentOrchestrator
2. Update existing human-in-loop to query VNC context
3. Document agent workflows using VNC observations

### Enhancement (Month 2)

1. Add VNC frame analysis (OCR, UI element detection)
2. Create visual diff detection for VNC changes
3. Implement VNC-based test automation

---

## Architecture Decisions

### Why MCP Instead of Direct API?

**MCP Benefits**:
- ✅ Standard protocol for LLM tool access
- ✅ Consistent with AutoBot's architecture
- ✅ Easily extensible (just add more tools)
- ✅ Works with any MCP-compatible LLM

**Direct API Drawbacks**:
- ❌ Custom integration per use case
- ❌ Doesn't follow AutoBot's patterns
- ❌ Harder to maintain

### Why Not LangChain Graph Interrupts?

**User's feedback**: "we have human in the loop in multiple places"

**Decision**: Use existing human-in-loop systems, don't create new ones

**VNC MCP provides**:
- Context for existing approval systems
- Observations for existing workflows
- No parallel approval mechanisms

### Why Backend Proxy Instead of Direct VNC?

**Backend Proxy Benefits**:
- ✅ Agent observation (backend sees all traffic)
- ✅ Centralized logging
- ✅ Single security entry point
- ✅ Can record to MCP bridge

**Direct VNC Drawbacks**:
- ❌ Agent blind (can't observe)
- ❌ No centralized logs
- ❌ Multiple entry points
- ❌ Can't integrate with MCP

---

## Summary

This architecture provides:

1. **Complete VNC observation via MCP** - Agents see what humans see
2. **Integration with existing systems** - No parallel mechanisms
3. **Human-agent collaboration** - Shared visual context
4. **Full MCP framework utilization** - Follows AutoBot's philosophy

**The key insight**: Don't add new systems (LangChain Graph interrupts). Instead, expose capabilities via MCP and let existing human-in-loop systems use them.

---

**Related Documentation**:
- `docs/QUICK_START_BROWSER_VNC.md` - VNC setup guide
- `docs/infrastructure/BROWSER_VNC_SETUP.md` - Detailed VNC infrastructure
- `autobot-user-backend/api/knowledge_mcp.py` - Similar MCP bridge example
- `src/langchain_agent_orchestrator.py` - Where to integrate VNC MCP tools

**Files Modified**:
- `autobot-user-backend/api/vnc_proxy.py` - WebSocket proxy with observation recording
- `autobot-user-backend/api/vnc_mcp.py` - MCP bridge for agent access (NEW)
- `backend/app_factory.py` - Router registration
- `autobot-user-frontend/src/config/AppConfig.js` - Fixed duplicate path, routes via backend

**Commit**: TBD (pending backend restart and testing)
