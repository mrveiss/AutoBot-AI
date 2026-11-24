<script setup lang="ts">
import { BaseAlert, BaseModal, HttpError, createLogger } from '@autobot/ui'
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
import { slmApiClient } from '@/utils/ApiClient'
import { useFleetStore } from '@/stores/fleet'
import { REMOTE_EXEC_TIMEOUT_MS } from '@/constants/api-timeouts'
import { joinSystemdUnits, parseSystemdUnits } from '@/composables/useRoles'

const logger = createLogger('RolesView')
const { t } = useI18n()
const fleetStore = useFleetStore()

// Types
interface RoleDefinition {
  name: string
  display_name: string | null
  sync_type: string | null
  source_paths: string[]
  target_path: string
  systemd_service: string[] | null // #16025: a role can own >1 systemd unit
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
  if (!fleetHealth.value) return 'bg-autobot-bg-tertiary text-autobot-text-secondary'
  return {
    healthy: 'bg-autobot-pill-ok-bg text-autobot-pill-ok-fg',
    degraded: 'bg-autobot-pill-warn-bg text-autobot-pill-warn-fg',
    critical: 'bg-autobot-pill-bad-bg text-autobot-pill-bad-fg',
  }[fleetHealth.value.health] ?? 'bg-autobot-bg-tertiary text-autobot-text-secondary'
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
      throw HttpError.withDetail(response.status, response.statusText, body.detail || undefined)
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
  // Every page of the fleet through the one node-list fetch (#21584), not the first 20.
  try {
    await fleetStore.fetchNodes() // a partial read is kept and announced once by the shell
    nodes.value = fleetStore.nodeList
  } catch (err) {
    errorMessage.value = t('rolesView.requestFailed', { message: (err instanceof HttpError && err.detail) || (err instanceof Error ? err.message : t('rolesView.unknownError')) })
    logger.error('Failed to load nodes:', err)
  }
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
    systemd_service: joinSystemdUnits(role.systemd_service),
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
    systemd_service: parseSystemdUnits(f.systemd_service),
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
        <h1 class="text-2xl font-bold text-autobot-text-primary">{{ $t('rolesView.roleRegistry') }}</h1>
        <p class="text-sm text-autobot-text-tertiary mt-1">{{ $t('rolesView.manageRoleDefinitionsFor') }}</p>
      </div>
      <div class="flex items-center gap-2">
        <!-- Fleet health badge -->
        <span v-if="fleetHealth" :class="['px-3 py-1 rounded-full text-xs font-medium capitalize', healthClass]">
          {{ fleetHealth.health }}
          <span v-if="fleetHealth.required_down.length">{{ $t('rolesView.countCritical', { count: fleetHealth.required_down.length }) }}</span>
        </span>
        <button @click="fetchRoles(); fetchFleetHealth()" :disabled="isLoading"
          class="px-4 py-2 border border-autobot-border-strong rounded-lg hover:bg-autobot-bg-hover disabled:opacity-50">
          {{ isLoading ? $t('rolesView.loading') : $t('rolesView.refresh') }}
        </button>
        <button @click="openCreateForm"
          class="px-4 py-2 bg-autobot-primary text-autobot-text-on-primary rounded-lg hover:bg-autobot-primary-hover">
          {{ $t('rolesView.createRole') }}
        </button>
      </div>
    </div>

    <!-- Fleet health detail (degraded/critical) -->
    <BaseAlert
      v-if="fleetHealth && fleetHealth.health !== 'healthy'"
      :variant="fleetHealth.health === 'critical' ? 'error' : 'warning'"
      class="mb-4"
      :message="fleetHealth.detail"
    />

    <!-- Node Status Summary -->
    <div class="grid grid-cols-4 gap-4 mb-6">
      <div class="bg-white rounded-lg border border-autobot-border p-4">
        <p class="text-sm text-autobot-text-tertiary">{{ $t('rolesView.totalNodes') }}</p>
        <p class="text-3xl font-bold text-autobot-text-primary">{{ nodeStatusSummary.total }}</p>
      </div>
      <div class="bg-white rounded-lg border border-autobot-success-light p-4">
        <p class="text-sm text-autobot-success">{{ $t('rolesView.online') }}</p>
        <p class="text-3xl font-bold text-autobot-pill-ok-fg">{{ nodeStatusSummary.online }}</p>
      </div>
      <div class="bg-white rounded-lg border border-autobot-error-light p-4">
        <p class="text-sm text-autobot-error">{{ $t('rolesView.offline') }}</p>
        <p class="text-3xl font-bold text-autobot-pill-bad-fg">{{ nodeStatusSummary.offline }}</p>
      </div>
      <div class="bg-white rounded-lg border border-autobot-warning-light p-4">
        <p class="text-sm text-autobot-warning">{{ $t('rolesView.pending') }}</p>
        <p class="text-3xl font-bold text-autobot-pill-warn-fg">{{ nodeStatusSummary.pending }}</p>
      </div>
    </div>

