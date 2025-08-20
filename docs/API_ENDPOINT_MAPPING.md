# API Endpoint Mapping - Frontend vs Backend

**Generated:** August 20, 2025
**Status:** Critical mismatches found

## 🔴 CRITICAL MISMATCHES

### Knowledge Base Endpoints
| Frontend Expected | Backend Actual | Status |
|------------------|----------------|--------|
| POST `/api/knowledge_base/search` | POST `/api/knowledge/search` | ❌ MISMATCH |
| POST `/api/knowledge_base/add_text` | POST `/api/knowledge/add_text` | ❌ MISMATCH |
| POST `/api/knowledge_base/add_url` | POST `/api/knowledge/add_url` | ❌ MISMATCH |
| POST `/api/knowledge_base/add_file` | POST `/api/knowledge/add_file` | ❌ MISMATCH |
| GET `/api/knowledge_base/export` | GET `/api/knowledge/export` | ❌ MISMATCH |
| POST `/api/knowledge_base/cleanup` | POST `/api/knowledge/cleanup` | ❌ MISMATCH |
| GET `/api/knowledge_base/stats` | GET `/api/knowledge/stats` | ❌ MISMATCH |
| GET `/api/knowledge_base/detailed_stats` | GET `/api/knowledge/detailed_stats` | ❌ MISMATCH |
| GET `/api/knowledge_base/entries` | GET `/api/knowledge/entries` | ❌ MISMATCH |
| POST `/api/knowledge_base/entries` | POST `/api/knowledge/entries` | ❌ MISMATCH |
| PUT `/api/knowledge_base/entries/{id}` | PUT `/api/knowledge/entries/{id}` | ❌ MISMATCH |
| DELETE `/api/knowledge_base/entries/{id}` | DELETE `/api/knowledge/entries/{id}` | ❌ MISMATCH |
| GET `/api/knowledge_base/entries/{id}` | GET `/api/knowledge/entries/{id}` | ❌ MISMATCH |
| POST `/api/knowledge_base/entries/{id}/crawl` | POST `/api/knowledge/entries/{id}/crawl` | ❌ MISMATCH |
| GET `/api/knowledge_base/categories` | GET `/api/knowledge/categories` | ❌ MISMATCH |

## 🟡 Additional API Endpoints to Verify

### Chat Endpoints
| Frontend Expected | Backend Status |
|------------------|----------------|
| POST `/api/chat` | ✅ EXISTS |
| GET `/api/chat/health` | ✅ EXISTS |
| GET `/api/chats` | ✅ EXISTS |
| GET `/api/chats/{chat_id}` | ✅ EXISTS |
| DELETE `/api/chats/{chat_id}` | ✅ EXISTS |

### System Endpoints
| Frontend Expected | Backend Status |
|------------------|----------------|
| GET `/api/system/health` | ✅ EXISTS |
| GET `/api/system/info` | ✅ EXISTS |
| GET `/api/system/metrics` | ✅ EXISTS |

### Settings Endpoints
| Frontend Expected | Backend Status |
|------------------|----------------|
| GET `/api/settings/backend` | ✅ EXISTS |
| POST `/api/settings/backend` | ✅ EXISTS |

### Terminal Endpoints
| Frontend Expected | Backend Status |
|------------------|----------------|
| POST `/api/terminal/execute` | ✅ EXISTS |
| GET `/api/terminal/sessions/{id}` | ✅ EXISTS |
| DELETE `/api/terminal/sessions/{id}` | ✅ EXISTS |

### Files Endpoints
| Frontend Expected | Backend Status |
|------------------|----------------|
| GET `/api/files/list` | ✅ EXISTS |
| POST `/api/files/upload` | ✅ EXISTS |
| GET `/api/files/download` | ✅ EXISTS |
| DELETE `/api/files/delete` | ✅ EXISTS |

### Workflow Endpoints
| Frontend Expected | Backend Status |
|------------------|----------------|
| GET `/api/workflows` | ✅ EXISTS |
| POST `/api/workflows` | ✅ EXISTS |
| GET `/api/workflows/{id}` | ✅ EXISTS |
| PUT `/api/workflows/{id}` | ✅ EXISTS |
| DELETE `/api/workflows/{id}` | ✅ EXISTS |
| POST `/api/workflows/{id}/execute` | ✅ EXISTS |

### WebSocket Endpoints
| Frontend Expected | Backend Status |
|------------------|----------------|
| WS `/ws/chat` | ✅ EXISTS |
| WS `/ws/terminal` | ✅ EXISTS |
| WS `/ws/logs` | ✅ EXISTS |
| WS `/ws/monitoring` | ✅ EXISTS |

## 🔧 IMMEDIATE FIX REQUIRED

The knowledge base endpoints have a critical naming mismatch. The frontend expects `/api/knowledge_base/*` but the backend provides `/api/knowledge/*`.

### Option 1: Update Frontend (Recommended)
Change all `/api/knowledge_base/` references to `/api/knowledge/` in:
- `/autobot-vue/src/utils/ApiClient.js`
- `/autobot-vue/src/components/KnowledgeManager.vue`
- Any other components using knowledge base APIs

### Option 2: Add Backend Aliases
Add route aliases in the backend to support both paths:
```python
# In backend/api/knowledge.py
@router.post("/search")
@router.post("_base/search")  # Alias for compatibility
async def search_knowledge(request: dict):
    ...
```

### Option 3: Nginx Rewrite
Add nginx rewrite rules to map the old paths to new:
```nginx
location ~ ^/api/knowledge_base/(.*)$ {
    rewrite ^/api/knowledge_base/(.*)$ /api/knowledge/$1 last;
}
```

## 📋 Validation Checklist

- [ ] Fix all knowledge base endpoint mismatches
- [ ] Test each endpoint with frontend
- [ ] Update API documentation
- [ ] Add integration tests
- [ ] Monitor for 404 errors in production

## 🚨 Impact

These mismatches are causing:
- Network timeouts and errors
- Failed knowledge base operations
- Poor user experience
- RUM dashboard showing disconnected WebSocket

**Priority: CRITICAL - Fix immediately**
