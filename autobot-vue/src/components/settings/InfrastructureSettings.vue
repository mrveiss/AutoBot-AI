<template>
  <div class="infrastructure-settings">
    <!-- Sub-tabs for Infrastructure -->
    <div class="infrastructure-tabs">
      <button
        class="infrastructure-tab"
        :class="{ active: activeSubTab === 'updates' }"
        @click="activeSubTab = 'updates'"
      >
        <i class="fas fa-download mr-2"></i>
        System Updates
      </button>
      <button
        class="infrastructure-tab"
        :class="{ active: activeSubTab === 'npu-workers' }"
        @click="activeSubTab = 'npu-workers'"
      >
        <i class="fas fa-microchip mr-2"></i>
        NPU Workers
      </button>
    </div>

    <!-- System Updates Tab -->
    <div v-show="activeSubTab === 'updates'">
    <!-- System Updates (Admin Only) - Issue #544 -->
    <div v-if="userStore.isAdmin" class="settings-section">
      <h4>System Updates</h4>
      <div class="updates-settings">
        <div class="updates-status">
          <div class="status-indicator" :class="updatesStatus.hasUpdates ? 'has-updates' : 'up-to-date'">
            <i :class="updatesStatus.hasUpdates ? 'fas fa-arrow-circle-up' : 'fas fa-check-circle'"></i>
            <span>{{ updatesStatus.hasUpdates ? 'Updates Available' : 'System Up to Date' }}</span>
          </div>
          <p class="status-message">{{ updatesStatus.message }}</p>
        </div>

        <div v-if="updatesStatus.pythonCount > 0 || updatesStatus.systemCount > 0" class="updates-info">
          <p v-if="updatesStatus.pythonCount > 0">
            <strong>Python Dependencies:</strong> {{ updatesStatus.pythonCount }} packages need updating
          </p>
          <p v-if="updatesStatus.systemCount > 0">
            <strong>System Packages:</strong> {{ updatesStatus.systemCount }} packages need updating
          </p>
        </div>

        <div class="updates-actions">
          <button
            @click="checkForUpdates"
            class="check-updates-btn"
            :disabled="isCheckingUpdates"
          >
            <i :class="isCheckingUpdates ? 'fas fa-spinner fa-spin' : 'fas fa-search'"></i>
            {{ isCheckingUpdates ? 'Checking...' : 'Check for Updates' }}
          </button>
          <button
            @click="showUpdateModal = true"
            class="run-updates-btn"
            :disabled="isRunningUpdate"
          >
            <i :class="isRunningUpdate ? 'fas fa-spinner fa-spin' : 'fas fa-download'"></i>
            {{ isRunningUpdate ? 'Updating...' : 'Run Updates' }}
          </button>
        </div>

        <!-- Progress indicator during updates -->
        <div v-if="updateTaskId" class="update-progress">
          <div class="progress-header">
            <span>Update Progress</span>
            <span class="task-status" :class="updateTaskStatus">{{ updateTaskStatus }}</span>
          </div>
          <div v-if="updateProgressInfo" class="progress-details">
            <p v-if="updateProgressInfo.task_name">Current task: {{ updateProgressInfo.task_name }}</p>
            <p v-if="updateProgressInfo.host">Host: {{ updateProgressInfo.host }}</p>
          </div>
        </div>
      </div>
    </div>

    <!-- Non-Admin Notice -->
    <div v-else class="settings-section">
      <div class="alert alert-info">
        <i class="fas fa-info-circle"></i>
        <span>Infrastructure management requires administrator privileges.</span>
      </div>
    </div>

    <!-- System Updates Modal - Issue #544 -->
    <BaseModal
      v-model="showUpdateModal"
      title="Run System Updates"
      size="medium"
      :closeOnOverlay="!isRunningUpdate"
    >
      <div class="update-modal">
        <div class="alert alert-warning">
          <i class="fas fa-exclamation-triangle"></i>
          <div>
            <strong>System Updates</strong>
            <p>This will update packages across the AutoBot infrastructure using Ansible. Services may be briefly interrupted during the update process.</p>
          </div>
        </div>

        <div class="form-group">
          <label for="updateType">Update Type</label>
          <select
            id="updateType"
            v-model="updateOptions.updateType"
            class="form-control"
            :disabled="isRunningUpdate"
          >
            <option value="dependencies">Python Dependencies (pip)</option>
            <option value="system">System Packages (apt)</option>
          </select>
        </div>

        <div class="form-group">
          <label>
            <input
              type="checkbox"
              v-model="updateOptions.dryRun"
              :disabled="isRunningUpdate"
            />
            Dry Run (preview changes without applying)
          </label>
        </div>

        <div class="form-group">
          <label>
            <input
              type="checkbox"
              v-model="updateOptions.forceUpdate"
              :disabled="isRunningUpdate"
            />
            Force Update (skip version checks)
          </label>
        </div>

        <!-- Progress indicator during update -->
        <div v-if="isRunningUpdate && updateTaskId" class="progress-section">
          <div class="progress-header">
            <i class="fas fa-spinner fa-spin"></i>
            <span class="status-text">{{ updateStatusMessage }}</span>
          </div>
          <div v-if="updateProgressInfo" class="progress-details">
            <p v-if="updateProgressInfo.task_name"><strong>Task:</strong> {{ updateProgressInfo.task_name }}</p>
            <p v-if="updateProgressInfo.host"><strong>Host:</strong> {{ updateProgressInfo.host }}</p>
          </div>
          <div class="task-info">
            <span class="task-id">Task ID: {{ updateTaskId.substring(0, 8) }}...</span>
            <span class="task-status-badge" :class="updateTaskStatus.toLowerCase()">{{ updateTaskStatus }}</span>
          </div>
        </div>

        <!-- Result message -->
        <div v-if="updateResult" class="alert" :class="updateResult.success ? 'alert-success' : 'alert-error'">
          <i :class="updateResult.success ? 'fas fa-check-circle' : 'fas fa-times-circle'"></i>
          {{ updateResult.message }}
        </div>
      </div>

      <template #actions>
        <button @click="showUpdateModal = false" class="cancel-btn" :disabled="isRunningUpdate">
          Cancel
        </button>
        <button @click="runSystemUpdate" class="save-btn" :disabled="isRunningUpdate">
          <i :class="isRunningUpdate ? 'fas fa-spinner fa-spin' : 'fas fa-download'"></i>
          {{ isRunningUpdate ? 'Updating...' : (updateOptions.dryRun ? 'Preview Updates' : 'Run Updates') }}
        </button>
      </template>
    </BaseModal>
    </div>

    <!-- NPU Workers Tab -->
    <div v-show="activeSubTab === 'npu-workers'">
      <NPUWorkersSettings :isSettingsLoaded="isSettingsLoaded" @change="$emit('change')" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useUserStore } from '../../stores/useUserStore'