    <!-- Alerts -->
    <BaseAlert v-if="errorMessage" variant="error" class="mb-4" :message="errorMessage" dismissible :dismiss-label="$t('rolesView.dismiss')" @dismiss="errorMessage = null" />
    <BaseAlert v-if="successMessage" variant="success" class="mb-4" :message="successMessage" />

    <!-- Role Form (Create/Edit) -->
    <div v-if="showForm" class="bg-white rounded-lg border mb-6">
      <div class="px-4 py-3 bg-autobot-bg-secondary border-b flex items-center justify-between">
        <h2 class="font-medium text-autobot-text-primary">{{ formTitle }}</h2>
        <button @click="showForm = false" class="text-autobot-text-tertiary hover:text-autobot-text-secondary">{{ $t('rolesView.times') }}</button>
      </div>
      <form @submit.prevent="saveRole" class="p-4 space-y-4">
        <div class="grid grid-cols-2 gap-4">
          <div>
            <label class="block text-sm font-medium text-autobot-text-secondary mb-1">{{ $t('rolesView.name') }}</label>
            <input v-model="formData.name" :disabled="!!editingRole" required
              class="w-full px-3 py-2 border rounded-lg text-sm disabled:bg-autobot-bg-tertiary" :placeholder="$t('rolesView.placeholderName')" />
          </div>
          <div>
            <label class="block text-sm font-medium text-autobot-text-secondary mb-1">{{ $t('rolesView.displayName') }}</label>
            <input v-model="formData.display_name"
              class="w-full px-3 py-2 border rounded-lg text-sm" :placeholder="$t('rolesView.placeholderDisplayName')" />
          </div>
          <div>
            <label class="block text-sm font-medium text-autobot-text-secondary mb-1">{{ $t('rolesView.syncType') }}</label>
            <select v-model="formData.sync_type" class="w-full px-3 py-2 border rounded-lg text-sm">
              <option value="component">{{ $t('rolesView.component') }}</option>
              <option value="full">{{ $t('rolesView.full') }}</option>
              <option value="config">{{ $t('rolesView.configOnly') }}</option>
            </select>
          </div>
          <div>
            <label class="block text-sm font-medium text-autobot-text-secondary mb-1">{{ $t('rolesView.targetPath') }}</label>
            <input v-model="formData.target_path" required
              class="w-full px-3 py-2 border rounded-lg text-sm" :placeholder="$t('rolesView.placeholderTargetPath')" />
          </div>
          <div class="col-span-2">
            <label class="block text-sm font-medium text-autobot-text-secondary mb-1">{{ $t('rolesView.sourcePathsCommaSeparated') }}</label>
            <input v-model="formData.source_paths"
              class="w-full px-3 py-2 border rounded-lg text-sm" :placeholder="$t('rolesView.placeholderSourcePaths')" />
          </div>
          <div>
            <label class="block text-sm font-medium text-autobot-text-secondary mb-1">{{ $t('rolesView.systemdService') }}</label>
            <input v-model="formData.systemd_service"
              class="w-full px-3 py-2 border rounded-lg text-sm" :placeholder="$t('rolesView.placeholderSystemdService')" />
          </div>
          <div>
            <label class="block text-sm font-medium text-autobot-text-secondary mb-1">{{ $t('rolesView.ansiblePlaybook') }}</label>
            <input v-model="formData.ansible_playbook"
              class="w-full px-3 py-2 border rounded-lg text-sm" :placeholder="$t('rolesView.placeholderAnsiblePlaybook')" />
          </div>
          <div class="flex items-center gap-4 pt-6">
            <label class="flex items-center gap-2 text-sm text-autobot-text-secondary">
              <input type="checkbox" v-model="formData.auto_restart" class="rounded-sm" />
              {{ $t('rolesView.autoRestartOnDeploy') }}
            </label>
            <label class="flex items-center gap-2 text-sm text-autobot-text-secondary">
              <input type="checkbox" v-model="formData.required" class="rounded-sm" />
              {{ $t('rolesView.requiredRole') }}
            </label>
          </div>
          <div>
            <label class="block text-sm font-medium text-autobot-text-secondary mb-1">{{ $t('rolesView.healthCheckPort') }}</label>
            <input v-model="formData.health_check_port" type="number"
              class="w-full px-3 py-2 border rounded-lg text-sm" :placeholder="$t('rolesView.placeholderHealthCheckPort')" />
          </div>
          <div>
            <label class="block text-sm font-medium text-autobot-text-secondary mb-1">{{ $t('rolesView.healthCheckPath') }}</label>
            <input v-model="formData.health_check_path"
              class="w-full px-3 py-2 border rounded-lg text-sm" :placeholder="$t('rolesView.placeholderHealthCheckPath')" />
          </div>
          <div>
            <label class="block text-sm font-medium text-autobot-text-secondary mb-1">{{ $t('rolesView.preSyncCommand') }}</label>
            <input v-model="formData.pre_sync_cmd"
              class="w-full px-3 py-2 border rounded-lg text-sm" :placeholder="$t('rolesView.placeholderPreSyncCmd')" />
          </div>
          <div>
            <label class="block text-sm font-medium text-autobot-text-secondary mb-1">{{ $t('rolesView.postSyncCommand') }}</label>
            <input v-model="formData.post_sync_cmd"
              class="w-full px-3 py-2 border rounded-lg text-sm" :placeholder="$t('rolesView.placeholderPostSyncCmd')" />
          </div>
        </div>
        <div class="flex gap-2 pt-2">
          <button type="submit" class="px-4 py-2 bg-autobot-primary text-autobot-text-on-primary rounded-lg hover:bg-autobot-primary-hover text-sm">
            {{ editingRole ? $t('rolesView.update') : $t('rolesView.create') }}
          </button>
          <button type="button" @click="showForm = false"
            class="px-4 py-2 border border-autobot-border-strong rounded-lg hover:bg-autobot-bg-hover text-sm">{{ $t('rolesView.cancel') }}</button>
        </div>
      </form>
    </div>

