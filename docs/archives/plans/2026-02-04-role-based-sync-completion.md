# Role-Based Code Sync Completion Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Complete issue #779 by adding centralized role dashboard UI, schedule role targeting, and wiring up existing components.

**Architecture:** The backend is 95% complete. This plan focuses on frontend integration and one database migration for schedule role targeting.

**Tech Stack:** Vue 3, TypeScript, FastAPI, SQLAlchemy

**GitHub Issue:** #779

---

## Task 1: Add target_roles to UpdateSchedule Model

**Files:**
- Modify: `slm-server/models/database.py:UpdateSchedule`
- Modify: `slm-server/models/schemas.py:ScheduleCreate/ScheduleUpdate/ScheduleResponse`

**Step 1: Add target_roles column to UpdateSchedule**

In `slm-server/models/database.py`, add to UpdateSchedule class after target_nodes:

```python
    target_roles = Column(JSON, default=list)  # Role-based targeting (Issue #779)
```

**Step 2: Update schema classes in models/schemas.py**

Add to ScheduleCreate, ScheduleUpdate, and ScheduleResponse:

```python
    target_roles: List[str] = Field(default_factory=list)  # Role-based targeting
```

**Step 3: Update schedule run logic to respect target_roles**

In `slm-server/api/code_sync.py:run_schedule`, add role-based node filtering after line ~880:

```python
    # If target_roles specified, filter by nodes with those roles
    elif schedule.target_roles:
        from models.database import NodeRole
        role_result = await db.execute(
            select(NodeRole.node_id).where(
                NodeRole.role_name.in_(schedule.target_roles)
            ).distinct()
        )
        role_node_ids = [r[0] for r in role_result.all()]
        nodes_result = await db.execute(
            select(Node).where(
                Node.node_id.in_(role_node_ids),
                Node.code_status == CodeStatus.OUTDATED.value,
            )
        )
```

**Step 4: Commit**

```bash
git add slm-server/models/database.py slm-server/models/schemas.py slm-server/api/code_sync.py
git commit -m "feat(slm): add target_roles to UpdateSchedule (#779)"
```

---

## Task 2: Add Role Dashboard Section to CodeSyncView

**Files:**
- Modify: `slm-admin/src/views/CodeSyncView.vue`
- Modify: `slm-admin/src/composables/useCodeSync.ts`

**Step 1: Add role data to useCodeSync composable**

In `slm-admin/src/composables/useCodeSync.ts`, add:

```typescript
// Import useRoles
import { useRoles, type Role, type SyncResult } from './useRoles'

// In the composable function, add:
const rolesComposable = useRoles()

// Add to returned object:
return {
  // ... existing
  roles: rolesComposable.roles,
  fetchRoles: rolesComposable.fetchRoles,
  syncRole: rolesComposable.syncRole,
  pullFromSource: rolesComposable.pullFromSource,
}
```

**Step 2: Add Roles tab/section to CodeSyncView template**

After the Pending Updates table section, add:

```vue
    <!-- Role-Based Sync Section (Issue #779) -->
    <div class="card p-5 mb-6">
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-lg font-semibold text-gray-900">Role-Based Sync</h2>
        <button
          @click="handlePullFromSource"
          :disabled="isPulling"
          class="btn btn-secondary text-sm"
        >
          {{ isPulling ? 'Pulling...' : 'Pull from Source' }}
        </button>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        <div
          v-for="role in codeSync.roles.value"
          :key="role.name"
          class="p-4 bg-gray-50 rounded-lg border border-gray-200"
        >
          <div class="flex items-center justify-between mb-2">
            <span class="font-medium">{{ role.display_name || role.name }}</span>
            <span
              v-if="role.auto_restart"
              class="text-xs px-2 py-1 bg-blue-100 text-blue-700 rounded"
            >
              auto-restart
            </span>
          </div>
          <p class="text-sm text-gray-500 mb-3">
            {{ role.target_path }}
          </p>
          <button
            @click="handleSyncRole(role.name)"
            :disabled="syncingRole === role.name"
            class="btn btn-primary btn-sm w-full"
          >
            {{ syncingRole === role.name ? 'Syncing...' : 'Sync All Nodes' }}
          </button>
        </div>
      </div>
    </div>
```

**Step 3: Add role sync handlers to script**

