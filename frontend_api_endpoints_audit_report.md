# Frontend API Endpoint Usage Audit Report

## Executive Summary

This comprehensive audit analyzed all frontend files (.vue, .js, .ts) to catalog API endpoint usage across the AutoBot Vue frontend application. The analysis reveals significant inconsistencies in endpoint usage, multiple duplicate endpoints, and missing backend implementations for actively used frontend endpoints.

## Key Findings

### Critical Issues
1. **Frontend uses missing endpoints**: Many frontend components call endpoints that don't exist in the backend
2. **Inconsistent endpoint patterns**: Multiple ways to call the same functionality
3. **Hardcoded URLs**: Many components bypass the centralized API client
4. **Legacy endpoint usage**: Old endpoint patterns still in use alongside new ones

## Detailed Analysis

### 1. CHAT ENDPOINTS

#### **Actively Used by Frontend:**
- `/api/chat` (POST) - Send messages - **HIGH FREQUENCY**
- `/api/chats` (GET) - List chats
- `/api/chats/new` (POST) - Create new chat
- `/api/chats/{id}` (GET) - Get chat messages
- `/api/chats/{id}` (DELETE) - Delete chat
- `/api/chats/{id}/save` (POST) - Save chat messages
- `/api/reset` (POST) - Reset chat
- `/api/history` (GET) - Get chat history **LEGACY**
- `/api/list_sessions` (GET) - List sessions **LEGACY**
- `/api/load_session/{id}` (GET) - Load session **LEGACY**

#### **Backend Available:**
- `/api/chat` (POST) - ✅ Available (chat_router)
- `/api/chats/*` - ❌ **MISSING** (not in backend routers)

#### **Conflict Analysis:**
- **MAJOR CONFLICT**: Frontend uses both new `/api/chats/*` pattern AND legacy `/api/list_sessions`, `/api/load_session` patterns
- **RECOMMENDATION**: Consolidate to `/api/chats/*` pattern

### 2. SYSTEM/HEALTH ENDPOINTS

#### **Actively Used by Frontend:**
- `/api/system/health` (GET) - **VERY HIGH FREQUENCY** (App.vue, SettingsPanel.vue, SystemMonitor.vue)
- `/api/system/info` (GET) - System information
- `/api/system/status` (GET) - System status

#### **Backend Available:**
- `/api/system/health` - ✅ Available (system_router)
- `/api/system/info` - ✅ Available (system_router)
- `/api/system/status` - ✅ Available (system_router)

#### **Usage Pattern:**
- Correctly implemented and widely used
- No conflicts detected

### 3. TERMINAL ENDPOINTS

#### **Actively Used by Frontend:**
- `/api/terminal/execute` (POST) - Execute commands **HIGH FREQUENCY**
- `/api/terminal/interrupt` (POST) - Interrupt execution
- `/api/terminal/kill` (POST) - Kill processes
- `/api/terminal/ws/simple/{sessionId}` (WebSocket) - Terminal sessions
- `/api/terminal/simple/sessions` (POST/GET) - Session management
- `/api/terminal/sessions/{id}` (DELETE/GET) - Session operations
- `/api/terminal/command` (POST) - Single command execution

#### **Backend Available:**
- `/api/terminal/*` - ✅ Available (terminal_router)
- WebSocket endpoints - ✅ Available (terminal_websocket)

#### **Usage Pattern:**
- Complex implementation with multiple endpoint patterns
- WebSocket integration working correctly

### 4. WORKFLOW ENDPOINTS

#### **Actively Used by Frontend:**
- `/api/workflow/workflows` (GET) - List workflows **HIGH FREQUENCY**
- `/api/workflow/workflow/{id}` (GET) - Get workflow details
- `/api/workflow/workflow/{id}/status` (GET) - Get workflow status
- `/api/workflow/workflow/{id}/approve` (POST) - Approve workflow step
- `/api/workflow/workflow/{id}` (DELETE) - Cancel workflow
- `/api/workflow/execute` (POST) - Execute workflow **HIGH FREQUENCY**
- `/api/workflow/workflow/{id}/pending_approvals` (GET) - Get pending approvals

#### **Backend Available:**
- `/api/workflow/*` - ✅ Available (workflow_router)

#### **Usage Pattern:**
- Well-implemented and consistently used
- No major conflicts detected

### 5. SETTINGS/CONFIGURATION ENDPOINTS

#### **Actively Used by Frontend:**
- `/api/settings/` (GET/POST) - **HIGH FREQUENCY**
- `/api/settings/backend` (GET/POST) - Backend settings
- `/api/settings/config` (GET/POST) - Configuration management

#### **Backend Available:**
- `/api/settings/*` - ✅ Available (settings_router)

#### **Usage Pattern:**
- Correctly implemented
- Consistent usage across components

### 6. KNOWLEDGE BASE ENDPOINTS

