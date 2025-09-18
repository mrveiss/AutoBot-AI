# 🔧 Hardcoded Values Consolidation Plan

**Generated:** August 20, 2025
**Analysis Source:** NPU Code Search Agent + Redis Indexing

## 🎯 Critical Issues Found

### 200+ Hardcoded Value Instances
- **Backend URLs**: 180+ occurrences of `http://localhost:8001`
- **Frontend URLs**: 65+ occurrences of `http://localhost:5173`
- **Redis URLs**: 25+ occurrences of `localhost:6379`
- **LLM URLs**: 30+ occurrences of `http://localhost:11434`
- **WebSocket URLs**: 15+ occurrences of `ws://localhost:8001/ws`

## 🔴 Immediate Action Items

### 1. Frontend Configuration Centralization
**Problem**: Multiple API clients, hardcoded URLs
**Solution**: Consolidate to single configuration source

```javascript
// Create: autobot-vue/src/config/environment.js
export const API_CONFIG = {
  BASE_URL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8001',
  WS_URL: import.meta.env.VITE_WS_BASE_URL || 'ws://localhost:8001/ws',
  TIMEOUT: parseInt(import.meta.env.VITE_API_TIMEOUT || '30000')
};
```

### 2. Backend Environment Variables
**Problem**: Hardcoded service URLs throughout backend
**Solution**: Update config.py to use environment variables

```python
# Update: src/config.py
API_BASE_URL = os.getenv('AUTOBOT_API_BASE_URL', 'http://localhost:8001')
REDIS_URL = os.getenv('AUTOBOT_REDIS_URL', 'redis://localhost:6379')
OLLAMA_URL = os.getenv('AUTOBOT_OLLAMA_URL', 'http://localhost:11434')
```

### 3. API Endpoint Deduplication
**Problem**: 4+ duplicate health endpoints
**Current**:
- `/api/system/health`
- `/api/chat/health`
- `/api/llm/health`
- `/api/terminal/health`

**Solution**: Consolidate to single comprehensive endpoint

## 🛠️ Implementation Strategy

### Phase 1: Critical Fixes (2 hours)
1. **Fix frontend hardcoded URLs** in KnowledgeManager.vue, ChatInterface.vue, SettingsPanel.vue
2. **Create centralized API configuration** for frontend
3. **Update environment variable loading** in backend config

### Phase 2: Backend Consolidation (3 hours)
1. **Merge duplicate health endpoints**
2. **Update all API clients** to use centralized config
3. **Fix script hardcoded values**

### Phase 3: Testing & Validation (1 hour)
1. **Test with different environment configurations**
2. **Validate all API endpoints work with configurable URLs**
3. **Update deployment documentation**

## 📋 Environment Variables Required

```bash
# Frontend (.env)
VITE_API_BASE_URL=http://localhost:8001
VITE_WS_BASE_URL=ws://localhost:8001/ws
VITE_API_TIMEOUT=30000

# Backend (.env)
AUTOBOT_API_BASE_URL=http://localhost:8001
AUTOBOT_REDIS_URL=redis://localhost:6379
AUTOBOT_OLLAMA_URL=http://localhost:11434
AUTOBOT_API_TIMEOUT=30000
AUTOBOT_LOG_LEVEL=INFO
```

## 🎯 Success Metrics

- [ ] Zero hardcoded URLs in production code
- [ ] Single API client implementation in frontend
- [ ] All services configurable via environment variables
- [ ] Consolidated health endpoint returning all service status
- [ ] Documentation updated with configuration options

## 📊 Impact Assessment

**Before**: 200+ hardcoded values, 5 API clients, 4+ duplicate endpoints
**After**: 0 hardcoded values, 1 API client, 1 comprehensive health endpoint

**Maintenance Reduction**: ~75% less configuration maintenance
**Deployment Flexibility**: Full environment configurability
**Error Reduction**: Centralized configuration reduces mismatches

This consolidation plan addresses the root cause of the API timeout issues by eliminating hardcoded URLs and providing proper configuration management.
