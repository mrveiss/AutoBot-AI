# Phase 4: Service Discovery Migration & Agent Management UI

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Migrate existing code to use discover_service()/discoverService() functions and create frontend UI for agent management.

**Dependencies:** Phase 3 complete (ServiceDiscoveryCache, discover_service(), discoverService(), useServiceDiscovery)

**Architecture:** Backend uses discover_service() for all service lookups. Frontend uses discoverService() via useServiceDiscovery composable. Agent management UI in SLM Admin.

---

## Task 1: Update backend/services/slm_client.py to Bootstrap via Environment

**Files:**
- Modify: `backend/services/slm_client.py`

**Problem:**
Line 38 has `DEFAULT_SLM_URL = "http://172.16.168.19:8000"` - hardcoded SLM URL.

**Solution:**
The SLM URL is special - it's the bootstrap service that can't use discover_service() (chicken-and-egg). Use environment variable with no hardcoded fallback.

**Step 1: Update DEFAULT_SLM_URL**

Change:
```python
DEFAULT_SLM_URL = "http://172.16.168.19:8000"
```

To:
```python
import os
# SLM URL from environment - no hardcoded fallback (SSOT requirement)
DEFAULT_SLM_URL = os.getenv("SLM_URL")
if not DEFAULT_SLM_URL:
    logger.warning("SLM_URL not set, SLM client will be unavailable")
```

**Step 2: Commit**
```bash
git add backend/services/slm_client.py
git commit -m "refactor(slm-client): remove hardcoded SLM URL (#760)"
```

---

## Task 2: Update Backend Provider Health to Use SSOT Config

**Files:**
- Modify: `backend/services/provider_health/providers.py`

**Problem:**
Lines 120, 214 have hardcoded cloud provider URLs:
- `self.base_url = "https://api.openai.com/v1"`
- `self.base_url = "https://api.anthropic.com/v1"`

**Solution:**
Import from SSOT config which already defines these.

**Step 1: Add import**
```python
from src.config.ssot_config import config
```

**Step 2: Update OpenAI provider (around line 120)**
```python
self.base_url = config.get_service_url("openai") or "https://api.openai.com/v1"
```

**Step 3: Update Anthropic provider (around line 214)**
```python
self.base_url = config.get_service_url("anthropic") or "https://api.anthropic.com/v1"
```

**Note:** Keep fallback for cloud providers since they're external APIs with stable URLs.

**Step 4: Commit**
```bash
git add backend/services/provider_health/providers.py
git commit -m "refactor(provider-health): use SSOT config for cloud URLs (#760)"
```

---

## Task 3: Update modern_ai_integration.py Cloud Endpoints

**Files:**
- Modify: `src/modern_ai_integration.py`

**Problem:**
Lines 843, 863 have hardcoded API endpoints:
- `api_endpoint="https://api.openai.com/v1/chat/completions"`
- `api_endpoint="https://api.anthropic.com/v1/messages"`

**Solution:**
Use SSOT config for base URLs.

**Step 1: Find and update OpenAI endpoint**
```python
from src.config.ssot_config import config
# ...
openai_base = config.get_service_url("openai") or "https://api.openai.com/v1"
api_endpoint=f"{openai_base}/chat/completions"
```

**Step 2: Find and update Anthropic endpoint**
```python
anthropic_base = config.get_service_url("anthropic") or "https://api.anthropic.com/v1"
api_endpoint=f"{anthropic_base}/messages"
```

**Step 3: Commit**
```bash
git add src/modern_ai_integration.py
git commit -m "refactor(ai-integration): use SSOT config for cloud URLs (#760)"
```

---

## Task 4: Update slm-admin SSOT Config to Use Environment Variables

**Files:**
- Modify: `slm-admin/src/config/ssot-config.ts`

**Problem:**
Lines 48-54 have hardcoded VM IPs without environment variable fallback.

**Solution:**
Add environment variable support using Vite's import.meta.env.

