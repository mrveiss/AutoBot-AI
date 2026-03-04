<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Decommission Modal (Issue #1369)
 *
 * Shows preflight role-dependency checks, allows the user to
 * migrate required roles, and requires type-to-confirm before
 * permanently removing a node from the fleet.
 */

import { ref, computed, onMounted } from 'vue'
import {
  useRoles,
  type DecommissionPreflight,
} from '@/composables/useRoles'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('DecommissionModal')

const props = defineProps<{
  node: { node_id: string; hostname: string; ip_address: string }
}>()

const emit = defineEmits<{
  close: []
  decommissioned: []
}>()

const { decommissionPreflight, decommissionNode } = useRoles()

type ModalState =
  | 'loading'
  | 'blocked'
  | 'ready'
  | 'running'
  | 'complete'
  | 'failed'

const state = ref<ModalState>('loading')
const preflight = ref<DecommissionPreflight | null>(null)
const backupEnabled = ref(true)
const confirmInput = ref('')
const errorMessage = ref('')

const canDecommission = computed(() => {
  return (
    state.value === 'ready' &&
    (preflight.value?.must_migrate.length ?? 0) === 0 &&
    confirmInput.value === props.node.node_id
  )
})

onMounted(async () => {
  const result = await decommissionPreflight(props.node.node_id)
  if (!result) {
    errorMessage.value = 'Failed to fetch preflight data'
    state.value = 'failed'
    return
  }

  preflight.value = result

  if (result.must_migrate.length > 0) {
    state.value = 'blocked'
  } else {
    state.value = 'ready'
  }

  logger.info(
    'Preflight loaded:',
    result.must_migrate.length,
    'must-migrate,',
    result.should_migrate.length,
    'should-migrate,',
    result.safe_to_remove.length,
    'safe-to-remove'
  )
})

async function handleDecommission() {
  if (!canDecommission.value) return

  state.value = 'running'
  errorMessage.value = ''

  const result = await decommissionNode(
    props.node.node_id,
    backupEnabled.value,
    confirmInput.value
  )

  if (result.success) {
    state.value = 'complete'
    logger.info('Node decommissioned:', props.node.node_id)
  } else {
    errorMessage.value =
      result.message || 'Decommission failed unexpectedly'
    state.value = 'failed'
    logger.warn('Decommission failed:', errorMessage.value)
  }
}

function handleMigrateClick() {
  emit('close')
}
</script>

<template>
  <div
    class="modal-overlay"
    @click.self="emit('close')"
    @keydown.escape="emit('close')"
    role="dialog"
    aria-modal="true"
    aria-labelledby="decommission-title"
  >
    <div class="modal-content">
      <!-- Header -->
      <div class="modal-header">
        <span class="header-icon" aria-hidden="true">&#9888;</span>
        <h3 id="decommission-title">
          Decommission Node: {{ node.hostname }}
        </h3>
        <button
          class="close-btn"
          @click="emit('close')"
          aria-label="Close decommission modal"
        >
          <span aria-hidden="true">&times;</span>
        </button>
      </div>

      <!-- Body -->
      <div class="modal-body">
        <!-- Loading -->
        <div v-if="state === 'loading'" class="loading" role="status">
          <span class="spinner" aria-hidden="true"></span>
          Checking role dependencies...
        </div>

        <!-- Preflight results (blocked or ready) -->
        <template
          v-if="state === 'blocked' || state === 'ready'"
        >
          <!-- Warning banner -->
          <div class="warning-banner">
            <p class="warning-text">
              This will permanently remove all AutoBot software
              and data from this node.
            </p>
            <p class="warning-ip">
              IP: <code>{{ node.ip_address }}</code>
            </p>
          </div>

          <!-- Must migrate (red) -->
          <div
            v-if="
              preflight &&
              preflight.must_migrate.length > 0
            "
            class="role-section role-section--danger"
          >
            <h4 class="section-title section-title--danger">
              Must migrate first
            </h4>
            <div
              v-for="role in preflight.must_migrate"
              :key="role.role_name"
              class="role-row"
            >
              <div class="role-info">
                <span class="role-name">
                  {{ role.display_name || role.role_name }}
                </span>
                <span class="role-reason">
                  {{ role.reason }}
                </span>
              </div>
              <button
                class="btn btn-sm btn-migrate"
                title="Close this modal and use Role Management to migrate this role"
                @click="handleMigrateClick"
              >
                Migrate
              </button>
            </div>
          </div>

          <!-- Should migrate (yellow) -->
          <div
            v-if="
              preflight &&
              preflight.should_migrate.length > 0
            "
            class="role-section role-section--warning"
          >
            <h4
              class="section-title section-title--warning"
            >
              Recommended to migrate
            </h4>
            <div
              v-for="role in preflight.should_migrate"
              :key="role.role_name"
              class="role-row"
            >
              <div class="role-info">
                <span class="role-name">
                  {{ role.display_name || role.role_name }}
                </span>
                <span class="role-reason">
                  {{ role.reason }}
                </span>
              </div>
            </div>
          </div>

          <!-- Safe to remove (green) -->
          <div
            v-if="
              preflight &&
              preflight.safe_to_remove.length > 0
            "
            class="role-section role-section--safe"
          >
            <h4 class="section-title section-title--safe">
              Safe to remove
            </h4>
            <div
              v-for="role in preflight.safe_to_remove"
              :key="role.role_name"
              class="role-row"
            >
              <div class="role-info">
                <span class="role-name">
                  {{ role.display_name || role.role_name }}
                </span>
                <span class="role-reason">
                  {{ role.reason }}
                </span>
              </div>
            </div>
          </div>

          <!-- Options -->
          <div class="options-section">
            <label class="checkbox-label">
              <input
                type="checkbox"
                v-model="backupEnabled"
              />
              Backup data before removal
            </label>
          </div>

          <!-- Confirm input -->
          <div class="confirm-section">
            <label
              for="confirm-node-id"
              class="confirm-label"
            >
              Type
              <code>{{ node.node_id }}</code>
              to confirm
            </label>
            <input
              id="confirm-node-id"
              v-model="confirmInput"
              type="text"
              class="confirm-input"
              :placeholder="node.node_id"
              autocomplete="off"
            />
          </div>
        </template>

        <!-- Running -->
        <div
          v-if="state === 'running'"
          class="status-block"
          role="status"
        >
          <span class="spinner" aria-hidden="true"></span>
          Decommissioning node...
        </div>

        <!-- Complete -->
        <div
          v-if="state === 'complete'"
          class="status-block status-block--success"
          role="status"
        >
          Node decommissioned successfully.
        </div>

        <!-- Failed -->
        <div
          v-if="state === 'failed'"
          class="status-block status-block--error"
          role="alert"
        >
          {{ errorMessage }}
        </div>
      </div>

      <!-- Footer -->
      <div class="modal-footer">
        <template v-if="state === 'complete'">
          <button
            class="btn btn-primary"
            @click="emit('decommissioned')"
          >
            Close
          </button>
        </template>
        <template v-else-if="state !== 'running'">
          <button
            class="btn btn-cancel"
            @click="emit('close')"
          >
            Cancel
          </button>
          <button
            class="btn btn-danger"
            :disabled="!canDecommission"
            @click="handleDecommission"
          >
            Decommission
          </button>
        </template>
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
  width: 540px;
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

.header-icon {
  font-size: 20px;
  color: #eab308;
  margin-right: 10px;
  flex-shrink: 0;
}

.modal-header h3 {
  margin: 0;
  flex: 1;
  font-size: 16px;
  color: var(--text-primary, #fff);
}

.close-btn {
  background: none;
  border: none;
  font-size: 24px;
  cursor: pointer;
  color: var(--text-muted, #888);
  flex-shrink: 0;
}

.modal-body {
  padding: 20px;
  overflow-y: auto;
  flex: 1;
}

.modal-footer {
  padding: 16px 20px;
  border-top: 1px solid var(--border-color, #333);
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}

/* Loading */
.loading {
  padding: 40px 0;
  text-align: center;
  color: var(--text-muted, #888);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
}

/* Spinner */
.spinner {
  display: inline-block;
  width: 18px;
  height: 18px;
  border: 2px solid var(--border-color, #333);
  border-top-color: var(--primary-color, #3b82f6);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

/* Warning banner */
.warning-banner {
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid #ef4444;
  border-radius: 6px;
  padding: 12px 16px;
  margin-bottom: 16px;
}

.warning-text {
  margin: 0 0 4px 0;
  font-weight: 500;
  color: #ef4444;
}

.warning-ip {
  margin: 0;
  color: var(--text-muted, #888);
  font-size: 13px;
}

.warning-ip code {
  color: var(--text-primary, #fff);
  font-family: monospace;
}

/* Role sections */
.role-section {
  margin-bottom: 16px;
  padding: 12px 16px;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.05);
}

.role-section--danger {
  border-left: 4px solid #ef4444;
}

.role-section--warning {
  border-left: 4px solid #eab308;
}

.role-section--safe {
  border-left: 4px solid #22c55e;
}

.section-title {
  margin: 0 0 10px 0;
  font-size: 13px;
  font-weight: 600;
  text-transform: uppercase;
}

.section-title--danger {
  color: #ef4444;
}

.section-title--warning {
  color: #eab308;
}

.section-title--safe {
  color: #22c55e;
}

.role-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 0;
}

.role-row + .role-row {
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}

.role-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.role-name {
  font-weight: 500;
  color: var(--text-primary, #fff);
  font-size: 14px;
}

.role-reason {
  color: var(--text-muted, #888);
  font-size: 12px;
}

/* Options */
.options-section {
  margin-bottom: 16px;
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  font-size: 14px;
  color: var(--text-primary, #fff);
}

.checkbox-label input[type='checkbox'] {
  accent-color: var(--primary-color, #3b82f6);
  width: 16px;
  height: 16px;
}

/* Confirm */
.confirm-section {
  margin-bottom: 8px;
}

.confirm-label {
  display: block;
  margin-bottom: 8px;
  font-size: 13px;
  color: var(--text-muted, #888);
}

.confirm-label code {
  color: var(--text-primary, #fff);
  font-family: monospace;
  background: rgba(255, 255, 255, 0.08);
  padding: 2px 6px;
  border-radius: 3px;
}

.confirm-input {
  width: 100%;
  padding: 8px 12px;
  border-radius: 4px;
  background: var(--bg-primary, #121220);
  color: var(--text-primary, #fff);
  border: 1px solid var(--border-color, #333);
  font-size: 14px;
  font-family: monospace;
  box-sizing: border-box;
}

.confirm-input:focus {
  outline: none;
  border-color: var(--primary-color, #3b82f6);
}

/* Status blocks (running / complete / failed) */
.status-block {
  padding: 40px 0;
  text-align: center;
  color: var(--text-muted, #888);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
}

.status-block--success {
  color: #22c55e;
  font-weight: 500;
}

.status-block--error {
  color: #ef4444;
  font-weight: 500;
}

/* Buttons */
.btn {
  padding: 8px 20px;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-weight: 500;
  font-size: 14px;
  transition: opacity 0.15s;
}

.btn-sm {
  padding: 4px 12px;
  font-size: 12px;
}

.btn-primary {
  background: var(--primary-color, #3b82f6);
  color: white;
}

.btn-danger {
  background: #ef4444;
  color: white;
}

.btn-danger:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-cancel {
  background: transparent;
  border: 1px solid var(--border-color, #333);
  color: var(--text-primary, #fff);
}

.btn-migrate {
  background: var(--primary-color, #3b82f6);
  color: white;
}
</style>
