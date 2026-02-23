<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * RolesView - Role Registry Management (Issue #841, #1129)
 *
 * CRUD interface for role definitions used across the fleet.
 * Phase 2/4 of #1129: adds required/degraded_without/ansible_playbook fields,
 * fleet health indicator, and role migration dialog.
 */

import { ref, computed, onMounted } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('RolesView')
const authStore = useAuthStore()

// Types
interface RoleDefinition {
  name: string
  display_name: string | null
  sync_type: string | null
  source_paths: string[]
  target_path: string
  systemd_service: string | null
  auto_restart: boolean
  health_check_port: number | null
  health_check_path: string | null
  pre_sync_cmd: string | null
  post_sync_cmd: string | null
  required: boolean
  degraded_without: string[]
  ansible_playbook: string | null
}

interface RoleFormData {
  name: string
  display_name: string
  sync_type: string
  source_paths: string
  target_path: string
  systemd_service: string
  auto_restart: boolean
  health_check_port: string
  health_check_path: string
  pre_sync_cmd: string
  post_sync_cmd: string
  required: boolean
  ansible_playbook: string
}

interface FleetHealth {
  health: 'healthy' | 'degraded' | 'critical'
  required_down: string[]
  optional_down: string[]
  detail: string
}

interface NodeSummary {
  node_id: string
  hostname: string
  ip_address: string
  status: string
}

// State
const roles = ref<RoleDefinition[]>([])
const isLoading = ref(false)
const showForm = ref(false)
const editingRole = ref<string | null>(null)
const errorMessage = ref<string | null>(null)
const successMessage = ref<string | null>(null)

// Fleet health
const fleetHealth = ref<FleetHealth | null>(null)
const isLoadingHealth = ref(false)

// Migration dialog
const showMigrateDialog = ref(false)
const migratingRole = ref<RoleDefinition | null>(null)
const targetNodeId = ref('')
const migrateLoading = ref(false)
const migrateOutput = ref<string | null>(null)
const nodes = ref<NodeSummary[]>([])

const formData = ref<RoleFormData>({
  name: '', display_name: '', sync_type: 'component',
  source_paths: '', target_path: '/opt/autobot',
  systemd_service: '', auto_restart: false,
  health_check_port: '', health_check_path: '',
  pre_sync_cmd: '', post_sync_cmd: '',
  required: false, ansible_playbook: '',
})

// Computed
const formTitle = computed(() => editingRole.value ? `Edit Role: ${editingRole.value}` : 'Create Role')
const filteredRoles = computed(() => roles.value)
const healthClass = computed(() => {
  if (!fleetHealth.value) return 'bg-gray-100 text-gray-600'
  return {
    healthy: 'bg-green-100 text-green-700',
    degraded: 'bg-yellow-100 text-yellow-700',
    critical: 'bg-red-100 text-red-700',
  }[fleetHealth.value.health] ?? 'bg-gray-100 text-gray-600'
})

// API helper
async function apiFetch<T>(path: string, options?: RequestInit): Promise<T | null> {
  try {
    const response = await fetch(`${authStore.getApiUrl()}${path}`, {
      ...options,
      headers: { 'Content-Type': 'application/json', ...authStore.getAuthHeaders(), ...options?.headers },
    })
    if (!response.ok) {
      const body = await response.json().catch(() => ({}))
      throw new Error(body.detail || `HTTP ${response.status}`)
    }
    return await response.json()
  } catch (err) {
    errorMessage.value = `Request failed: ${err instanceof Error ? err.message : 'Unknown error'}`
    logger.error('API error:', err)
    return null
  }
}

// Actions
async function fetchRoles(): Promise<void> {
  isLoading.value = true
  errorMessage.value = null
  const result = await apiFetch<RoleDefinition[]>('/api/roles')
  if (result) roles.value = result
  isLoading.value = false
}

async function fetchFleetHealth(): Promise<void> {
  isLoadingHealth.value = true
  const result = await apiFetch<FleetHealth>('/api/roles/fleet-health')
  if (result) fleetHealth.value = result
  isLoadingHealth.value = false
}

async function fetchNodes(): Promise<void> {
  const result = await apiFetch<NodeSummary[]>('/api/nodes')
  if (result) nodes.value = result
}

function openCreateForm(): void {
  editingRole.value = null
  formData.value = {
    name: '', display_name: '', sync_type: 'component',
    source_paths: '', target_path: '/opt/autobot',
    systemd_service: '', auto_restart: false,
    health_check_port: '', health_check_path: '',
    pre_sync_cmd: '', post_sync_cmd: '',
    required: false, ansible_playbook: '',
  }
  showForm.value = true
}

function openEditForm(role: RoleDefinition): void {
  editingRole.value = role.name
  formData.value = {
    name: role.name,
    display_name: role.display_name || '',
    sync_type: role.sync_type || 'component',
    source_paths: (role.source_paths || []).join(', '),
    target_path: role.target_path,
    systemd_service: role.systemd_service || '',
    auto_restart: role.auto_restart,
    health_check_port: role.health_check_port?.toString() || '',
    health_check_path: role.health_check_path || '',
    pre_sync_cmd: role.pre_sync_cmd || '',
    post_sync_cmd: role.post_sync_cmd || '',
    required: role.required,
    ansible_playbook: role.ansible_playbook || '',
  }
  showForm.value = true
}

function buildPayload(): Record<string, unknown> {
  const f = formData.value
  return {
    name: f.name,
    display_name: f.display_name || null,
    sync_type: f.sync_type,
    source_paths: f.source_paths ? f.source_paths.split(',').map(s => s.trim()).filter(Boolean) : [],
    target_path: f.target_path,
    systemd_service: f.systemd_service || null,
    auto_restart: f.auto_restart,
    health_check_port: f.health_check_port ? parseInt(f.health_check_port) : null,
    health_check_path: f.health_check_path || null,
    pre_sync_cmd: f.pre_sync_cmd || null,
    post_sync_cmd: f.post_sync_cmd || null,
    required: f.required,
    ansible_playbook: f.ansible_playbook || null,
  }
}

async function saveRole(): Promise<void> {
  errorMessage.value = null
  const payload = buildPayload()

  if (editingRole.value) {
    const result = await apiFetch<RoleDefinition>(
      `/api/roles/${editingRole.value}`,
      { method: 'PUT', body: JSON.stringify(payload) }
    )
    if (result) {
      successMessage.value = `Role "${result.name}" updated`
      showForm.value = false
      await fetchRoles()
      setTimeout(() => { successMessage.value = null }, 3000)
    }
  } else {
    const result = await apiFetch<RoleDefinition>(
      '/api/roles',
      { method: 'POST', body: JSON.stringify(payload) }
    )
    if (result) {
      successMessage.value = `Role "${result.name}" created`
      showForm.value = false
      await fetchRoles()
      setTimeout(() => { successMessage.value = null }, 3000)
    }
  }
}

async function deleteRole(roleName: string): Promise<void> {
  if (!confirm(`Delete role "${roleName}"? This cannot be undone.`)) return
  const result = await apiFetch<{ message: string }>(
    `/api/roles/${roleName}`,
    { method: 'DELETE' }
  )
  if (result) {
    successMessage.value = result.message
    await fetchRoles()
    setTimeout(() => { successMessage.value = null }, 3000)
  }
}

function openMigrateDialog(role: RoleDefinition): void {
  migratingRole.value = role
  targetNodeId.value = ''
  migrateOutput.value = null
  showMigrateDialog.value = true
  fetchNodes()
}

async function executeMigrate(): Promise<void> {
  if (!migratingRole.value || !targetNodeId.value) return
  migrateLoading.value = true
  migrateOutput.value = null
  errorMessage.value = null

  const result = await apiFetch<{ success: boolean; output: string; playbook: string }>(
    `/api/roles/${migratingRole.value.name}/migrate`,
    { method: 'POST', body: JSON.stringify({ target_node_id: targetNodeId.value }) }
  )

  migrateLoading.value = false
  if (result) {
    migrateOutput.value = result.output
    if (result.success) {
      successMessage.value = `Role "${migratingRole.value.name}" migrated to ${targetNodeId.value}`
    } else {
      errorMessage.value = `Migration failed — see output below`
    }
  }
}

// Lifecycle
onMounted(() => {
  fetchRoles()
  fetchFleetHealth()
})
</script>

<template>
  <div class="p-6 max-w-7xl mx-auto">
    <!-- Header -->
    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-2xl font-bold text-gray-900">Role Registry</h1>
        <p class="text-sm text-gray-500 mt-1">Manage role definitions for fleet nodes</p>
      </div>
      <div class="flex items-center gap-2">
        <!-- Fleet health badge -->
        <span v-if="fleetHealth" :class="['px-3 py-1 rounded-full text-xs font-medium capitalize', healthClass]">
          {{ fleetHealth.health }}
          <span v-if="fleetHealth.required_down.length"> — {{ fleetHealth.required_down.length }} critical</span>
        </span>
        <button @click="fetchRoles(); fetchFleetHealth()" :disabled="isLoading"
          class="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50">
          {{ isLoading ? 'Loading...' : 'Refresh' }}
        </button>
        <button @click="openCreateForm"
          class="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">
          Create Role
        </button>
      </div>
    </div>

    <!-- Fleet health detail (degraded/critical) -->
    <div v-if="fleetHealth && fleetHealth.health !== 'healthy'" class="mb-4 p-3 rounded-lg border text-sm"
      :class="fleetHealth.health === 'critical' ? 'bg-red-50 border-red-200 text-red-700' : 'bg-yellow-50 border-yellow-200 text-yellow-700'">
      {{ fleetHealth.detail }}
    </div>

    <!-- Alerts -->
    <div v-if="errorMessage" class="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
      {{ errorMessage }}
      <button @click="errorMessage = null" class="ml-2 underline">Dismiss</button>
    </div>
    <div v-if="successMessage" class="mb-4 p-3 bg-green-50 border border-green-200 rounded-lg text-green-700 text-sm">
      {{ successMessage }}
    </div>

    <!-- Role Form (Create/Edit) -->
    <div v-if="showForm" class="bg-white rounded-lg border mb-6">
      <div class="px-4 py-3 bg-gray-50 border-b flex items-center justify-between">
        <h2 class="font-medium text-gray-900">{{ formTitle }}</h2>
        <button @click="showForm = false" class="text-gray-400 hover:text-gray-600">&times;</button>
      </div>
      <form @submit.prevent="saveRole" class="p-4 space-y-4">
        <div class="grid grid-cols-2 gap-4">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Name *</label>
            <input v-model="formData.name" :disabled="!!editingRole" required
              class="w-full px-3 py-2 border rounded-lg text-sm disabled:bg-gray-100" placeholder="e.g. redis-server" />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Display Name</label>
            <input v-model="formData.display_name"
              class="w-full px-3 py-2 border rounded-lg text-sm" placeholder="e.g. Redis Server" />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Sync Type</label>
            <select v-model="formData.sync_type" class="w-full px-3 py-2 border rounded-lg text-sm">
              <option value="component">Component</option>
              <option value="full">Full</option>
              <option value="config">Config Only</option>
            </select>
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Target Path *</label>
            <input v-model="formData.target_path" required
              class="w-full px-3 py-2 border rounded-lg text-sm" placeholder="/opt/autobot" />
          </div>
          <div class="col-span-2">
            <label class="block text-sm font-medium text-gray-700 mb-1">Source Paths (comma-separated)</label>
            <input v-model="formData.source_paths"
              class="w-full px-3 py-2 border rounded-lg text-sm" placeholder="autobot-slm-backend/, autobot-shared/" />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Systemd Service</label>
            <input v-model="formData.systemd_service"
              class="w-full px-3 py-2 border rounded-lg text-sm" placeholder="autobot-slm.service" />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Ansible Playbook</label>
            <input v-model="formData.ansible_playbook"
              class="w-full px-3 py-2 border rounded-lg text-sm" placeholder="deploy-backend.yml" />
          </div>
          <div class="flex items-center gap-4 pt-6">
            <label class="flex items-center gap-2 text-sm text-gray-700">
              <input type="checkbox" v-model="formData.auto_restart" class="rounded" />
              Auto Restart on Deploy
            </label>
            <label class="flex items-center gap-2 text-sm text-gray-700">
              <input type="checkbox" v-model="formData.required" class="rounded" />
              Required Role
            </label>
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Health Check Port</label>
            <input v-model="formData.health_check_port" type="number"
              class="w-full px-3 py-2 border rounded-lg text-sm" placeholder="8000" />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Health Check Path</label>
            <input v-model="formData.health_check_path"
              class="w-full px-3 py-2 border rounded-lg text-sm" placeholder="/health" />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Pre-sync Command</label>
            <input v-model="formData.pre_sync_cmd"
              class="w-full px-3 py-2 border rounded-lg text-sm" placeholder="systemctl stop autobot-slm" />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Post-sync Command</label>
            <input v-model="formData.post_sync_cmd"
              class="w-full px-3 py-2 border rounded-lg text-sm" placeholder="systemctl restart autobot-slm" />
          </div>
        </div>
        <div class="flex gap-2 pt-2">
          <button type="submit" class="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm">
            {{ editingRole ? 'Update' : 'Create' }}
          </button>
          <button type="button" @click="showForm = false"
            class="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 text-sm">Cancel</button>
        </div>
      </form>
    </div>

    <!-- Roles Table -->
    <div class="bg-white rounded-lg border">
      <div class="px-4 py-3 bg-gray-50 border-b">
        <h2 class="font-medium text-gray-900">Registered Roles ({{ filteredRoles.length }})</h2>
      </div>
      <table class="w-full">
        <thead class="bg-gray-50">
          <tr>
            <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Name</th>
            <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Sync Type</th>
            <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Target</th>
            <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Service</th>
            <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Health</th>
            <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Actions</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-200">
          <tr v-for="role in filteredRoles" :key="role.name" class="hover:bg-gray-50">
            <td class="px-4 py-3">
              <div class="flex items-center gap-2">
                <p class="text-sm font-medium text-gray-900">{{ role.display_name || role.name }}</p>
                <span v-if="role.required"
                  class="px-1.5 py-0.5 text-xs rounded bg-red-100 text-red-700 font-medium">Required</span>
              </div>
              <p v-if="role.display_name" class="text-xs text-gray-500">{{ role.name }}</p>
            </td>
            <td class="px-4 py-3">
              <span class="px-2 py-1 text-xs rounded-full bg-blue-100 text-blue-700">{{ role.sync_type || 'component' }}</span>
            </td>
            <td class="px-4 py-3 text-sm text-gray-600 font-mono">{{ role.target_path }}</td>
            <td class="px-4 py-3 text-sm text-gray-600">{{ role.systemd_service || '-' }}</td>
            <td class="px-4 py-3 text-sm text-gray-600">
              <span v-if="role.health_check_port">:{{ role.health_check_port }}{{ role.health_check_path || '' }}</span>
              <span v-else class="text-gray-400">-</span>
            </td>
            <td class="px-4 py-3 text-right space-x-1">
              <button @click="openEditForm(role)"
                class="px-2 py-1 text-xs bg-gray-100 text-gray-700 rounded hover:bg-gray-200">Edit</button>
              <button v-if="role.ansible_playbook" @click="openMigrateDialog(role)"
                class="px-2 py-1 text-xs bg-purple-100 text-purple-700 rounded hover:bg-purple-200">Migrate</button>
              <button @click="deleteRole(role.name)"
                class="px-2 py-1 text-xs bg-red-100 text-red-700 rounded hover:bg-red-200">Delete</button>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="!filteredRoles.length && !isLoading" class="p-8 text-center text-gray-500">
        No roles defined. Click "Create Role" to add one.
      </div>
      <div v-if="isLoading" class="p-8 text-center text-gray-500">Loading roles...</div>
    </div>

    <!-- Migrate Role Dialog -->
    <div v-if="showMigrateDialog"
      class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div class="bg-white rounded-lg shadow-xl w-full max-w-lg mx-4">
        <div class="px-6 py-4 border-b flex items-center justify-between">
          <h2 class="text-lg font-semibold text-gray-900">
            Migrate Role: {{ migratingRole?.display_name || migratingRole?.name }}
          </h2>
          <button @click="showMigrateDialog = false; migrateOutput = null"
            class="text-gray-400 hover:text-gray-600 text-xl">&times;</button>
        </div>
        <div class="p-6 space-y-4">
          <div v-if="migratingRole?.ansible_playbook" class="text-sm text-gray-600">
            Playbook: <code class="bg-gray-100 px-1 rounded">{{ migratingRole.ansible_playbook }}</code>
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Target Node *</label>
            <select v-model="targetNodeId" class="w-full px-3 py-2 border rounded-lg text-sm">
              <option value="">Select target node…</option>
              <option v-for="node in nodes" :key="node.node_id" :value="node.node_id">
                {{ node.node_id }} — {{ node.ip_address }} ({{ node.status }})
              </option>
            </select>
          </div>
          <div v-if="migratingRole?.degraded_without?.length" class="text-xs text-yellow-700 bg-yellow-50 p-2 rounded">
            ⚠ Optional role. Without it: {{ migratingRole.degraded_without.join('; ') }}
          </div>
          <!-- Output -->
          <div v-if="migrateOutput" class="mt-2">
            <p class="text-xs font-medium text-gray-600 mb-1">Playbook Output:</p>
            <pre class="bg-gray-900 text-green-300 text-xs p-3 rounded overflow-auto max-h-48">{{ migrateOutput }}</pre>
          </div>
        </div>
        <div class="px-6 py-4 border-t flex justify-end gap-2">
          <button @click="showMigrateDialog = false; migrateOutput = null"
            class="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 text-sm">Cancel</button>
          <button @click="executeMigrate" :disabled="!targetNodeId || migrateLoading"
            class="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50 text-sm">
            {{ migrateLoading ? 'Running…' : 'Run Migration' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