#### **Actively Used by Frontend:**
- `/api/knowledge_base/search` (POST) - **HIGH FREQUENCY**
- `/api/knowledge_base/add_text` (POST) - Add text content
- `/api/knowledge_base/add_url` (POST) - Add URL content
- `/api/knowledge_base/add_file` (POST) - Add file content
- `/api/knowledge_base/export` (GET) - Export knowledge
- `/api/knowledge_base/cleanup` (POST) - Cleanup knowledge
- `/api/knowledge_base/stats` (GET) - Get statistics
- `/api/knowledge_base/detailed_stats` (GET) - Detailed statistics

#### **Backend Available:**
- `/api/knowledge_base/*` - ✅ Available (knowledge_router)

#### **Usage Pattern:**
- Well-implemented across multiple components
- Consistent usage pattern

### 7. FILE MANAGEMENT ENDPOINTS

#### **Actively Used by Frontend:**
- `/api/files/list` (GET) - **HIGH FREQUENCY** (FileBrowser.vue, KnowledgeManager.vue)
- `/api/files/upload` (POST) - **HIGH FREQUENCY**
- `/api/files/download/{path}` (GET) - Download files
- `/api/files/view/{path}` (GET) - View file content
- `/api/files/delete` (DELETE) - Delete files
- `/api/files/create_directory` (POST) - Create directories
- `/api/files/stats` (GET) - File statistics

#### **Backend Available:**
- `/api/files/*` - ✅ Available (files_router)

#### **Usage Pattern:**
- Heavily used by FileBrowser and KnowledgeManager components
- Consistent implementation

### 8. LLM/AI ENDPOINTS

#### **Actively Used by Frontend:**
- `/api/llm/models` (GET) - Get available models **FREQUENT**
- `/api/llm/provider` (POST) - Set LLM provider
- `/api/llm/embedding` (POST) - Embedding configuration
- `/api/llm/embedding/models` (GET) - Embedding models
- `/api/llm/status/comprehensive` (GET) - Comprehensive status

#### **Backend Available:**
- `/api/llm/*` - ✅ Available (llm_router)

#### **Usage Pattern:**
- Used primarily in SettingsPanel component
- Good integration with backend

### 9. PROMPTS ENDPOINTS

#### **Actively Used by Frontend:**
- `/api/prompts/` (GET) - Get prompts **FREQUENT**
- `/api/prompts/{id}` (POST) - Save prompt
- `/api/prompts/{id}/revert` (POST) - Revert prompt

#### **Backend Available:**
- `/api/prompts/*` - ✅ Available (prompts_router)

#### **Usage Pattern:**
- Used in SettingsPanel for prompt management
- Consistent implementation

### 10. RESEARCH/BROWSER ENDPOINTS

#### **Actively Used by Frontend:**
- `/api/research/url` (POST) - Research URL
- `/api/research/session/action` (POST) - Session actions
- `/api/research/session/{id}/status` (GET) - Session status
- `/api/research/session/{id}/navigate` (POST) - Navigate session
- `/api/research/session/{id}` (DELETE) - Delete session
- `/api/research/browser/{id}` (GET) - Get browser info

#### **Backend Available:**
- `/api/research/*` - ✅ Available (research_browser_router)

#### **Usage Pattern:**
- Used by ResearchBrowser and PopoutChromiumBrowser components
- Complex session management

### 11. PROJECT/VALIDATION ENDPOINTS

#### **Actively Used by Frontend:**
- `/api/project/status` (GET) - Project status
- `/api/project/validate` (POST) - Validate project
- `/api/project/report` (GET) - Project report
- `/api/validation-dashboard/report` (GET) - Validation dashboard

#### **Backend Available:**
- `/api/project/*` - ❌ **MISSING** (project_state_router not properly mounted)
- `/api/validation-dashboard/*` - ✅ Available (validation_dashboard_router)

#### **Critical Issue:**
- **MAJOR PROBLEM**: PhaseStatusIndicator.vue calls `/api/project/*` endpoints that are not accessible

## MISSING BACKEND ENDPOINTS (High Priority)

### 1. Chat Management (Critical)
- `/api/chats` (GET) - List all chats
- `/api/chats/new` (POST) - Create new chat
- `/api/chats/{id}` (GET) - Get specific chat
- `/api/chats/{id}` (DELETE) - Delete specific chat
- `/api/chats/{id}/save` (POST) - Save chat messages

### 2. Project State Management (Critical)
- `/api/project/status` (GET) - Called by PhaseStatusIndicator
- `/api/project/validate` (POST) - Called by PhaseStatusIndicator
- `/api/project/report` (GET) - Called by PhaseStatusIndicator

### 3. Developer API Endpoints
- `/api/developer/config` (GET/POST) - Called by SettingsService
- `/api/developer/endpoints` (GET) - Called by SettingsService
- `/api/developer/system-info` (GET) - Called by SettingsService

## HARDCODED URL PATTERNS (High Priority Fix Needed)