    <!-- Roles Table -->
    <div class="bg-white rounded-lg border">
      <div class="px-4 py-3 bg-autobot-bg-secondary border-b">
        <h2 class="font-medium text-autobot-text-primary">{{ $t('rolesView.registeredRoles', { count: filteredRoles.length }) }}</h2>
      </div>
      <table class="w-full">
        <thead class="bg-autobot-bg-secondary">
          <tr>
            <th class="px-4 py-3 text-left text-xs font-medium text-autobot-text-tertiary uppercase">{{ $t('rolesView.name1') }}</th>
            <th class="px-4 py-3 text-left text-xs font-medium text-autobot-text-tertiary uppercase">{{ $t('rolesView.syncType') }}</th>
            <th class="px-4 py-3 text-left text-xs font-medium text-autobot-text-tertiary uppercase">{{ $t('rolesView.target') }}</th>
            <th class="px-4 py-3 text-left text-xs font-medium text-autobot-text-tertiary uppercase">{{ $t('rolesView.service') }}</th>
            <th class="px-4 py-3 text-left text-xs font-medium text-autobot-text-tertiary uppercase">{{ $t('rolesView.health') }}</th>
            <th class="px-4 py-3 text-right text-xs font-medium text-autobot-text-tertiary uppercase">{{ $t('rolesView.actions') }}</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-autobot-border">
          <tr v-for="role in filteredRoles" :key="role.name" class="hover:bg-autobot-bg-hover">
            <td class="px-4 py-3">
              <div class="flex items-center gap-2">
                <p class="text-sm font-medium text-autobot-text-primary">{{ role.display_name || role.name }}</p>
                <span v-if="role.required"
                  class="px-1.5 py-0.5 text-xs rounded-sm bg-autobot-pill-bad-bg text-autobot-pill-bad-fg font-medium">{{ $t('rolesView.required') }}</span>
              </div>
              <p v-if="role.display_name" class="text-xs text-autobot-text-tertiary">{{ role.name }}</p>
            </td>
            <td class="px-4 py-3">
              <span class="px-2 py-1 text-xs rounded-full bg-autobot-pill-info-bg text-autobot-text-primary">{{ role.sync_type || $t('rolesView.component2') }}</span>
            </td>
            <td class="px-4 py-3 text-sm text-autobot-text-secondary font-mono">{{ role.target_path }}</td>
            <td class="px-4 py-3 text-sm text-autobot-text-secondary">{{ joinSystemdUnits(role.systemd_service) || '-' }}</td>
            <td class="px-4 py-3 text-sm text-autobot-text-secondary">
              <span v-if="role.health_check_port">:{{ role.health_check_port }}{{ role.health_check_path || '' }}</span>
              <span v-else class="text-autobot-text-tertiary">-</span>
            </td>
            <td class="px-4 py-3 text-right space-x-1">
              <button @click="openEditForm(role)"
                class="px-2 py-1 text-xs bg-autobot-bg-tertiary text-autobot-text-secondary rounded-sm hover:bg-autobot-bg-active">{{ $t('rolesView.edit') }}</button>
              <button v-if="role.ansible_playbook" @click="openMigrateDialog(role)"
                class="px-2 py-1 text-xs bg-autobot-illus-2-tint text-autobot-text-primary rounded-sm hover:bg-autobot-illus-2-tint">{{ $t('rolesView.migrate') }}</button>
              <button v-if="role.ansible_playbook" @click="openRedeployDialog(role)"
                class="px-2 py-1 text-xs bg-autobot-illus-1-tint text-autobot-text-primary rounded-sm hover:bg-autobot-primary-bg">{{ $t('rolesView.redeploy') }}</button>
              <button @click="deleteRole(role.name)"
                class="px-2 py-1 text-xs bg-autobot-pill-bad-bg text-autobot-pill-bad-fg rounded-sm hover:bg-autobot-pill-bad-bg">{{ $t('rolesView.delete') }}</button>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="!filteredRoles.length && !isLoading" class="p-8 text-center text-autobot-text-tertiary">
        {{ $t('rolesView.noRolesDefinedClick') }}
      </div>
      <div v-if="isLoading" class="p-8 text-center text-autobot-text-tertiary">{{ $t('rolesView.loadingRoles') }}</div>
    </div>

