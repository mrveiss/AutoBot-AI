<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Role Management Modal (Issue #779)
 *
 * Allows viewing and managing roles for a node.
 *
 * Issue #754: Added role="dialog", aria-modal, aria-labelledby,
 * keyboard escape handling, accessible labels on buttons,
 * scope attributes on table headers, role="status" on sync message.
 */

import { ref, computed, onMounted } from 'vue'
import { useRoles, type NodeRolesInfo } from '@/composables/useRoles'
import { formatDateTime } from '@/composables/useTimezone'

const props = defineProps<{
  nodeId: string
  hostname: string
}>()

const emit = defineEmits<{
  close: []
  saved: []
}>()

const { roles, fetchRoles, getNodeRoles, assignRole, removeRole, syncRole } = useRoles()

const nodeRoles = ref<NodeRolesInfo | null>(null)
const selectedRole = ref<string>('')
const isSaving = ref(false)
const isLoading = ref(true)
const isSyncing = ref(false)
const syncMessage = ref<string | null>(null)

// Removal confirmation state (Issue #1041)
const showRemoveConfirm = ref(false)
const roleToRemove = ref<string>('')
const isRemoving = ref(false)

const DATA_BEARING_ROLES = [
  'redis', 'slm-database', 'ai-stack', 'chromadb',
  'autobot-llm-cpu', 'autobot-llm-gpu', 'backend', 'slm-monitoring',
]

const isDataBearingRole = computed(() => DATA_BEARING_ROLES.includes(roleToRemove.value))

const availableRoles = computed(() =>
  roles.filter(r => r.name !== 'code-source' && r.target_path)
)

const detectedRolesList = computed(() => nodeRoles.value?.detected_roles || [])

const allNodeRoles = computed(() => nodeRoles.value?.roles || [])

onMounted(async () => {
  await Promise.all([fetchRoles(), loadNodeRoles()])
  isLoading.value = false
})

async function loadNodeRoles() {
  nodeRoles.value = await getNodeRoles(props.nodeId)
}

async function handleAssignRole() {
  if (!selectedRole.value) return

  isSaving.value = true
  const result = await assignRole(props.nodeId, selectedRole.value, 'manual')
  isSaving.value = false

  if (result) {
    await loadNodeRoles()
    selectedRole.value = ''
    emit('saved')
  }
}

function handleRemoveRole(roleName: string) {
  roleToRemove.value = roleName
  showRemoveConfirm.value = true
}

function cancelRemove() {
  showRemoveConfirm.value = false
  roleToRemove.value = ''
}

async function confirmRemove(withBackup: boolean) {
  showRemoveConfirm.value = false
  isRemoving.value = true
  syncMessage.value = `Removing ${roleToRemove.value}...`

  const result = await removeRole(props.nodeId, roleToRemove.value, withBackup)
  isRemoving.value = false

  if (result.success) {
    syncMessage.value = result.backup_path
      ? `Removed. Backup saved to ${result.backup_path}`
      : result.message || `Role '${roleToRemove.value}' removed`
    roleToRemove.value = ''
    await loadNodeRoles()
    emit('saved')
  } else {
    syncMessage.value = result.message || 'Role removal failed'
  }
}

async function handleSyncRole(roleName: string) {
  isSyncing.value = true
  syncMessage.value = null

  const result = await syncRole(roleName, [props.nodeId], true)

  syncMessage.value = result.message
  isSyncing.value = false

  if (result.success) {
    await loadNodeRoles()
  }
}

function getStatusClass(status: string): string {
  switch (status) {
    case 'active':
      return 'status-active'
    case 'inactive':
      return 'status-inactive'
    default:
      return 'status-not-installed'
  }
}

function formatDate(dateStr: string | null): string {
  return formatDateTime(dateStr)
}
</script>

<template>
  <div
    class="modal-overlay"
    @click.self="emit('close')"
    @keydown.escape="emit('close')"
    role="dialog"
    aria-modal="true"
    aria-labelledby="role-mgmt-title"
  >
    <div class="modal-content">
      <div class="modal-header">
        <h3 id="role-mgmt-title">{{ $t('roleManagementModal.roleManagement') }}</h3>
        <span class="hostname">{{ hostname }}</span>
        <button class="close-btn" @click="emit('close')" :aria-label="$t('roleManagementModal.closeRoleManagement')">
          <span aria-hidden="true">{{ $t('roleManagementModal.times') }}</span>
        </button>
      </div>

      <div v-if="isLoading" class="loading" role="status">
        {{ $t('roleManagementModal.loadingRoleInformation') }}
      </div>

      <div v-else class="modal-body">
        <!-- Detected Roles Section -->
        <section class="section" :aria-label="$t('roleManagementModal.autoDetectedRoles2')">
          <h4>{{ $t('roleManagementModal.autoDetectedRoles') }}</h4>
          <div v-if="detectedRolesList.length === 0" class="empty-message">
            {{ $t('roleManagementModal.noRolesAutoDetected') }}
          </div>
          <div v-else class="role-list">
            <div
              v-for="roleName in detectedRolesList"
              :key="roleName"
              class="role-item detected"
            >
              <span class="role-name">{{ roleName }}</span>
              <span class="role-badge auto">{{ $t('roleManagementModal.auto') }}</span>
            </div>
          </div>
        </section>

        <!-- All Role Statuses -->
        <section class="section" :aria-label="$t('roleManagementModal.roleStatusTable')">
          <h4>{{ $t('roleManagementModal.roleStatus') }}</h4>
          <table class="role-table" v-if="allNodeRoles.length > 0">
            <thead>
              <tr>
                <th scope="col">{{ $t('roleManagementModal.role') }}</th>
                <th scope="col">{{ $t('roleManagementModal.status') }}</th>
                <th scope="col">{{ $t('roleManagementModal.version') }}</th>
                <th scope="col">{{ $t('roleManagementModal.lastSynced') }}</th>
                <th scope="col">{{ $t('roleManagementModal.actions') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="role in allNodeRoles" :key="role.role_name">
                <td>
                  {{ role.role_name }}
                  <span v-if="role.assignment_type === 'manual'" class="role-badge manual">{{ $t('roleManagementModal.manual') }}</span>
                </td>
                <td>
                  <span :class="['status', getStatusClass(role.status)]">
                    {{ role.status }}
                  </span>
                </td>
                <td>{{ role.current_version?.slice(0, 12) || '-' }}</td>
                <td>{{ formatDate(role.last_synced_at) }}</td>
                <td class="actions">
                  <button
                    class="btn btn-sm btn-primary"
                    :disabled="isSyncing"
                    @click="handleSyncRole(role.role_name)"
                    :aria-label="$t('roleManagementModal.syncRoleAria', { roleName: role.role_name })"
                  >
                    {{ $t('roleManagementModal.sync') }}
                  </button>
                  <button
                    v-if="role.assignment_type === 'manual'"
                    class="btn btn-sm btn-danger"
                    :disabled="isSaving || isRemoving"
                    @click="handleRemoveRole(role.role_name)"
                    :aria-label="$t('roleManagementModal.removeRoleAria', { roleName: role.role_name })"
                  >
                    {{ $t('roleManagementModal.remove') }}
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
          <div v-else class="empty-message">
            {{ $t('roleManagementModal.noRolesAssignedTo') }}
          </div>
        </section>

        <!-- Assign Role Section -->
        <section class="section" :aria-label="$t('roleManagementModal.assignRole')">
          <h4>{{ $t('roleManagementModal.assignRoleManually') }}</h4>
          <div class="assign-form">
            <label for="role-select" class="sr-only">{{ $t('roleManagementModal.selectARoleTo') }}</label>
            <select id="role-select" v-model="selectedRole" class="role-select">
              <option value="">{{ $t('roleManagementModal.selectARole') }}</option>
              <option
                v-for="role in availableRoles"
                :key="role.name"
                :value="role.name"
              >
                {{ role.display_name || role.name }}
              </option>
            </select>
            <button
              class="btn btn-primary"
              :disabled="!selectedRole || isSaving"
              @click="handleAssignRole"
            >
              {{ $t('roleManagementModal.assign') }}
            </button>
          </div>
        </section>

        <!-- Listening Ports -->
        <section class="section" v-if="nodeRoles?.listening_ports?.length" :aria-label="$t('roleManagementModal.listeningPorts2')">
          <h4>{{ $t('roleManagementModal.listeningPorts') }}</h4>
          <div class="port-list">
            <span
              v-for="port in nodeRoles.listening_ports"
              :key="port.port"
              class="port-badge"
            >
              {{ port.port }}
              <span v-if="port.process" class="port-process">({{ port.process }})</span>
            </span>
          </div>
        </section>

        <!-- Remove Confirmation Dialog (Issue #1041) -->
        <div v-if="showRemoveConfirm" class="confirm-overlay">
          <div class="confirm-dialog" role="alertdialog" aria-labelledby="confirm-title">
            <h4 id="confirm-title">{{ $t('roleManagementModal.removeValue0', { value0: roleToRemove }) }}</h4>
            <p v-if="isDataBearingRole" class="confirm-warning">
              {{ $t('roleManagementModal.thisRoleMayContain') }}
            </p>
            <p v-else class="confirm-text">
              {{ $t('roleManagementModal.thisWillStopAnd') }}
            </p>
            <div class="confirm-actions">
              <button
                v-if="isDataBearingRole"
                class="btn btn-sm btn-primary"
                @click="confirmRemove(true)"
              >
                {{ $t('roleManagementModal.backupAmpRemove') }}
              </button>
              <button
                class="btn btn-sm btn-danger"
                @click="confirmRemove(false)"
              >
                {{ isDataBearingRole ? $t('roleManagementModal.removeWithoutBackup') : $t('roleManagementModal.remove') }}
              </button>
              <button class="btn btn-sm btn-secondary" @click="cancelRemove">
                {{ $t('roleManagementModal.cancel') }}
              </button>
            </div>
          </div>
        </div>

        <!-- Sync / Status Message -->
        <div v-if="syncMessage" class="sync-message" role="status">
          {{ syncMessage }}
        </div>
      </div>

      <div class="modal-footer">
        <button class="btn btn-secondary" @click="emit('close')">{{ $t('roleManagementModal.close') }}</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: var(--z-modal);
}

.modal-content {
  background: var(--bg-secondary);
  color: var(--text-primary);
  border-radius: var(--radius-lg);
  width: 600px;
  max-width: 90vw;
  max-height: 80vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.modal-header {
  display: flex;
  align-items: center;
  padding: var(--spacing-4) var(--spacing-5);
  border-bottom: 1px solid var(--border-color);
}

.modal-header h3 {
  margin: 0;
  flex: 1;
  color: var(--text-primary);
}

.hostname {
  color: var(--text-muted);
  margin-right: var(--spacing-4);
}

.close-btn {
  background: none;
  border: none;
  font-size: var(--text-2xl);
  cursor: pointer;
  color: var(--text-muted);
}

.modal-body {
  padding: var(--spacing-5);
  overflow-y: auto;
  flex: 1;
}

.loading {
  padding: var(--spacing-10);
  text-align: center;
  color: var(--text-muted);
}

.section {
  margin-bottom: var(--spacing-6);
}

.section h4 {
  margin: 0 0 var(--spacing-3) 0;
  color: var(--text-secondary);
  font-size: var(--text-sm);
  text-transform: uppercase;
}

.empty-message {
  color: var(--text-muted);
  font-style: italic;
}

.role-list {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-2);
}

.role-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2) var(--spacing-3);
  background: var(--bg-tertiary);
  border-radius: var(--radius-default);
}

.role-name {
  font-weight: 500;
  color: var(--text-primary);
}

.role-badge {
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 3px;
  text-transform: uppercase;
}

.role-badge.auto {
  background: var(--info-bg);
  color: var(--info-color);
}

.role-badge.manual {
  background: var(--warning-bg);
  color: var(--warning-color);
}

.role-table {
  width: 100%;
  border-collapse: collapse;
}

.role-table th,
.role-table td {
  padding: var(--spacing-2) var(--spacing-3);
  text-align: left;
  border-bottom: 1px solid var(--border-color);
}

.role-table td {
  color: var(--text-primary);
}

.role-table th {
  color: var(--text-muted);
  font-weight: 500;
  font-size: var(--text-xs);
  text-transform: uppercase;
}

.status {
  display: inline-block;
  padding: 2px var(--spacing-2);
  border-radius: 3px;
  font-size: var(--text-xs);
}

.status-active {
  background: var(--success-bg);
  color: var(--success-color);
}

.status-inactive {
  background: var(--warning-bg);
  color: var(--warning-color);
}

.status-not-installed {
  background: var(--bg-tertiary);
  color: var(--text-muted);
}

.actions {
  display: flex;
  gap: var(--spacing-2);
}

.assign-form {
  display: flex;
  gap: var(--spacing-3);
}

.role-select {
  flex: 1;
  padding: var(--spacing-2) var(--spacing-3);
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-default);
  color: var(--text-primary);
}