**Step 1: Update VM config to use env vars**
```typescript
function getEnv(key: string, defaultValue: string): string {
  const value = (import.meta as any).env?.[key];
  return value || defaultValue;
}

vm: {
  main: getEnv('VITE_BACKEND_HOST', '172.16.168.20'),
  frontend: getEnv('VITE_FRONTEND_HOST', '172.16.168.21'),
  npu: getEnv('VITE_NPU_WORKER_HOST', '172.16.168.22'),
  redis: getEnv('VITE_REDIS_HOST', '172.16.168.23'),
  ai: getEnv('VITE_AI_STACK_HOST', '172.16.168.24'),
  browser: getEnv('VITE_BROWSER_HOST', '172.16.168.25'),
  slm: getEnv('VITE_SLM_HOST', '172.16.168.19'),
},
```

**Step 2: Commit**
```bash
git add slm-admin/src/config/ssot-config.ts
git commit -m "refactor(slm-admin): use env vars for VM IPs (#760)"
```

---

## Task 5: Create Agent Management Vue Component

**Files:**
- Create: `slm-admin/src/components/AgentManager.vue`

**Description:**
Create a Vue component for managing agents in the SLM Admin interface.

**Step 1: Create component structure**
```vue
<script setup lang="ts">
// Agent management component for SLM Admin
// Issue #760 Phase 4
</script>

<template>
  <div class="agent-manager">
    <h2>Agent Registry</h2>
    <!-- Agent list -->
    <!-- Agent detail/edit panel -->
  </div>
</template>
```

**Step 2: Implement agent list with CRUD operations**
- GET /api/agents - list all
- GET /api/agents/{id} - detail
- PUT /api/agents/{id} - update
- POST /api/agents - create

**Step 3: Add LLM configuration editing**
- Provider selection (ollama, openai, anthropic)
- Model selection
- Endpoint configuration
- Temperature, timeout settings

**Step 4: Commit**
```bash
git add slm-admin/src/components/AgentManager.vue
git commit -m "feat(slm-admin): add AgentManager component (#760)"
```

---

## Task 6: Add Agent Management Route to SLM Admin

**Files:**
- Modify: `slm-admin/src/router/index.ts`
- Modify: `slm-admin/src/views/` (add AgentsView.vue if needed)

**Step 1: Add route**
```typescript
{
  path: '/agents',
  name: 'agents',
  component: () => import('../views/AgentsView.vue'),
  meta: { title: 'Agent Management' }
}
```

**Step 2: Add navigation link**

**Step 3: Commit**
```bash
git add slm-admin/src/router/index.ts slm-admin/src/views/AgentsView.vue
git commit -m "feat(slm-admin): add agents route (#760)"
```

---

## Task 7: Update GitHub Issue with Phase 4 Progress

**Step 1: Add progress comment**
```bash
gh issue comment 760 --body "## Phase 4 Implementation Progress

### Completed Tasks:
- [x] Removed hardcoded SLM URL from slm_client.py
- [x] Updated provider_health to use SSOT config
- [x] Updated modern_ai_integration.py cloud endpoints
- [x] Added env var support to slm-admin SSOT config
- [x] Created AgentManager Vue component
- [x] Added agents route to SLM Admin

### Migration Status:
- Backend: discover_service() integrated
- Frontend: discoverService() available via useServiceDiscovery
- SLM Admin: Agent management UI added

### Next Steps:
- [ ] Integration testing
- [ ] Remove deprecated local config after stabilization
- [ ] Documentation updates"
```

---

## Summary

Phase 4 delivers:

1. **Backend Migration**
   - SLM client uses environment-based URL (no hardcode)
   - Provider health uses SSOT config for cloud APIs
   - AI integration uses SSOT config endpoints

2. **Frontend Migration**
   - slm-admin uses environment variables
   - Agent management UI component

3. **Agent Management UI**
   - List agents with status
   - Edit agent LLM configuration
   - CRUD operations via SLM API
