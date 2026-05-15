# API Consolidation Priority Plan

Based on frontend usage audit and backend duplication analysis.

## 🚨 **CRITICAL PRIORITY (Fix Immediately)**

### **1. Chat Endpoints - BROKEN FUNCTIONALITY**
**Problem**: Frontend calls `/api/chats/*` but backend only has `/api/chat` and legacy endpoints
**Impact**: Chat management likely broken in production
**Action**:
- ✅ Already fixed in recent edits (updated frontend to use `/api/list_sessions`, `/api/load_session/{id}`)
- Still need to implement proper `/api/chats/*` in backend for consistency

### **2. Project State Endpoints - MISSING**
**Problem**: PhaseProgressionIndicator calls `/api/project/*` endpoints that don't exist
**Impact**: Phase management UI completely broken
**Frontend Usage**:
```javascript
await apiRequest('/api/project/status')
await apiRequest('/api/project/report')
await apiRequest('/api/phases/status')
await apiRequest('/api/phases/validation/run')
```
**Action**: Create project state API endpoints immediately

## 🔥 **HIGH PRIORITY (Fix This Week)**

### **3. Terminal API Chaos - 4 COMPETING SYSTEMS**
**Frontend Usage**:
- TerminalWindow.vue: Uses WebSocket `/api/terminal/ws/simple/`
- Multiple components call `/api/terminal/execute`, `/api/terminal/sessions`
**Backend Reality**: 4 different terminal implementations!
- `terminal.py` - Main API
- `simple_terminal_websocket.py` - WebSocket simple
- `secure_terminal_websocket.py` - WebSocket secure
- `base_terminal.py` - Base functions
**Action**: Consolidate to single terminal API

### **4. Health Check Sprawl - 37+ IMPLEMENTATIONS** ✅ Partial (Issue #3333)
**Frontend Usage**: Only calls `/api/system/health` (good!)
**Backend Reality**: 37+ different health endpoints across modules (12 noted originally, audit
found more)
**Action**: Deprecate unused health endpoints, keep `/api/system/health` as primary
**Completed (Issue #3333)**:
- Audited all health endpoints in `autobot-backend/api/`
- Primary endpoint `/api/system/health` kept as-is (no changes)
- Frontend-called endpoints kept as-is: `/api/long-running/health`,
  `/api/monitoring/services/health`
- Added deprecation `logger.warning` + `deprecated`/`use_instead` response fields to 9 endpoints
  with boilerplate static responses or unregistered routers:
  - `analytics_llm_patterns.py` → `/api/llm-patterns/health`
  - `analytics_code_generation.py` → `/api/code-generation/health`
  - `analytics_dfa.py` → `/api/dfa-analytics/health`
  - `analytics_architecture.py` → `/api/architecture/health`
  - `analytics_cfg.py` → `/api/cfg-analytics/health`
  - `services.py` → `/api/services/health`
  - `mesh_brain.py` → deleted (#3354, unregistered router — dead module)
  - `monitoring_compat.py` → deleted (#3354, unregistered router — already deprecated module)
  - `natural_language_search.py` → `/api/health` (no-prefix collision risk)
- Remaining endpoints have legitimate per-service logic (Redis ping, real service checks)
  and are not called by the frontend

## 📋 **MEDIUM PRIORITY (Fix This Month)**

### **5. Configuration Scattered - 8 ENDPOINTS**
**Frontend Usage**:
- `/api/settings/` (main)
- `/api/settings/config`
- `/api/settings/backend`
**Backend Reality**: 8 different config endpoints
**Action**: Route all config through settings.py, deprecate others

### **6. Workflow Duplication - 3 SYSTEMS**
**Frontend Usage**: Consistently uses `/api/workflow/*` ✅
**Backend Reality**: 3 workflow implementations
- `workflow.py` ✅ (Used by frontend)
- `workflow_automation.py` ❌ (Unused?)
- `advanced_workflow_orchestrator.py` ❌ (Unused?)
**Action**: Deprecate unused workflow systems

### **7. Knowledge Base Confusion - 3 APIS**
**Frontend Usage**:
- `/api/knowledge_base/*` (primary)
- `/api/chat_knowledge/*` (chat-specific)
- `/api/kb_librarian/*` (librarian)
**Backend Reality**: All 3 exist but overlap significantly
**Action**: Define clear boundaries or merge

## 🔧 **LOW PRIORITY (Technical Debt)**

### **8. Agent Management - 3 SYSTEMS**
**Frontend Usage**: Limited usage of `/api/agent-config/*`
**Backend Reality**: 3 agent APIs with significant overlap
**Action**: Merge when other priorities complete

### **9. WebSocket Chaos - MULTIPLE IMPLEMENTATIONS**
**Frontend Usage**:
- Terminal WebSockets (working)
- Monitoring WebSockets (working)
**Backend Reality**: Scattered WebSocket implementations
**Action**: Consolidate WebSocket patterns

## 📊 **Implementation Strategy**

### **Week 1: Critical Fixes**
1. **Implement missing project state endpoints**
   - Create `/api/project/status`
   - Create `/api/project/report`
   - Create `/api/phases/*` endpoints
2. **Verify chat endpoint fixes are working**

### **Week 2: Terminal Consolidation**
1. **Audit which terminal endpoints frontend actually uses**
2. **Choose primary terminal implementation** (likely `terminal.py` + `simple_terminal_websocket.py`)
3. **Deprecate unused terminal APIs**
4. **Update documentation**

### **Week 3: Health Check Cleanup** ✅ Phase 1 done (Issue #3333)
1. ✅ **Audit all health endpoints** — found 37+ (not 12 as originally estimated)
2. ✅ **Keep `/api/system/health` as primary** — no changes to primary endpoint
3. ✅ **Add deprecation warnings to boilerplate endpoints** — 9 endpoints updated
4. **Route internal health checks through system API** — deferred: remaining endpoints
   have legitimate per-service logic and are not called by the frontend

### **Week 4: Configuration Consolidation**
1. **Route all config through `/api/settings/*`**
2. **Deprecate scattered config endpoints**
3. **Add backward compatibility layer**

## 🎯 **Success Metrics**

- **50% reduction** in total API endpoints
- **Zero frontend 404 errors** from missing endpoints
- **Single source of truth** for each functionality
- **Consistent naming patterns** across all APIs
- **Clear deprecation timeline** for old endpoints

## 🚨 **Risk Mitigation**

1. **Backward Compatibility**: Keep old endpoints with deprecation warnings initially
2. **Frontend Testing**: Test all UI components after each consolidation
3. **Gradual Migration**: Move one endpoint category at a time
4. **Documentation**: Update API docs immediately after changes
5. **Monitoring**: Watch for 404 errors in production logs

## 📈 **Expected Benefits**

- **Faster frontend development** (clear API patterns)
- **Easier testing** (fewer duplicate code paths)
- **Better performance** (optimized single implementations)
- **Simpler maintenance** (less duplicate code)
- **Clearer documentation** (single API reference)
