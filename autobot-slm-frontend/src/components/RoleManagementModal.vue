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
  if (!dateStr) return 'Never'
  return new Date(dateStr).toLocaleString()
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
        <h3 id="role-mgmt-title">Role Management</h3>
        <span class="hostname">{{ hostname }}</span>
        <button class="close-btn" @click="emit('close')" aria-label="Close role management">
          <span aria-hidden="true">&times;</span>
        </button>
      </div>

      <div v-if="isLoading" class="loading" role="status">
        Loading role information...
      </div>

      <div v-else class="modal-body">
        <!-- Detected Roles Section -->
        <section class="section" aria-label="Auto-detected roles">
          <h4>Auto-Detected Roles</h4>
          <div v-if="detectedRolesList.length === 0" class="empty-message">
            No roles auto-detected on this node.
          </div>
          <div v-else class="role-list">
            <div
              v-for="roleName in detectedRolesList"
              :key="roleName"
              class="role-item detected"
            >
              <span class="role-name">{{ roleName }}</span>
              <span class="role-badge auto">auto</span>
            </div>
          </div>
        </section>

        <!-- All Role Statuses -->
        <section class="section" aria-label="Role status table">
          <h4>Role Status</h4>
          <table class="role-table" v-if="allNodeRoles.length > 0">
            <thead>
              <tr>
                <th scope="col">Role</th>
                <th scope="col">Status</th>
                <th scope="col">Version</th>
                <th scope="col">Last Synced</th>
                <th scope="col">Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="role in allNodeRoles" :key="role.role_name">
                <td>
                  {{ role.role_name }}
                  <span v-if="role.assignment_type === 'manual'" class="role-badge manual">
                    manual
                  </span>
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
                    :aria-label="`Sync ${role.role_name}`"
                  >
                    Sync
                  </button>
                  <button
                    v-if="role.assignment_type === 'manual'"
                    class="btn btn-sm btn-danger"
                    :disabled="isSaving || isRemoving"
                    @click="handleRemoveRole(role.role_name)"
                    :aria-label="`Remove ${role.role_name}`"
                  >
                    Remove
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
          <div v-else class="empty-message">
            No roles assigned to this node.
          </div>
        </section>

        <!-- Assign Role Section -->
        <section class="section" aria-label="Assign role">
          <h4>Assign Role Manually</h4>
          <div class="assign-form">
            <label for="role-select" class="sr-only">Select a role to assign</label>
            <select id="role-select" v-model="selectedRole" class="role-select">
              <option value="">Select a role...</option>
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
              Assign
            </button>
          </div>
        </section>

        <!-- Listening Ports -->
        <section class="section" v-if="nodeRoles?.listening_ports?.length" aria-label="Listening ports">
          <h4>Listening Ports</h4>
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
            <h4 id="confirm-title">Remove {{ roleToRemove }}?</h4>
            <p v-if="isDataBearingRole" class="confirm-warning">
              This role may contain data. You can back it up before removal.
            </p>
            <p v-else class="confirm-text">
              This will stop and remove the service from the node.
            </p>
            <div class="confirm-actions">
              <button
                v-if="isDataBearingRole"
                class="btn btn-sm btn-primary"
                @click="confirmRemove(true)"
              >
                Backup &amp; Remove
              </button>
              <button
                class="btn btn-sm btn-danger"
                @click="confirmRemove(false)"
              >
                {{ isDataBearingRole ? 'Remove without backup' : 'Remove' }}
              </button>
              <button class="btn btn-sm btn-secondary" @click="cancelRemove">
                Cancel
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
        <button class="btn btn-secondary" @click="emit('close')">Close</button>
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
  z-index: 1000;
}