import BaseModal from '@/components/ui/BaseModal.vue'
import NPUWorkersSettings from './NPUWorkersSettings.vue'
import { createLogger } from '@/utils/debugUtils'
import { getBackendUrl } from '@/config/ssot-config'

const logger = createLogger('InfrastructureSettings')
const userStore = useUserStore()

// Sub-tab state
const activeSubTab = ref<'updates' | 'npu-workers'>('updates')

// Props
interface Props {
  isSettingsLoaded?: boolean
}

const props = defineProps<Props>()

// Emits
const emit = defineEmits<{
  'setting-changed': [key: string, value: any]
  'change': []
}>()

// System Updates State (Issue #544)
const MAX_UPDATE_POLL_ATTEMPTS = 300 // 5 minutes max polling (300 * 1000ms)
const showUpdateModal = ref(false)
const isCheckingUpdates = ref(false)
const isRunningUpdate = ref(false)
const updateTaskId = ref<string | null>(null)
const updateTaskStatus = ref('')
const updatePollAttempts = ref(0)
const updateProgressInfo = ref<{ task_name?: string; host?: string } | null>(null)
const updateResult = ref<{ success: boolean; message: string } | null>(null)
const updatesStatus = reactive({
  hasUpdates: false,
  message: 'Click "Check for Updates" to scan for available updates',
  pythonCount: 0,
  systemCount: 0,
})
const updateOptions = reactive({
  updateType: 'dependencies' as 'dependencies' | 'system',
  dryRun: false,
  forceUpdate: false,
})

