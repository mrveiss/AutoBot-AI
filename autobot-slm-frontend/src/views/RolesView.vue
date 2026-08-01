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
import { useI18n } from 'vue-i18n'
import { createLogger } from '@/utils/debugUtils'
import { slmApiClient } from '@/utils/ApiClient'
import { REMOTE_EXEC_TIMEOUT_MS } from '@/constants/api-timeouts'

const logger = createLogger('RolesView')
const { t } = useI18n()

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
  roles?: string[]
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

// Migration / redeploy dialog (#11719: same dialog, "Redeploy" preselects the
// node already running the role instead of asking the operator to pick one)
const showMigrateDialog = ref(false)
const migratingRole = ref<RoleDefinition | null>(null)
const targetNodeId = ref('')
const migrateLoading = ref(false)
const migrateOutput = ref<string | null>(null)
const nodes = ref<NodeSummary[]>([])
const isRedeploy = ref(false)

const formData = ref<RoleFormData>({
  name: '', display_name: '', sync_type: 'component',
  source_paths: '', target_path: '/opt/autobot',
  systemd_service: '', auto_restart: false,
  health_check_port: '', health_check_path: '',
  pre_sync_cmd: '', post_sync_cmd: '',
  required: false, ansible_playbook: '',
})

// Computed
const formTitle = computed(() => editingRole.value
  ? t('rolesView.editRoleTitle', { name: editingRole.value })
  : t('rolesView.createRole'))
const filteredRoles = computed(() => roles.value)
const nodeStatusSummary = computed(() => {
  const list = nodes.value
  return {
    total: list.length,
    online: list.filter(n => n.status === 'online' || n.status === 'healthy').length,
    offline: list.filter(n => n.status === 'offline' || n.status === 'error' || n.status === 'unhealthy').length,
    pending: list.filter(n => n.status === 'pending' || n.status === 'enrolling').length,
  }
})
const healthClass = computed(() => {
  if (!fleetHealth.value) return 'bg-gray-100 text-gray-600'
  return {
    healthy: 'bg-green-100 text-green-700',
    degraded: 'bg-yellow-100 text-yellow-700',
    critical: 'bg-red-100 text-red-700',
  }[fleetHealth.value.health] ?? 'bg-gray-100 text-gray-600'
})

/**
 * API helper — one request through the canonical client (#13140).
 *
 * `rawRequest`, not the `get`/`post`/... helpers, so the `body.detail` message
 * this view renders in `errorMessage` survives (the helpers flatten it into
 * `HTTP <n>: <msg>`) and so writes stay single-shot. The client supplies the
 * base URL, the bearer, the request timeout and the 401 handler.
 *
 * The bearer replaces `authStore.getAuthHeaders()`, which returns `{}` when the
 * store's `token` ref is null. That ref is seeded from storage once, at store
 * construction (`stores/auth.ts:66`), so a token that lands later is invisible
 * to it and the request went out anonymous; the client re-reads storage on
 * every call.
 *
 * `path` stays relative to the API base, exactly as callers already pass it,
 * and `body` is handed over unserialised (rawRequest JSON-stringifies it).
 */
async function apiFetch<T>(
  path: string,
  options: { method?: string; body?: unknown; timeout?: number } = {}
): Promise<T | null> {
  try {
    const response = await slmApiClient.rawRequest(path, options)
    if (!response.ok) {
      const body = await response.json().catch(() => ({}))
      throw new Error(body.detail || `HTTP ${response.status}`)
    }
    return await response.json()
  } catch (err) {
    errorMessage.value = t('rolesView.requestFailed', {
      message: err instanceof Error ? err.message : t('rolesView.unknownError'),
    })
    logger.error('API error:', err)
    return null
  }
}

// Actions
async function fetchRoles(): Promise<void> {
  isLoading.value = true
  errorMessage.value = null
  const result = await apiFetch<RoleDefinition[]>('/roles')
  if (result) roles.value = result
  isLoading.value = false
}

async function fetchFleetHealth(): Promise<void> {
  isLoadingHealth.value = true
  const result = await apiFetch<FleetHealth>('/roles/fleet-health')
  if (result) fleetHealth.value = result
  isLoadingHealth.value = false
}