Many components bypass the centralized API client and use hardcoded URLs:

### Direct fetch() calls with hardcoded localhost:8001:
1. **App.vue**: `fetch('http://localhost:8001/api/system/health')`
2. **FileBrowser.vue**: `fetch('http://localhost:8001/api/files/list')`
3. **ChatInterface.vue**: `fetch('http://localhost:8001/api/files/upload')`
4. **SettingsPanel.vue**: `fetch('http://localhost:8001/api/system/health')`
5. **KnowledgeManager.vue**: Multiple hardcoded file and knowledge endpoints
6. **ValidationDashboard.vue**: `fetch('http://localhost:8001/api/validation-dashboard/report')`

### Components using settings.backend.api_endpoint:
1. **HistoryView.vue**: Correctly uses configurable endpoint
2. **ChatManager.js**: Correctly uses configurable endpoint

## CONFLICTING ENDPOINT USAGE

### Chat Endpoints Conflict:
- **Legacy Pattern**: `/api/list_sessions`, `/api/load_session/{id}`
- **New Pattern**: `/api/chats`, `/api/chats/{id}`
- **Components**: HistoryView.vue uses legacy, ChatInterface.vue uses new pattern

### Settings Endpoint Variations:
- `/api/settings/` (trailing slash)
- `/api/settings` (no trailing slash)
- Both patterns used across components

## RECOMMENDATIONS

### Immediate Actions (Priority 1):

1. **Implement Missing Chat Endpoints**:
   ```python
   # Add to backend/api/chat.py or create backend/api/chat_management.py
   @router.get("/chats")
   @router.post("/chats/new")
   @router.get("/chats/{chat_id}")
   @router.delete("/chats/{chat_id}")
   @router.post("/chats/{chat_id}/save")
   ```

2. **Fix Project State Endpoints**:
   - Ensure project_state_router is properly mounted in app_factory.py
   - Verify endpoints are accessible at `/api/project/*`

3. **Standardize API Client Usage**:
   - Replace all hardcoded `fetch('http://localhost:8001/...)` calls
   - Use centralized ApiClient for all API calls
   - Implement proper environment variable handling

### Medium Priority Actions:

1. **Consolidate Chat Patterns**:
   - Migrate all components to use `/api/chats/*` pattern
   - Deprecate legacy `/api/list_sessions` endpoints
   - Update backend to maintain compatibility during transition

2. **Add Missing Developer Endpoints**:
   - Implement `/api/developer/*` endpoints in backend
   - Ensure SettingsService can access configuration data

3. **Standardize Endpoint Patterns**:
   - Decide on trailing slash convention for `/api/settings`
   - Update all components to use consistent patterns

### Long-term Improvements:

1. **Create API Client Wrapper Methods**:
   - Add domain-specific methods to ApiClient
   - Reduce direct endpoint URL usage in components

2. **Implement API Versioning**:
   - Add version prefixes to prevent future conflicts
   - Plan migration strategy for legacy endpoints

3. **Add API Documentation**:
   - Document all available endpoints
   - Create usage guidelines for frontend developers

## COMPONENT-SPECIFIC ISSUES

### High Usage Components:
1. **ChatInterface.vue**: Mixed patterns, hardcoded URLs
2. **FileBrowser.vue**: Hardcoded URLs, should use ApiClient
3. **SettingsPanel.vue**: Hardcoded URLs for health checks
4. **KnowledgeManager.vue**: Extensive hardcoded URL usage
5. **PhaseStatusIndicator.vue**: Calls missing `/api/project/*` endpoints

### Well-Implemented Components:
1. **WorkflowApproval.vue**: Proper ApiService usage
2. **ResearchBrowser.vue**: Consistent ApiClient usage
3. **SystemMonitor.vue**: Good ApiClient integration

## TESTING IMPLICATIONS

The audit reveals that many E2E and integration tests may fail due to:
1. Missing backend endpoints for frontend functionality
2. Hardcoded URLs that won't work in test environments
3. Inconsistent API patterns causing test complexity

**Immediate testing fixes needed:**
- Mock missing `/api/chats/*` endpoints
- Update test configurations for hardcoded URLs
- Add integration tests for project state endpoints

## CONCLUSION

This audit reveals significant technical debt in API endpoint management. The frontend has evolved faster than the backend, creating numerous missing endpoints and inconsistent usage patterns.

**Critical Path for Stability:**
1. Implement missing chat management endpoints (breaks chat functionality)
2. Fix project state endpoint mounting (breaks phase validation)
3. Replace hardcoded URLs with centralized API client usage
4. Consolidate conflicting endpoint patterns

**Risk Assessment:**
- **High Risk**: Chat functionality may be unstable due to missing endpoints
- **Medium Risk**: Phase validation broken due to missing project endpoints
- **Low Risk**: Hardcoded URLs will break in production deployment

The recommendation is to prioritize implementing missing endpoints before any major refactoring to ensure application stability.