// Computed status message for better UX (Issue #544)
const updateStatusMessage = computed(() => {
  if (!updateTaskId.value) return 'Preparing...'
  switch (updateTaskStatus.value) {
    case 'PENDING':
      return 'Task queued, waiting for worker...'
    case 'PROGRESS':
      return updateProgressInfo.value?.task_name || 'Running update playbook...'
    case 'SUCCESS':
      return 'System update complete!'
    case 'FAILURE':
      return 'System update failed'
    default:
      return `Status: ${updateTaskStatus.value || 'Waiting...'}`
  }
})

// System Updates Methods (Issue #544)
const resetUpdateState = () => {
  updateTaskId.value = null
  updateTaskStatus.value = ''
  updatePollAttempts.value = 0
  updateProgressInfo.value = null
  updateResult.value = null
}

// Track polling attempts for update check
let updateCheckPollAttempts = 0
const MAX_CHECK_POLL_ATTEMPTS = 60 // 1 minute max for check operation

const checkForUpdates = async () => {
  if (!userStore.isAdmin) return

  isCheckingUpdates.value = true
  updatesStatus.message = 'Checking for updates...'

  try {
    // Trigger the check task
    const response = await fetch(`${getBackendUrl()}/api/settings/updates/check`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${userStore.authState.token}`,
      },
    })

    if (response.ok) {
      const data = await response.json()
      // Poll for results
      await pollUpdateCheckStatus(data.task_id)
    } else {
      updatesStatus.message = 'Failed to start update check'
      isCheckingUpdates.value = false
    }
  } catch (error) {
    logger.error('Error checking for updates:', error)
    updatesStatus.message = 'Error checking for updates'
    isCheckingUpdates.value = false
  }
}

const pollUpdateCheckStatus = async (taskId: string) => {
  // Check for polling timeout
  updateCheckPollAttempts++
  if (updateCheckPollAttempts > MAX_CHECK_POLL_ATTEMPTS) {
    logger.warn('Update check polling timeout reached after %d attempts', MAX_CHECK_POLL_ATTEMPTS)
    updatesStatus.message = 'Check timeout - please try again'
    isCheckingUpdates.value = false
    updateCheckPollAttempts = 0
    return
  }

  try {
    const response = await fetch(
      `${getBackendUrl()}/api/settings/updates/status/${taskId}`,
      {
        headers: {
          'Authorization': `Bearer ${userStore.authState.token}`,
        },
      }
    )

    if (response.ok) {
      const data = await response.json()

      if (data.status === 'SUCCESS') {
        const result = data.result
        updatesStatus.pythonCount = result.python_update_count || 0
        updatesStatus.systemCount = result.system_update_count || 0
        updatesStatus.hasUpdates = updatesStatus.pythonCount > 0 || updatesStatus.systemCount > 0
        updatesStatus.message = result.message || 'Update check complete'
        isCheckingUpdates.value = false
        updateCheckPollAttempts = 0
      } else if (data.status === 'FAILURE') {
        updatesStatus.message = data.error || 'Update check failed'
        isCheckingUpdates.value = false
        updateCheckPollAttempts = 0
      } else {
        // Continue polling
        setTimeout(() => pollUpdateCheckStatus(taskId), 1000)
      }
    } else {
      updatesStatus.message = 'Error checking task status'
      isCheckingUpdates.value = false
      updateCheckPollAttempts = 0
    }
  } catch (error) {
    logger.error('Error polling update check status:', error)
    updatesStatus.message = 'Lost connection while checking'
    isCheckingUpdates.value = false
    updateCheckPollAttempts = 0
  }
}

const runSystemUpdate = async () => {
  if (!userStore.isAdmin) return

  resetUpdateState()
  isRunningUpdate.value = true

  try {
    const response = await fetch(`${getBackendUrl()}/api/settings/updates/run`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${userStore.authState.token}`,
      },
      body: JSON.stringify({
        update_type: updateOptions.updateType,
        dry_run: updateOptions.dryRun,
        force_update: updateOptions.forceUpdate,
      }),
    })

    if (response.ok) {
      const data = await response.json()
      updateTaskId.value = data.task_id
      updateTaskStatus.value = 'PENDING'

      // Start polling for task status
      pollUpdateTaskStatus()
    } else {
      const error = await response.json()
      updateResult.value = {
        success: false,
        message: error.detail || 'Failed to start system update',
      }
      isRunningUpdate.value = false
    }
  } catch (error) {
    logger.error('Error running system update:', error)
    updateResult.value = {
      success: false,
      message: 'Error connecting to server',
    }
    isRunningUpdate.value = false
  }
}