.port-list {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-2);
}

.port-badge {
  padding: var(--spacing-1) var(--spacing-2);
  background: var(--bg-tertiary);
  color: var(--text-primary);
  border-radius: var(--radius-default);
  font-family: monospace;
}

.port-process {
  color: var(--text-muted);
  font-size: var(--text-xs);
}

.sync-message {
  margin-top: var(--spacing-4);
  padding: var(--spacing-3);
  background: var(--info-bg);
  border-radius: var(--radius-default);
  color: var(--info-color);
}

.modal-footer {
  padding: var(--spacing-4) var(--spacing-5);
  border-top: 1px solid var(--border-color);
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-3);
}

.btn {
  padding: var(--spacing-2) var(--spacing-4);
  border: none;
  border-radius: var(--radius-default);
  cursor: pointer;
  font-weight: 500;
}

.btn-sm {
  padding: var(--spacing-1) var(--spacing-2);
  font-size: var(--text-xs);
}

.btn-primary {
  background: var(--primary-color);
  color: white;
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-secondary {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.btn-danger {
  background: var(--danger-color);
  color: white;
}

/* Removal confirmation dialog (Issue #1041) */
.confirm-overlay {
  margin-top: var(--spacing-4);
  padding: var(--spacing-4);
  background: var(--bg-tertiary);
  border: 1px solid var(--danger-color);
  border-radius: var(--radius-md);
}

.confirm-dialog h4 {
  margin: 0 0 var(--spacing-2) 0;
  color: var(--text-primary);
  font-size: var(--text-sm);
}

.confirm-warning {
  margin: 0 0 var(--spacing-3) 0;
  color: var(--warning-color);
  font-size: 13px;
}

.confirm-text {
  margin: 0 0 var(--spacing-3) 0;
  color: var(--text-muted);
  font-size: 13px;
}

.confirm-actions {
  display: flex;
  gap: var(--spacing-2);
  flex-wrap: wrap;
}

/* Screen reader only utility (Issue #754) */
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border-width: 0;
}
</style>