async function fetchNodes(): Promise<void> {
  const result = await apiFetch<NodeSummary[]>('/nodes')
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
      `/roles/${editingRole.value}`,
      { method: 'PUT', body: payload }
    )
    if (result) {
      successMessage.value = t('rolesView.roleUpdated', { name: result.name })
      showForm.value = false
      await fetchRoles()
      setTimeout(() => { successMessage.value = null }, 3000)
    }
  } else {
    const result = await apiFetch<RoleDefinition>(
      '/roles',
      { method: 'POST', body: payload }
    )
    if (result) {
      successMessage.value = t('rolesView.roleCreated', { name: result.name })
      showForm.value = false
      await fetchRoles()
      setTimeout(() => { successMessage.value = null }, 3000)
    }
  }
}

async function deleteRole(roleName: string): Promise<void> {
  if (!confirm(t('rolesView.confirmDeleteRole', { name: roleName }))) return
  const result = await apiFetch<{ message: string }>(
    `/roles/${roleName}`,
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
  isRedeploy.value = false
  showMigrateDialog.value = true
  fetchNodes()
}

async function openRedeployDialog(role: RoleDefinition): Promise<void> {
  migratingRole.value = role
  migrateOutput.value = null
  isRedeploy.value = true
  showMigrateDialog.value = true
  await fetchNodes()
  // Preselect the node currently running this role, when determinable
  // (#11719) — same-node migrate IS a redeploy, so this saves the operator
  // from having to look it up on the fleet-health/nodes view first.
  const currentOwner = nodes.value.find((n) => n.roles?.includes(role.name))
  targetNodeId.value = currentOwner?.node_id || ''
}

async function executeMigrate(): Promise<void> {
  if (!migratingRole.value || !targetNodeId.value) return
  migrateLoading.value = true
  migrateOutput.value = null
  errorMessage.value = null

  const result = await apiFetch<{ success: boolean; output: string; playbook: string }>(
    `/roles/${migratingRole.value.name}/migrate`,
    // Runs an ansible playbook against the target node — the client's 30s
    // default would abort a migration that completes fine today.
    {
      method: 'POST',
      body: { target_node_id: targetNodeId.value },
      timeout: REMOTE_EXEC_TIMEOUT_MS,
    }
  )

  migrateLoading.value = false
  if (result) {
    migrateOutput.value = result.output
    if (result.success) {
      successMessage.value = isRedeploy.value
        ? t('rolesView.redeploySucceeded', { role: migratingRole.value.name, node: targetNodeId.value })
        : t('rolesView.migrateSucceeded', { role: migratingRole.value.name, node: targetNodeId.value })
    } else {
      errorMessage.value = isRedeploy.value
        ? t('rolesView.redeployFailed')
        : t('rolesView.migrateFailed')
    }
  }
}

// Lifecycle
onMounted(() => {
  fetchRoles()
  fetchFleetHealth()
  fetchNodes()
})
</script>

<template>
  <div class="p-6 max-w-7xl mx-auto">
    <!-- Header -->
    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-2xl font-bold text-gray-900">{{ $t('rolesView.roleRegistry') }}</h1>
        <p class="text-sm text-gray-500 mt-1">{{ $t('rolesView.manageRoleDefinitionsFor') }}</p>
      </div>
      <div class="flex items-center gap-2">
        <!-- Fleet health badge -->
        <span v-if="fleetHealth" :class="['px-3 py-1 rounded-full text-xs font-medium capitalize', healthClass]">
          {{ fleetHealth.health }}
          <span v-if="fleetHealth.required_down.length">{{ $t('rolesView.countCritical', { count: fleetHealth.required_down.length }) }}</span>
        </span>
        <button @click="fetchRoles(); fetchFleetHealth()" :disabled="isLoading"
          class="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50">
          {{ isLoading ? $t('rolesView.loading') : $t('rolesView.refresh') }}
        </button>
        <button @click="openCreateForm"
          class="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">
          {{ $t('rolesView.createRole') }}
        </button>
      </div>
    </div>

    <!-- Fleet health detail (degraded/critical) -->
    <div v-if="fleetHealth && fleetHealth.health !== 'healthy'" class="mb-4 p-3 rounded-lg border text-sm"
      :class="fleetHealth.health === 'critical' ? 'bg-red-50 border-red-200 text-red-700' : 'bg-yellow-50 border-yellow-200 text-yellow-700'">
      {{ fleetHealth.detail }}
    </div>

    <!-- Node Status Summary -->
    <div class="grid grid-cols-4 gap-4 mb-6">
      <div class="bg-white rounded-lg border border-gray-200 p-4">
        <p class="text-sm text-gray-500">{{ $t('rolesView.totalNodes') }}</p>
        <p class="text-3xl font-bold text-gray-900">{{ nodeStatusSummary.total }}</p>
      </div>
      <div class="bg-white rounded-lg border border-green-200 p-4">
        <p class="text-sm text-green-600">{{ $t('rolesView.online') }}</p>
        <p class="text-3xl font-bold text-green-700">{{ nodeStatusSummary.online }}</p>
      </div>
      <div class="bg-white rounded-lg border border-red-200 p-4">
        <p class="text-sm text-red-600">{{ $t('rolesView.offline') }}</p>
        <p class="text-3xl font-bold text-red-700">{{ nodeStatusSummary.offline }}</p>
      </div>
      <div class="bg-white rounded-lg border border-yellow-200 p-4">
        <p class="text-sm text-yellow-600">{{ $t('rolesView.pending') }}</p>
        <p class="text-3xl font-bold text-yellow-700">{{ nodeStatusSummary.pending }}</p>
      </div>
    </div>

    <!-- Alerts -->
    <div v-if="errorMessage" class="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
      {{ errorMessage }}
      <button @click="errorMessage = null" class="ml-2 underline">{{ $t('rolesView.dismiss') }}</button>
    </div>
    <div v-if="successMessage" class="mb-4 p-3 bg-green-50 border border-green-200 rounded-lg text-green-700 text-sm">
      {{ successMessage }}
    </div>

    <!-- Role Form (Create/Edit) -->
    <div v-if="showForm" class="bg-white rounded-lg border mb-6">
      <div class="px-4 py-3 bg-gray-50 border-b flex items-center justify-between">
        <h2 class="font-medium text-gray-900">{{ formTitle }}</h2>
        <button @click="showForm = false" class="text-gray-400 hover:text-gray-600">{{ $t('rolesView.times') }}</button>
      </div>
      <form @submit.prevent="saveRole" class="p-4 space-y-4">
        <div class="grid grid-cols-2 gap-4">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">{{ $t('rolesView.name') }}</label>
            <input v-model="formData.name" :disabled="!!editingRole" required
              class="w-full px-3 py-2 border rounded-lg text-sm disabled:bg-gray-100" :placeholder="$t('rolesView.placeholderName')" />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">{{ $t('rolesView.displayName') }}</label>
            <input v-model="formData.display_name"
              class="w-full px-3 py-2 border rounded-lg text-sm" :placeholder="$t('rolesView.placeholderDisplayName')" />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">{{ $t('rolesView.syncType') }}</label>
            <select v-model="formData.sync_type" class="w-full px-3 py-2 border rounded-lg text-sm">
              <option value="component">{{ $t('rolesView.component') }}</option>
              <option value="full">{{ $t('rolesView.full') }}</option>
              <option value="config">{{ $t('rolesView.configOnly') }}</option>
            </select>
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">{{ $t('rolesView.targetPath') }}</label>
            <input v-model="formData.target_path" required
              class="w-full px-3 py-2 border rounded-lg text-sm" :placeholder="$t('rolesView.placeholderTargetPath')" />
          </div>
          <div class="col-span-2">
            <label class="block text-sm font-medium text-gray-700 mb-1">{{ $t('rolesView.sourcePathsCommaSeparated') }}</label>
            <input v-model="formData.source_paths"
              class="w-full px-3 py-2 border rounded-lg text-sm" :placeholder="$t('rolesView.placeholderSourcePaths')" />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">{{ $t('rolesView.systemdService') }}</label>
            <input v-model="formData.systemd_service"
              class="w-full px-3 py-2 border rounded-lg text-sm" :placeholder="$t('rolesView.placeholderSystemdService')" />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">{{ $t('rolesView.ansiblePlaybook') }}</label>
            <input v-model="formData.ansible_playbook"
              class="w-full px-3 py-2 border rounded-lg text-sm" :placeholder="$t('rolesView.placeholderAnsiblePlaybook')" />
          </div>
          <div class="flex items-center gap-4 pt-6">
            <label class="flex items-center gap-2 text-sm text-gray-700">
              <input type="checkbox" v-model="formData.auto_restart" class="rounded-sm" />
              {{ $t('rolesView.autoRestartOnDeploy') }}
            </label>
            <label class="flex items-center gap-2 text-sm text-gray-700">
              <input type="checkbox" v-model="formData.required" class="rounded-sm" />
              {{ $t('rolesView.requiredRole') }}
            </label>
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">{{ $t('rolesView.healthCheckPort') }}</label>
            <input v-model="formData.health_check_port" type="number"
              class="w-full px-3 py-2 border rounded-lg text-sm" :placeholder="$t('rolesView.placeholderHealthCheckPort')" />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">{{ $t('rolesView.healthCheckPath') }}</label>
            <input v-model="formData.health_check_path"
              class="w-full px-3 py-2 border rounded-lg text-sm" :placeholder="$t('rolesView.placeholderHealthCheckPath')" />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">{{ $t('rolesView.preSyncCommand') }}</label>
            <input v-model="formData.pre_sync_cmd"
              class="w-full px-3 py-2 border rounded-lg text-sm" :placeholder="$t('rolesView.placeholderPreSyncCmd')" />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">{{ $t('rolesView.postSyncCommand') }}</label>
            <input v-model="formData.post_sync_cmd"
              class="w-full px-3 py-2 border rounded-lg text-sm" :placeholder="$t('rolesView.placeholderPostSyncCmd')" />
          </div>
        </div>
        <div class="flex gap-2 pt-2">
          <button type="submit" class="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm">
            {{ editingRole ? $t('rolesView.update') : $t('rolesView.create') }}
          </button>
          <button type="button" @click="showForm = false"
            class="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 text-sm">{{ $t('rolesView.cancel') }}</button>
        </div>
      </form>
    </div>

    <!-- Roles Table -->
    <div class="bg-white rounded-lg border">
      <div class="px-4 py-3 bg-gray-50 border-b">
        <h2 class="font-medium text-gray-900">{{ $t('rolesView.registeredRoles', { count: filteredRoles.length }) }}</h2>
      </div>
      <table class="w-full">
        <thead class="bg-gray-50">
          <tr>
            <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">{{ $t('rolesView.name1') }}</th>
            <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">{{ $t('rolesView.syncType') }}</th>
            <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">{{ $t('rolesView.target') }}</th>
            <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">{{ $t('rolesView.service') }}</th>
            <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">{{ $t('rolesView.health') }}</th>
            <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">{{ $t('rolesView.actions') }}</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-200">
          <tr v-for="role in filteredRoles" :key="role.name" class="hover:bg-gray-50">
            <td class="px-4 py-3">
              <div class="flex items-center gap-2">
                <p class="text-sm font-medium text-gray-900">{{ role.display_name || role.name }}</p>
                <span v-if="role.required"
                  class="px-1.5 py-0.5 text-xs rounded-sm bg-red-100 text-red-700 font-medium">{{ $t('rolesView.required') }}</span>
              </div>
              <p v-if="role.display_name" class="text-xs text-gray-500">{{ role.name }}</p>
            </td>
            <td class="px-4 py-3">
              <span class="px-2 py-1 text-xs rounded-full bg-blue-100 text-blue-700">{{ role.sync_type || $t('rolesView.component2') }}</span>
            </td>
            <td class="px-4 py-3 text-sm text-gray-600 font-mono">{{ role.target_path }}</td>
            <td class="px-4 py-3 text-sm text-gray-600">{{ role.systemd_service || '-' }}</td>
            <td class="px-4 py-3 text-sm text-gray-600">
              <span v-if="role.health_check_port">:{{ role.health_check_port }}{{ role.health_check_path || '' }}</span>
              <span v-else class="text-gray-400">-</span>
            </td>
            <td class="px-4 py-3 text-right space-x-1">
              <button @click="openEditForm(role)"
                class="px-2 py-1 text-xs bg-gray-100 text-gray-700 rounded-sm hover:bg-gray-200">{{ $t('rolesView.edit') }}</button>
              <button v-if="role.ansible_playbook" @click="openMigrateDialog(role)"
                class="px-2 py-1 text-xs bg-purple-100 text-purple-700 rounded-sm hover:bg-purple-200">{{ $t('rolesView.migrate') }}</button>
              <button v-if="role.ansible_playbook" @click="openRedeployDialog(role)"
                class="px-2 py-1 text-xs bg-indigo-100 text-indigo-700 rounded-sm hover:bg-indigo-200">{{ $t('rolesView.redeploy') }}</button>
              <button @click="deleteRole(role.name)"
                class="px-2 py-1 text-xs bg-red-100 text-red-700 rounded-sm hover:bg-red-200">{{ $t('rolesView.delete') }}</button>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="!filteredRoles.length && !isLoading" class="p-8 text-center text-gray-500">
        {{ $t('rolesView.noRolesDefinedClick') }}
      </div>
      <div v-if="isLoading" class="p-8 text-center text-gray-500">{{ $t('rolesView.loadingRoles') }}</div>
    </div>

    <!-- Migrate Role Dialog -->
    <div v-if="showMigrateDialog"
      class="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div class="bg-white rounded-lg shadow-xl w-full max-w-lg mx-4">
        <div class="px-6 py-4 border-b flex items-center justify-between">
          <h2 class="text-lg font-semibold text-gray-900">
            {{ isRedeploy ? $t('rolesView.redeployRoleTitle') : $t('rolesView.migrateRoleTitle') }}:
            {{ migratingRole?.display_name || migratingRole?.name }}
          </h2>
          <button @click="showMigrateDialog = false; migrateOutput = null"
            class="text-gray-400 hover:text-gray-600 text-xl">{{ $t('rolesView.times') }}</button>
        </div>
        <div class="p-6 space-y-4">
          <div v-if="isRedeploy" class="text-xs text-indigo-700 bg-indigo-50 p-2 rounded-sm">
            {{ $t('rolesView.redeployHint') }}
          </div>
          <div v-if="migratingRole?.ansible_playbook" class="text-sm text-gray-600">
            {{ $t('rolesView.playbook') }} <code class="bg-gray-100 px-1 rounded-sm">{{ migratingRole.ansible_playbook }}</code>
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">{{ $t('rolesView.targetNode') }}</label>
            <select v-model="targetNodeId" class="w-full px-3 py-2 border rounded-lg text-sm">
              <option value="">{{ $t('rolesView.selectTargetNode') }}</option>
              <option v-for="node in nodes" :key="node.node_id" :value="node.node_id">
                {{ node.node_id }} — {{ node.ip_address }} ({{ node.status }})
              </option>
            </select>
          </div>
          <div v-if="migratingRole?.degraded_without?.length" class="text-xs text-yellow-700 bg-yellow-50 p-2 rounded-sm">
            {{ $t('rolesView.optionalRoleWithout', { detail: migratingRole.degraded_without.join('; ') }) }}
          </div>
          <!-- Output -->
          <div v-if="migrateOutput" class="mt-2">
            <p class="text-xs font-medium text-gray-600 mb-1">{{ $t('rolesView.playbookOutput') }}</p>
            <pre class="bg-gray-900 text-green-300 text-xs p-3 rounded-sm overflow-auto max-h-48">{{ migrateOutput }}</pre>
          </div>
        </div>
        <div class="px-6 py-4 border-t flex justify-end gap-2">
          <button @click="showMigrateDialog = false; migrateOutput = null"
            class="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 text-sm">{{ $t('rolesView.cancel') }}</button>
          <button @click="executeMigrate" :disabled="!targetNodeId || migrateLoading"
            :class="isRedeploy ? 'bg-indigo-600 hover:bg-indigo-700' : 'bg-purple-600 hover:bg-purple-700'"
            class="px-4 py-2 text-white rounded-lg disabled:opacity-50 text-sm">
            {{ migrateLoading
              ? $t('rolesView.running')
              : (isRedeploy ? $t('rolesView.runRedeploy') : $t('rolesView.runMigration')) }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