.modal-content {
  background: var(--bg-secondary, #1e1e2e);
  color: var(--text-primary, #fff);
  border-radius: 8px;
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
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-color, #333);
}

.modal-header h3 {
  margin: 0;
  flex: 1;
  color: var(--text-primary, #fff);
}

.hostname {
  color: var(--text-muted, #888);
  margin-right: 16px;
}

.close-btn {
  background: none;
  border: none;
  font-size: 24px;
  cursor: pointer;
  color: var(--text-muted, #888);
}

.modal-body {
  padding: 20px;
  overflow-y: auto;
  flex: 1;
}

.loading {
  padding: 40px;
  text-align: center;
  color: var(--text-muted, #888);
}

.section {
  margin-bottom: 24px;
}

.section h4 {
  margin: 0 0 12px 0;
  color: var(--text-secondary, #aaa);
  font-size: 14px;
  text-transform: uppercase;
}

.empty-message {
  color: var(--text-muted, #888);
  font-style: italic;
}

.role-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.role-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: var(--bg-tertiary, #2a2a3e);
  border-radius: 4px;
}

.role-name {
  font-weight: 500;
  color: var(--text-primary, #fff);
}

.role-badge {
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 3px;
  text-transform: uppercase;
}

.role-badge.auto {
  background: var(--info-bg, #1e3a5f);
  color: var(--info-color, #60a5fa);
}

.role-badge.manual {
  background: var(--warning-bg, #5f4b1e);
  color: var(--warning-color, #fbbf24);
}

.role-table {
  width: 100%;
  border-collapse: collapse;
}

.role-table th,
.role-table td {
  padding: 8px 12px;
  text-align: left;
  border-bottom: 1px solid var(--border-color, #333);
}

.role-table td {
  color: var(--text-primary, #fff);
}

.role-table th {
  color: var(--text-muted, #888);
  font-weight: 500;
  font-size: 12px;
  text-transform: uppercase;
}

.status {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 3px;
  font-size: 12px;
}

.status-active {
  background: var(--success-bg, #1e5f3a);
  color: var(--success-color, #34d399);
}

.status-inactive {
  background: var(--warning-bg, #5f4b1e);
  color: var(--warning-color, #fbbf24);
}

.status-not-installed {
  background: var(--bg-tertiary, #2a2a3e);
  color: var(--text-muted, #888);
}

.actions {
  display: flex;
  gap: 8px;
}

.assign-form {
  display: flex;
  gap: 12px;
}

.role-select {
  flex: 1;
  padding: 8px 12px;
  background: var(--bg-tertiary, #2a2a3e);
  border: 1px solid var(--border-color, #333);
  border-radius: 4px;
  color: var(--text-primary, #fff);
}

.port-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.port-badge {
  padding: 4px 8px;
  background: var(--bg-tertiary, #2a2a3e);
  color: var(--text-primary, #fff);
  border-radius: 4px;
  font-family: monospace;
}

.port-process {
  color: var(--text-muted, #888);
  font-size: 12px;
}

.sync-message {
  margin-top: 16px;
  padding: 12px;
  background: var(--info-bg, #1e3a5f);
  border-radius: 4px;
  color: var(--info-color, #60a5fa);
}

.modal-footer {
  padding: 16px 20px;
  border-top: 1px solid var(--border-color, #333);
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}

.btn {
  padding: 8px 16px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-weight: 500;
}

.btn-sm {
  padding: 4px 8px;
  font-size: 12px;
}

.btn-primary {
  background: var(--primary-color, #3b82f6);
  color: white;
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-secondary {
  background: var(--bg-tertiary, #2a2a3e);
  color: var(--text-primary, #fff);
}

.btn-danger {
  background: var(--danger-color, #ef4444);
  color: white;
}

/* Removal confirmation dialog (Issue #1041) */
.confirm-overlay {
  margin-top: 16px;
  padding: 16px;
  background: var(--bg-tertiary, #2a2a3e);
  border: 1px solid var(--danger-color, #ef4444);
  border-radius: 6px;
}

.confirm-dialog h4 {
  margin: 0 0 8px 0;
  color: var(--text-primary, #fff);
  font-size: 14px;
}

.confirm-warning {
  margin: 0 0 12px 0;
  color: var(--warning-color, #fbbf24);
  font-size: 13px;
}

.confirm-text {
  margin: 0 0 12px 0;
  color: var(--text-muted, #888);
  font-size: 13px;
}

.confirm-actions {
  display: flex;
  gap: 8px;
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