const pollUpdateTaskStatus = async () => {
  if (!updateTaskId.value) return

  // Check for polling timeout
  updatePollAttempts.value++
  if (updatePollAttempts.value > MAX_UPDATE_POLL_ATTEMPTS) {
    logger.warn('Update polling timeout reached after %d attempts', MAX_UPDATE_POLL_ATTEMPTS)
    updateResult.value = {
      success: false,
      message: 'Polling timeout reached. The update may still be running. Please check logs.',
    }
    isRunningUpdate.value = false
    return
  }

  try {
    const response = await fetch(
      `${getBackendUrl()}/api/settings/updates/status/${updateTaskId.value}`,
      {
        headers: {
          'Authorization': `Bearer ${userStore.authState.token}`,
        },
      }
    )

    if (response.ok) {
      const data = await response.json()
      updateTaskStatus.value = data.status

      if (data.status === 'PROGRESS') {
        updateProgressInfo.value = data.progress
        setTimeout(pollUpdateTaskStatus, 1000)
      } else if (data.status === 'SUCCESS') {
        const result = data.result
        updateResult.value = {
          success: true,
          message: result?.message || 'System update completed successfully',
        }
        isRunningUpdate.value = false
        // Refresh update status
        await checkForUpdates()
      } else if (data.status === 'FAILURE') {
        updateResult.value = {
          success: false,
          message: data.error || 'System update failed',
        }
        isRunningUpdate.value = false
      } else if (data.status === 'PENDING') {
        setTimeout(pollUpdateTaskStatus, 1000)
      }
    } else {
      logger.error('Update polling received error response: %d', response.status)
      updateResult.value = {
        success: false,
        message: `Failed to get task status (HTTP ${response.status})`,
      }
      isRunningUpdate.value = false
    }
  } catch (error) {
    logger.error('Error polling update task status:', error)
    updateResult.value = {
      success: false,
      message: 'Lost connection while checking task status',
    }
    isRunningUpdate.value = false
  }
}

onMounted(async () => {
  // Check auth from backend first (handles single_user mode auto-auth)
  if (!userStore.isAuthenticated) {
    await userStore.checkAuthFromBackend()
  }
})
</script>

<style scoped>
.infrastructure-settings {
  padding: 24px;
}

/* Infrastructure Sub-tabs */
.infrastructure-tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 24px;
  border-bottom: 2px solid #e9ecef;
  padding-bottom: 0;
}

.infrastructure-tab {
  padding: 12px 20px;
  border: none;
  background: transparent;
  color: #6c757d;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  border-bottom: 2px solid transparent;
  margin-bottom: -2px;
  display: flex;
  align-items: center;
}

.infrastructure-tab:hover {
  color: #495057;
  background: #f8f9fa;
}

.infrastructure-tab.active {
  color: #007bff;
  border-bottom-color: #007bff;
  background: transparent;
}

.infrastructure-settings h3 {
  color: #2c3e50;
  margin-bottom: 24px;
  font-size: 24px;
  font-weight: 600;
}

.settings-section {
  margin-bottom: 32px;
  background: #f8f9fa;
  border-radius: 8px;
  padding: 20px;
}

.settings-section h4 {
  color: #495057;
  margin-bottom: 16px;
  font-size: 18px;
  font-weight: 500;
}

/* Form Elements */
.form-group {
  margin-bottom: 16px;
}

.form-group label {
  display: block;
  margin-bottom: 4px;
  font-weight: 500;
  color: #495057;
}

.form-control {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid #ced4da;
  border-radius: 4px;
  font-size: 14px;
}

.form-control:disabled {
  background: #e9ecef;
  color: #6c757d;
}

/* Action Buttons */
.save-btn {
  background: #28a745;
  color: white;
  border: none;
  padding: 10px 16px;
  border-radius: 6px;
  cursor: pointer;
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 8px;
}

.cancel-btn {
  background: #6c757d;
  color: white;
  border: none;
  padding: 10px 16px;
  border-radius: 6px;
  cursor: pointer;
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 8px;
}