    <!-- Migrate Role Dialog: locked while the playbook runs, as Cancel is (#14777) -->
    <BaseModal
      v-model="showMigrateDialog"
      :title="`${isRedeploy ? $t('rolesView.redeployRoleTitle') : $t('rolesView.migrateRoleTitle')}: ${migratingRole?.display_name || migratingRole?.name || ''}`"
      width="32rem"
      :locked="migrateLoading"
      :close-label="$t('ui.modal.closeDialog')"
      @close="migrateOutput = null"
    >
      <div class="space-y-4">
        <div v-if="isRedeploy" class="text-xs text-autobot-text-primary bg-autobot-illus-1-tint p-2 rounded-sm">
          {{ $t('rolesView.redeployHint') }}
        </div>
        <div v-if="migratingRole?.ansible_playbook" class="text-sm text-autobot-text-secondary">
          {{ $t('rolesView.playbook') }} <code class="bg-autobot-bg-tertiary px-1 rounded-sm">{{ migratingRole.ansible_playbook }}</code>
        </div>
        <div>
          <label class="block text-sm font-medium text-autobot-text-secondary mb-1">{{ $t('rolesView.targetNode') }}</label>
          <select v-model="targetNodeId" class="w-full px-3 py-2 border rounded-lg text-sm">
            <option value="">{{ $t('rolesView.selectTargetNode') }}</option>
            <option v-for="node in nodes" :key="node.node_id" :value="node.node_id">
              {{ node.node_id }} — {{ node.ip_address }} ({{ node.status }})
            </option>
          </select>
        </div>
        <BaseAlert
          v-if="migratingRole?.degraded_without?.length"
          variant="warning"
          size="compact"
          :message="$t('rolesView.optionalRoleWithout', { detail: migratingRole.degraded_without.join('; ') })"
        />
        <!-- Output -->
        <div v-if="migrateOutput" class="mt-2">
          <p class="text-xs font-medium text-autobot-text-secondary mb-1">{{ $t('rolesView.playbookOutput') }}</p>
          <pre class="bg-autobot-bg-tertiary text-autobot-success text-xs p-3 rounded-sm overflow-auto max-h-48">{{ migrateOutput }}</pre>
        </div>
      </div>
      <template #actions>
        <div class="flex justify-end gap-2">
          <button @click="showMigrateDialog = false; migrateOutput = null" :disabled="migrateLoading"
            class="px-4 py-2 border border-autobot-border-strong rounded-lg hover:bg-autobot-bg-hover text-sm disabled:opacity-50">{{ $t('rolesView.cancel') }}</button>
          <button @click="executeMigrate" :disabled="!targetNodeId || migrateLoading"
            :class="isRedeploy ? 'bg-autobot-primary hover:bg-autobot-primary-hover' : 'bg-autobot-ink hover:bg-autobot-ink-hover'"
            class="px-4 py-2 text-autobot-text-on-primary rounded-lg disabled:opacity-50 text-sm">
            {{ migrateLoading
              ? $t('rolesView.running')
              : (isRedeploy ? $t('rolesView.runRedeploy') : $t('rolesView.runMigration')) }}
          </button>
        </div>
      </template>
    </BaseModal>
  </div>
</template>