```typescript
// State
const syncingRole = ref<string | null>(null)
const isPulling = ref(false)

// Methods
async function handlePullFromSource(): Promise<void> {
  isPulling.value = true
  const result = await codeSync.pullFromSource()
  isPulling.value = false

  if (result.success) {
    logger.info('Pulled from source:', result.commit)
  } else {
    logger.error('Pull failed:', result.message)
  }
}

async function handleSyncRole(roleName: string): Promise<void> {
  syncingRole.value = roleName
  const result = await codeSync.syncRole(roleName)
  syncingRole.value = null

  if (result.success) {
    logger.info('Role sync completed:', roleName, result.nodes_synced)
    await handleRefresh()
  } else {
    logger.error('Role sync failed:', result.message)
  }
}
```

**Step 4: Fetch roles on mount**

```typescript
onMounted(async () => {
  logger.info('CodeSyncView mounted')
  await Promise.all([
    codeSync.fetchStatus(),
    codeSync.fetchPendingNodes(),
    codeSync.fetchSchedules(),
    codeSync.fetchRoles(),  // Add this
  ])
})
```

**Step 5: Commit**

```bash
git add slm-admin/src/views/CodeSyncView.vue slm-admin/src/composables/useCodeSync.ts
git commit -m "feat(ui): add role-based sync section to CodeSyncView (#779)"
```

---

## Task 3: Wire RoleManagementModal into NodesView

**Files:**
- Modify: `slm-admin/src/views/NodesView.vue`

**Step 1: Import RoleManagementModal**

```typescript
import RoleManagementModal from '@/components/RoleManagementModal.vue'
```

**Step 2: Add state for modal**

```typescript
const showRoleModal = ref(false)
const selectedNodeForRoles = ref<{ id: string; hostname: string } | null>(null)

function openRoleModal(node: { node_id: string; hostname: string }): void {
  selectedNodeForRoles.value = { id: node.node_id, hostname: node.hostname }
  showRoleModal.value = true
}

function closeRoleModal(): void {
  showRoleModal.value = false
  selectedNodeForRoles.value = null
}
```

**Step 3: Add "Roles" button to node actions in template**

Find the node actions dropdown/buttons and add:

```vue
<button
  @click="openRoleModal(node)"
  class="btn btn-sm btn-secondary"
>
  Roles
</button>
```

**Step 4: Add modal component to template**

```vue
<RoleManagementModal
  v-if="showRoleModal && selectedNodeForRoles"
  :node-id="selectedNodeForRoles.id"
  :hostname="selectedNodeForRoles.hostname"
  @close="closeRoleModal"
  @saved="handleRefresh"
/>
```

**Step 5: Commit**

```bash
git add slm-admin/src/views/NodesView.vue
git commit -m "feat(ui): wire RoleManagementModal into NodesView (#779)"
```

---

## Task 4: Add Code Source Assignment UI

**Files:**
- Create: `slm-admin/src/components/CodeSourceModal.vue`
- Modify: `slm-admin/src/views/CodeSyncView.vue`
- Create: `slm-admin/src/composables/useCodeSource.ts`

**Step 1: Create useCodeSource composable**

```typescript
// slm-admin/src/composables/useCodeSource.ts
import { ref } from 'vue'
import axios from 'axios'
import { getBackendUrl } from '@/config/ssot-config'

export interface CodeSource {
  node_id: string
  hostname: string | null
  ip_address: string | null
  repo_path: string
  branch: string
  last_known_commit: string | null
  last_notified_at: string | null
  is_active: boolean
}

export function useCodeSource() {
  const codeSource = ref<CodeSource | null>(null)
  const isLoading = ref(false)
  const error = ref<string | null>(null)

  const API_BASE = getBackendUrl()

  async function fetchCodeSource(): Promise<void> {
    isLoading.value = true
    error.value = null
    try {
      const response = await axios.get<CodeSource | null>(`${API_BASE}/api/code-source`)
      codeSource.value = response.data
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string }
      error.value = err.response?.data?.detail || err.message || 'Failed to fetch'
    } finally {
      isLoading.value = false
    }
  }

  async function assignCodeSource(
    nodeId: string,
    repoPath: string = '/home/kali/Desktop/AutoBot',
    branch: string = 'main'
  ): Promise<CodeSource | null> {
    try {
      const response = await axios.post<CodeSource>(`${API_BASE}/api/code-source/assign`, {
        node_id: nodeId,
        repo_path: repoPath,
        branch,
      })
      codeSource.value = response.data
      return response.data
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string }
      error.value = err.response?.data?.detail || err.message || 'Failed to assign'
      return null
    }
  }

  async function removeCodeSource(): Promise<boolean> {
    try {
      await axios.delete(`${API_BASE}/api/code-source/assign`)
      codeSource.value = null
      return true
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string }
      error.value = err.response?.data?.detail || err.message || 'Failed to remove'
      return false
    }
  }

  return {
    codeSource,
    isLoading,
    error,
    fetchCodeSource,
    assignCodeSource,
    removeCodeSource,
  }
}
```