/* Alert messages */
.alert {
  padding: 12px 16px;
  border-radius: 6px;
  margin-bottom: 16px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.alert-success {
  background: #d4edda;
  border: 1px solid #c3e6cb;
  color: #155724;
}

.alert-error {
  background: #f8d7da;
  border: 1px solid #f5c6cb;
  color: #721c24;
}

.alert-info {
  background: #cce5ff;
  border: 1px solid #b8daff;
  color: #004085;
}

.alert-warning {
  background: #fff3cd;
  border: 1px solid #ffc107;
  color: #856404;
}

.alert i {
  font-size: 16px;
}

/* Status Indicator */
.status-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  margin-bottom: 8px;
}

.status-indicator.has-updates {
  color: #fd7e14;
}

.status-indicator.up-to-date {
  color: #28a745;
}

.status-message {
  color: #6c757d;
  font-size: 14px;
  margin: 0;
}

/* System Updates Settings (Issue #544) */
.updates-settings {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.updates-status {
  padding: 16px;
  background: #e9ecef;
  border-radius: 8px;
}

.updates-info {
  padding: 12px;
  background: #fff3cd;
  border-radius: 6px;
  font-size: 14px;
}

.updates-info p {
  margin: 4px 0;
}

.updates-actions {
  display: flex;
  gap: 12px;
}

.check-updates-btn {
  background: #17a2b8;
  color: white;
  border: none;
  padding: 10px 16px;
  border-radius: 6px;
  cursor: pointer;
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 8px;
}

.check-updates-btn:hover:not(:disabled) {
  background: #138496;
}

.run-updates-btn {
  background: #28a745;
  color: white;
  border: none;
  padding: 10px 16px;
  border-radius: 6px;
  cursor: pointer;
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 8px;
}

.run-updates-btn:hover:not(:disabled) {
  background: #218838;
}

.update-progress {
  padding: 12px;
  background: #e3f2fd;
  border-radius: 6px;
  border-left: 4px solid #2196f3;
}

.progress-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 500;
}

.task-status {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 4px;
  text-transform: uppercase;
}

.task-status.PENDING {
  background: #ffc107;
  color: #212529;
}

.task-status.PROGRESS {
  background: #17a2b8;
  color: white;
}

.task-status.SUCCESS {
  background: #28a745;
  color: white;
}

.task-status.FAILURE {
  background: #dc3545;
  color: white;
}

.progress-details {
  margin-top: 8px;
  font-size: 14px;
  color: #495057;
}

/* Progress section for modals (Issue #544) */
.progress-section {
  margin: 16px 0;
  padding: 16px;
  background: linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%);
  border-radius: 8px;
  border-left: 4px solid #2196f3;
}

.progress-section .progress-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.progress-section .status-text {
  font-weight: 500;
  color: #1565c0;
}

.progress-section .task-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid rgba(33, 150, 243, 0.2);
}

.progress-section .task-id {
  font-family: monospace;
  font-size: 12px;
  color: #546e7a;
}

.task-status-badge {
  font-size: 11px;
  padding: 3px 10px;
  border-radius: 12px;
  text-transform: uppercase;
  font-weight: 600;
}

.task-status-badge.pending {
  background: #fff3cd;
  color: #856404;
}

.task-status-badge.progress {
  background: #17a2b8;
  color: white;
}

.task-status-badge.success {
  background: #28a745;
  color: white;
}

.task-status-badge.failure {
  background: #dc3545;
  color: white;
}

.update-modal .alert {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}

/* Disabled button styles */
button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* Dark theme support */
@media (prefers-color-scheme: dark) {
  .infrastructure-settings h3,
  .settings-section h4 {
    color: #ffffff;
  }

  .settings-section {
    background: #2d2d2d;
  }

  .form-group label {
    color: #ffffff;
  }

  .form-control {
    background: #3d3d3d;
    border-color: #555;
    color: #ffffff;
  }

  .updates-status {
    background: #383838;
  }

  .status-message {
    color: #b0b0b0;
  }
}

/* Mobile responsive */
@media (max-width: 768px) {
  .infrastructure-settings {
    padding: 16px;
  }

  .updates-actions {
    flex-direction: column;
  }

  .check-updates-btn,
  .run-updates-btn {
    width: 100%;
    justify-content: center;
  }
}
</style>