**Step 2: Create CodeSourceModal component**

```vue
<!-- slm-admin/src/components/CodeSourceModal.vue -->
<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { ref, onMounted } from 'vue'
import axios from 'axios'
import { getBackendUrl } from '@/config/ssot-config'

const emit = defineEmits<{
  close: []
  saved: []
}>()

interface Node {
  node_id: string
  hostname: string
  ip_address: string
}

const nodes = ref<Node[]>([])
const selectedNodeId = ref('')
const repoPath = ref('/home/kali/Desktop/AutoBot')
const branch = ref('main')
const isLoading = ref(true)
const isSaving = ref(false)
const error = ref<string | null>(null)

const API_BASE = getBackendUrl()

onMounted(async () => {
  try {
    const response = await axios.get<{ nodes: Node[] }>(`${API_BASE}/api/nodes`)
    nodes.value = response.data.nodes
  } catch {
    error.value = 'Failed to load nodes'
  } finally {
    isLoading.value = false
  }
})

async function handleAssign(): Promise<void> {
  if (!selectedNodeId.value) return

  isSaving.value = true
  error.value = null

  try {
    await axios.post(`${API_BASE}/api/code-source/assign`, {
      node_id: selectedNodeId.value,
      repo_path: repoPath.value,
      branch: branch.value,
    })
    emit('saved')
    emit('close')
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string }
    error.value = err.response?.data?.detail || err.message || 'Failed to assign'
  } finally {
    isSaving.value = false
  }
}
</script>

<template>
  <div class="fixed inset-0 bg-black/50 flex items-center justify-center z-50" @click.self="emit('close')">
    <div class="bg-white rounded-lg shadow-xl w-full max-w-md p-6">
      <h3 class="text-lg font-semibold mb-4">Assign Code Source</h3>

      <div v-if="isLoading" class="text-gray-500">Loading nodes...</div>

      <div v-else class="space-y-4">
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">Node</label>
          <select v-model="selectedNodeId" class="w-full border rounded-md p-2">
            <option value="">Select a node...</option>
            <option v-for="node in nodes" :key="node.node_id" :value="node.node_id">
              {{ node.hostname }} ({{ node.ip_address }})
            </option>
          </select>
        </div>

        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">Repository Path</label>
          <input v-model="repoPath" type="text" class="w-full border rounded-md p-2" />
        </div>

        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">Branch</label>
          <input v-model="branch" type="text" class="w-full border rounded-md p-2" />
        </div>

        <div v-if="error" class="text-red-600 text-sm">{{ error }}</div>
      </div>

      <div class="flex justify-end gap-3 mt-6">
        <button @click="emit('close')" class="btn btn-secondary">Cancel</button>
        <button
          @click="handleAssign"
          :disabled="!selectedNodeId || isSaving"
          class="btn btn-primary"
        >
          {{ isSaving ? 'Assigning...' : 'Assign' }}
        </button>
      </div>
    </div>
  </div>
</template>
```

**Step 3: Add Code Source info card to CodeSyncView**

Add after the Status Banner section:

```vue
    <!-- Code Source Card (Issue #779) -->
    <div class="card p-5 mb-6">
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-lg font-semibold text-gray-900">Code Source</h2>
        <button
          v-if="!codeSourceData"
          @click="showCodeSourceModal = true"
          class="btn btn-primary text-sm"
        >
          Configure
        </button>
      </div>

      <div v-if="codeSourceData" class="flex items-center justify-between">
        <div>
          <p class="font-medium">{{ codeSourceData.hostname || codeSourceData.node_id }}</p>
          <p class="text-sm text-gray-500">{{ codeSourceData.repo_path }} ({{ codeSourceData.branch }})</p>
          <p class="text-sm text-gray-500">
            Last commit: {{ codeSourceData.last_known_commit?.slice(0, 12) || 'Unknown' }}
          </p>
        </div>
        <button @click="handleRemoveCodeSource" class="btn btn-danger text-sm">
          Remove
        </button>
      </div>
      <div v-else class="text-gray-500">
        No code source configured. Assign a node that has git access to the repository.
      </div>
    </div>

    <CodeSourceModal
      v-if="showCodeSourceModal"
      @close="showCodeSourceModal = false"
      @saved="handleCodeSourceSaved"
    />
```

**Step 4: Add state and handlers**

```typescript
import CodeSourceModal from '@/components/CodeSourceModal.vue'
import { useCodeSource, type CodeSource } from '@/composables/useCodeSource'

const codeSourceComposable = useCodeSource()
const codeSourceData = codeSourceComposable.codeSource
const showCodeSourceModal = ref(false)

async function handleCodeSourceSaved(): Promise<void> {
  await codeSourceComposable.fetchCodeSource()
}

async function handleRemoveCodeSource(): Promise<void> {
  if (!confirm('Remove code source assignment?')) return
  await codeSourceComposable.removeCodeSource()
}

// In onMounted:
await codeSourceComposable.fetchCodeSource()
```

**Step 5: Commit**

```bash
git add slm-admin/src/components/CodeSourceModal.vue slm-admin/src/composables/useCodeSource.ts slm-admin/src/views/CodeSyncView.vue
git commit -m "feat(ui): add code source assignment UI (#779)"
```

---

## Task 5: Update ScheduleModal with Role Targeting

**Files:**
- Modify: `slm-admin/src/components/ScheduleModal.vue`

**Step 1: Add roles multiselect to ScheduleModal**

Add target type option for "roles" and a multi-select for role selection:

```vue
<div class="form-group">
  <label>Target Type</label>
  <select v-model="formData.target_type">
    <option value="all">All Outdated Nodes</option>
    <option value="specific">Specific Nodes</option>
    <option value="roles">By Role</option>
  </select>
</div>

<div v-if="formData.target_type === 'roles'" class="form-group">
  <label>Target Roles</label>
  <div class="checkbox-group">
    <label v-for="role in availableRoles" :key="role.name" class="checkbox-label">
      <input
        type="checkbox"
        :value="role.name"
        v-model="formData.target_roles"
      />
      {{ role.display_name || role.name }}
    </label>
  </div>
</div>
```

**Step 2: Update form data and submission**

```typescript
const formData = ref({
  // existing fields...
  target_roles: [] as string[],
})
```

**Step 3: Commit**

```bash
git add slm-admin/src/components/ScheduleModal.vue
git commit -m "feat(ui): add role targeting to schedule modal (#779)"
```

---

## Task 6: Sync Frontend to VM and Test

**Step 1: Sync to VM**

```bash
./scripts/utilities/sync-to-vm.sh frontend slm-admin/src/ /home/autobot/AutoBot/slm-admin/src/
```

**Step 2: Verify in browser**

1. Navigate to Code Sync page - verify role cards appear
2. Click "Pull from Source" - verify it works
3. Click "Sync All Nodes" on a role - verify sync initiates
4. Navigate to Nodes page - verify "Roles" button appears
5. Click Roles button - verify modal opens with role info
6. Create a schedule with role targeting - verify it saves

**Step 3: Final commit with issue closing**

```bash
git add -A
git commit -m "feat(slm): complete role-based code sync implementation (#779)

- Add target_roles to UpdateSchedule for role-based scheduling
- Add role-based sync section to CodeSyncView dashboard
- Wire RoleManagementModal into NodesView
- Add Code Source assignment UI
- Update ScheduleModal with role targeting option

Closes #779"
```

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Add target_roles to schedules | database.py, schemas.py, code_sync.py |
| 2 | Role dashboard in CodeSyncView | CodeSyncView.vue, useCodeSync.ts |
| 3 | Wire RoleManagementModal | NodesView.vue |
| 4 | Code Source assignment UI | CodeSourceModal.vue, useCodeSource.ts |
| 5 | Schedule role targeting UI | ScheduleModal.vue |
| 6 | Test and final commit | - |

**Estimated tasks:** 6 tasks, ~20 steps total
