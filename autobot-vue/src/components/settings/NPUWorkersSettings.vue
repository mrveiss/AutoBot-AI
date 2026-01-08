<template>
  <div class="npu-workers-settings">
    <div class="settings-header">
      <div>
        <h3 class="text-xl font-semibold text-gray-800">NPU Worker Management</h3>
        <p class="text-sm text-gray-600 mt-1">Manage distributed NPU workers for AI processing</p>
      </div>
      <!-- Issue #641: Button text reflects new pairing flow -->
      <button @click="openAddWorkerDialog" class="btn-primary">
        <i class="fas fa-link mr-2"></i>
        Pair Worker
      </button>
    </div>

    <!-- Load Balancing Configuration -->
    <div class="config-section">
      <h4 class="section-title">
        <i class="fas fa-balance-scale mr-2"></i>
        Load Balancing Configuration
      </h4>
      <div class="config-grid">
        <div class="config-item">
          <label class="config-label">Strategy</label>
          <select v-model="loadBalancingConfig.strategy" @change="handleConfigChange" class="config-select">
            <option value="round-robin">Round Robin</option>
            <option value="least-loaded">Least Loaded</option>
            <option value="weighted">Weighted</option>
            <option value="priority">Priority Based</option>
          </select>
          <p class="config-help">Distribution strategy for task allocation</p>
        </div>
        <div class="config-item">
          <label class="config-label">Health Check Interval</label>
          <input
            v-model.number="loadBalancingConfig.health_check_interval"
            @input="handleConfigChange"
            type="number"
            min="5"
            max="300"
            class="config-input"
          />
          <p class="config-help">Seconds between health checks</p>
        </div>
      </div>
    </div>

    <!-- Workers List -->
    <div class="workers-section">
      <h4 class="section-title">
        <i class="fas fa-network-wired mr-2"></i>
        Registered Workers ({{ workers.length }})
      </h4>

      <!-- Loading State -->
      <div v-if="isLoading" class="loading-state">
        <i class="fas fa-spinner fa-spin text-3xl text-blue-500"></i>
        <p class="text-gray-600 mt-2">Loading workers...</p>
      </div>

      <!-- Empty State -->
      <EmptyState
        v-else-if="workers.length === 0"
        icon="fas fa-server"
        message="No NPU workers registered"
      >
        <!-- Issue #641: Updated button text for pairing flow -->
        <template #actions>
          <button @click="openAddWorkerDialog" class="btn-secondary mt-4">
            <i class="fas fa-link mr-2"></i>
            Pair Your First Worker
          </button>
        </template>
      </EmptyState>

      <!-- Workers Table -->
      <div v-else class="workers-table-container">
        <table class="workers-table">
          <thead>
            <tr>
              <th>Worker</th>
              <th>Platform</th>
              <th>Connection</th>
              <th>Status</th>
              <th>Load</th>
              <th>Uptime</th>
              <th>Priority</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="worker in workers" :key="worker.id" :class="getWorkerRowClass(worker)">
              <!-- Worker Name & ID -->
              <td>
                <div class="worker-info">
                  <div class="worker-name">{{ worker.name }}</div>
                  <div class="worker-id">{{ worker.id }}</div>
                </div>
              </td>

              <!-- Platform -->
              <td>
                <div class="platform-badge" :class="getPlatformClass(worker.platform)">
                  <i :class="getPlatformIcon(worker.platform)" class="mr-1"></i>
                  {{ worker.platform }}
                </div>
              </td>

              <!-- Connection -->
              <td>
                <div class="connection-info">
                  <div class="text-sm font-mono">{{ worker.ip_address }}:{{ worker.port }}</div>
                  <div class="text-xs text-gray-500">{{ worker.last_heartbeat }}</div>
                </div>
              </td>

              <!-- Status -->
              <td>
                <StatusBadge :variant="getStatusVariant(worker.status)" size="small">
                  <span class="status-dot" :class="getStatusDotClass(worker.status)"></span>
                  {{ worker.status }}
                </StatusBadge>
              </td>

              <!-- Load -->
              <td>
                <div class="load-info">
                  <div class="load-bar-container">
                    <div
                      class="load-bar"
                      :class="getLoadBarClass(worker.current_load)"
                      :style="{ width: worker.current_load + '%' }"
                    ></div>
                  </div>
                  <div class="load-text">{{ worker.current_load }}% / {{ worker.max_capacity }}</div>
                </div>
              </td>

              <!-- Uptime -->
              <td>
                <div class="uptime-info">{{ worker.uptime }}</div>
              </td>

              <!-- Priority & Weight -->
              <td>
                <div class="priority-info">
                  <div class="text-sm">P: {{ worker.priority }}</div>
                  <div class="text-xs text-gray-500">W: {{ worker.weight }}</div>
                </div>
              </td>

              <!-- Actions -->
              <td>
                <div class="action-buttons">
                  <button
                    @click="toggleWorkerEnabled(worker)"
                    :disabled="operationInProgress"
                    class="action-btn toggle-btn"
                    :class="worker.enabled ? 'toggle-enabled' : 'toggle-disabled'"
                    :title="worker.enabled ? 'Disable worker' : 'Enable worker'"
                  >
                    <i :class="worker.enabled ? 'fas fa-toggle-on' : 'fas fa-toggle-off'"></i>
                  </button>
                  <button
                    @click="testWorker(worker)"
                    :disabled="isTestingWorker[worker.id] || !worker.enabled"
                    class="action-btn test-btn"
                    :title="'Test connection to ' + worker.name"
                  >
                    <i :class="isTestingWorker[worker.id] ? 'fas fa-spinner fa-spin' : 'fas fa-plug'"></i>
                  </button>
                  <button
                    @click="viewWorkerMetrics(worker)"
                    class="action-btn metrics-btn"
                    :disabled="!worker.enabled"
                    title="View detailed metrics"
                  >
                    <i class="fas fa-chart-line"></i>
                  </button>
                  <button
                    @click="openLogLevelDialog(worker)"
                    class="action-btn log-btn"
                    :disabled="!worker.enabled"
                    title="Set log level (for debugging)"
                  >
                    <i class="fas fa-bug"></i>
                  </button>
                  <button
                    @click="editWorker(worker)"
                    class="action-btn edit-btn"
                    title="Edit worker configuration"
                  >
                    <i class="fas fa-edit"></i>
                  </button>
                  <button
                    @click="confirmDeleteWorker(worker)"
                    class="action-btn delete-btn"
                    title="Remove worker"
                  >
                    <i class="fas fa-trash"></i>
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Add/Edit Worker Dialog -->
    <!-- Issue #641: New workers are paired (main host contacts worker) -->
    <BaseModal
      :modelValue="showAddWorkerDialog || showEditWorkerDialog"
      @update:modelValue="val => !val && closeWorkerDialog()"
      :title="showEditWorkerDialog ? 'Edit Worker' : 'Pair New Worker'"
      size="medium"
      :closeOnOverlay="!isSavingWorker && !operationInProgress"
    >
      <!-- Error Alert -->
      <BaseAlert
        v-if="workerFormError"
        variant="error"
        :message="workerFormError"
      />

      <div class="form-group">
        <label class="form-label">Worker Name *</label>
        <input
          v-model="workerForm.name"
          type="text"
          class="form-input"
          placeholder="e.g., NPU-Worker-VM2"
          required
        />
      </div>

      <div class="form-row">
        <div class="form-group">
          <label class="form-label">Platform *</label>
          <select v-model="workerForm.platform" class="form-select">
            <option value="linux">Linux</option>
            <option value="windows">Windows</option>
            <option value="macos">macOS</option>
          </select>
        </div>

        <div class="form-group">
          <label class="form-label">IP Address *</label>
          <input
            v-model="workerForm.ip_address"
            type="text"
            class="form-input"
            :placeholder="NetworkConstants.NPU_WORKER_VM_IP"
            required
          />
        </div>

        <div class="form-group">
          <label class="form-label">Port *</label>
          <input
            v-model.number="workerForm.port"
            type="number"
            class="form-input"
            placeholder="8081"
            min="1"
            max="65535"
            required
          />
        </div>
      </div>

      <div class="form-row">
        <div class="form-group">
          <label class="form-label">Priority (1-10)</label>
          <input
            v-model.number="workerForm.priority"
            type="number"
            class="form-input"
            min="1"
            max="10"
          />
          <p class="form-help">Higher priority workers receive tasks first</p>
        </div>

        <div class="form-group">
          <label class="form-label">Weight</label>
          <input
            v-model.number="workerForm.weight"
            type="number"
            class="form-input"
            min="1"
            max="100"
          />
          <p class="form-help">Load balancing weight (higher = more tasks)</p>
        </div>
      </div>

      <template #actions>
        <button @click="closeWorkerDialog" class="btn-secondary">
          Cancel
        </button>
        <!-- Issue #641: Button text reflects pairing vs update -->
        <button
          @click="saveWorker"
          :disabled="!isWorkerFormValid || isSavingWorker || operationInProgress"
          class="btn-primary"
        >
          <i :class="isSavingWorker ? 'fas fa-spinner fa-spin mr-2' : (showEditWorkerDialog ? 'fas fa-save mr-2' : 'fas fa-link mr-2')"></i>
          {{ isSavingWorker ? (showEditWorkerDialog ? 'Saving...' : 'Pairing...') : (showEditWorkerDialog ? 'Save Worker' : 'Pair Worker') }}
        </button>
      </template>
    </BaseModal>

    <!-- Delete Confirmation Dialog -->
    <BaseModal
      v-model="showDeleteDialog"
      title="Confirm Deletion"
      size="small"
      :closeOnOverlay="!isDeletingWorker && !operationInProgress"
    >
      <template #title>
        <span class="text-red-700">
          <i class="fas fa-exclamation-triangle mr-2"></i>
          Confirm Deletion
        </span>
      </template>

      <p class="text-gray-700">
        Are you sure you want to remove worker <strong>{{ workerToDelete?.name }}</strong>?
      </p>
      <p class="text-sm text-gray-600 mt-2">
        This action cannot be undone.
      </p>

      <template #actions>
        <button @click="closeDeleteDialog" class="btn-secondary">
          Cancel
        </button>
        <button @click="deleteWorker" :disabled="isDeletingWorker || operationInProgress" class="btn-danger">
          <i :class="isDeletingWorker ? 'fas fa-spinner fa-spin mr-2' : 'fas fa-trash mr-2'"></i>
          {{ isDeletingWorker ? 'Deleting...' : 'Delete Worker' }}
        </button>
      </template>
    </BaseModal>

    <!-- Worker Metrics Modal -->
    <BaseModal
      v-if="selectedWorkerMetrics"
      v-model="showMetricsDialog"
      title="Worker Metrics"
      size="large"
    >
      <template #title>
        <i class="fas fa-chart-line mr-2"></i>
        Worker Metrics: {{ selectedWorkerMetrics.name }}
      </template>

      <div class="metrics-grid">
        <div class="metric-card">
          <div class="metric-label">CPU Usage</div>
          <div class="metric-value">{{ selectedWorkerMetrics.performance_metrics?.cpu_usage ?? 0 }}%</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">Memory Usage</div>
          <div class="metric-value">{{ selectedWorkerMetrics.performance_metrics?.memory_usage ?? 0 }}%</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">NPU Utilization</div>
          <div class="metric-value">{{ selectedWorkerMetrics.performance_metrics?.npu_utilization ?? 0 }}%</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">Tasks Completed</div>
          <div class="metric-value">{{ selectedWorkerMetrics.performance_metrics?.tasks_completed ?? 0 }}</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">Avg Response Time</div>
          <div class="metric-value">{{ selectedWorkerMetrics.performance_metrics?.avg_response_time ?? 0 }}ms</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">Error Rate</div>
          <div class="metric-value">{{ selectedWorkerMetrics.performance_metrics?.error_rate ?? 0 }}%</div>
        </div>
      </div>

      <template #actions>
        <button @click="closeMetricsDialog" class="btn-secondary">
          Close
        </button>
      </template>
    </BaseModal>

    <!-- Log Level Configuration Modal -->
    <BaseModal
      v-if="selectedLogLevelWorker"
      v-model="showLogLevelDialog"
      title="Worker Log Level"
      size="small"
    >
      <template #title>
        <i class="fas fa-bug mr-2"></i>
        Log Level: {{ selectedLogLevelWorker.name }}
      </template>

      <div class="log-level-config">
        <p class="text-sm text-gray-600 mb-4">
          Set the logging verbosity for debugging. Use DEBUG to capture detailed crash information.
        </p>

        <div class="form-group">
          <label class="form-label">Current Level</label>
          <div class="current-level-badge" :class="'level-' + currentLogLevel.toLowerCase()">
            {{ currentLogLevel }}
          </div>
        </div>

        <div class="form-group mt-4">
          <label class="form-label">Set New Level</label>
          <div class="log-level-buttons">
            <button
              v-for="level in logLevels"
              :key="level"
              @click="setLogLevel(level)"
              :disabled="isSettingLogLevel"
              class="log-level-btn"
              :class="{ 'active': currentLogLevel === level, 'level-debug': level === 'DEBUG' }"
            >
              {{ level }}
            </button>
          </div>
          <p class="form-help mt-2">
            <strong>DEBUG</strong>: Full details for crash investigation<br>
            <strong>INFO</strong>: Normal operation logs<br>
            <strong>WARNING</strong>: Potential issues only<br>
            <strong>ERROR</strong>: Errors only
          </p>
        </div>
      </div>

      <template #actions>
        <button @click="closeLogLevelDialog" class="btn-secondary">
          Close
        </button>
      </template>
    </BaseModal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import axios from 'axios'
import { NetworkConstants } from '@/constants/network'
import { useModal } from '@/composables/useModal'
import { useAsyncOperation } from '@/composables/useAsyncOperation'
import { useToast } from '@/composables/useToast'
import EmptyState from '@/components/ui/EmptyState.vue'
import StatusBadge from '@/components/ui/StatusBadge.vue'
import BaseAlert from '@/components/ui/BaseAlert.vue'
import BaseModal from '@/components/ui/BaseModal.vue'
import { createLogger } from '@/utils/debugUtils'

// Create scoped logger for NPUWorkersSettings
const logger = createLogger('NPUWorkersSettings')

// Toast notifications
const { showToast } = useToast()

// Notification helper for error handling
const notify = (message: string, type: 'info' | 'success' | 'warning' | 'error' = 'info') => {
  showToast(message, type, type === 'error' ? 5000 : 3000)
}

// ===== TYPE DEFINITIONS =====

interface NPUWorkerConfig {
  id: string
  name: string
  url: string
  platform: string
  priority: number
  weight: number
  max_concurrent_tasks: number
  enabled?: boolean
}

interface NPUWorkerStatus {
  status: string
  current_load: number
  uptime_seconds: number
  last_heartbeat: string | null
}

interface NPUWorkerMetrics {
  total_tasks?: number
  completed_tasks?: number
  failed_tasks?: number
  average_processing_time?: number
  cpu_usage?: number
  memory_usage?: number
  npu_utilization?: number
  tasks_completed?: number
  avg_response_time?: number
  error_rate?: number
}

interface NPUWorkerAPIResponse {
  config: NPUWorkerConfig
  status: NPUWorkerStatus
  metrics: NPUWorkerMetrics
}

interface NPUWorker {
  id: string
  name: string
  platform: string
  ip_address: string
  port: number
  status: string
  current_load: number
  max_capacity: number
  uptime: string
  performance_metrics: NPUWorkerMetrics
  priority: number
  weight: number
  last_heartbeat: string
  created_at: string
  enabled: boolean
}

interface WorkerForm {
  name: string
  platform: string
  ip_address: string
  port: number
  priority: number
  weight: number
}

interface LoadBalancingConfig {
  strategy: string
  health_check_interval: number
}

// Props
interface Props {
  isSettingsLoaded?: boolean
}

// Emits
interface Emits {
  (e: 'change'): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

// ===== STATE =====

const workers = ref<NPUWorker[]>([])
const workerToDelete = ref<NPUWorker | null>(null)
const selectedWorkerMetrics = ref<NPUWorker | null>(null)
const editingWorker = ref<NPUWorker | null>(null)
const isTestingWorker = ref<Record<string, boolean>>({})
const workerFormError = ref<string | null>(null)
const operationInProgress = ref(false)

// Issue #156 Fix: useModal expects ModalOptions object with id property
const { isOpen: showAddWorkerDialog, open: openAddWorkerDialog, close: closeAddWorkerDialog } = useModal({ id: 'add-worker' })
const { isOpen: showEditWorkerDialog, open: openEditWorkerDialog, close: closeEditWorkerDialog } = useModal({ id: 'edit-worker' })
const { isOpen: showDeleteDialog, open: openDeleteDialog, close: closeDeleteDialog } = useModal({ id: 'delete-worker' })
const { isOpen: showMetricsDialog, open: openMetricsDialog, close: closeMetricsDialog } = useModal({ id: 'metrics' })
const { isOpen: showLogLevelDialog, open: openLogLevelDialogModal, close: closeLogLevelDialogModal } = useModal({ id: 'log-level' })

// Log level configuration state
const selectedLogLevelWorker = ref<NPUWorker | null>(null)
const currentLogLevel = ref('INFO')
const isSettingLogLevel = ref(false)
const logLevels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']

// Use composables for async operations
const { execute: loadWorkersOp, loading: isLoading } = useAsyncOperation()
const { execute: saveWorkerOp, loading: isSavingWorker } = useAsyncOperation()
const { execute: deleteWorkerOp, loading: isDeletingWorker } = useAsyncOperation()

const loadBalancingConfig = ref<LoadBalancingConfig>({
  strategy: 'round-robin',
  health_check_interval: 30
})

const workerForm = ref<WorkerForm>({
  name: '',
  platform: 'linux',
  ip_address: '',
  port: 8081,
  priority: 5,
  weight: 1
})

// ===== HELPER FUNCTIONS =====

/**
 * Parse worker URL with proper error handling for IPv6, paths, and edge cases
 * Fixes C2: URL Parsing Vulnerability
 */
const parseWorkerURL = (urlString: string): { ip: string; port: number } => {
  try {
    const url = new URL(urlString)
    return {
      ip: url.hostname,
      port: parseInt(url.port) || 8081
    }
  } catch (error) {
    logger.error(`Invalid worker URL: ${urlString}`, error)
    // Fallback to regex parsing for non-standard URLs
    const match = urlString.match(/^(?:https?:\/\/)?(.+?):(\d+)/)
    if (match) {
      return { ip: match[1], port: parseInt(match[2]) }
    }
    return { ip: urlString, port: 8081 }
  }
}

/**
 * Validate IP address format (IPv4 and basic IPv6)
 * Additional validation for worker form submission
 */
const validateIPAddress = (ip: string): boolean => {
  // IPv4 validation
  const ipv4Regex = /^(\d{1,3}\.){3}\d{1,3}$/
  if (ipv4Regex.test(ip)) {
    return ip.split('.').every(octet => parseInt(octet) <= 255)
  }

  // IPv6 validation (basic)
  const ipv6Regex = /^([0-9a-fA-F]{0,4}:){7}[0-9a-fA-F]{0,4}$/
  if (ipv6Regex.test(ip)) {
    return true
  }

  // Allow localhost
  return ip === 'localhost'
}

/**
 * Generate unique worker ID with timestamp to prevent duplicates
 * Fixes C4: Duplicate Worker IDs
 */
const generateWorkerId = (name: string): string => {
  const baseName = name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .substring(0, 40) || 'npu-worker'

  // Add timestamp for uniqueness
  const timestamp = Date.now()
  return `${baseName}-${timestamp}`
}

const formatUptime = (seconds: number): string => {
  if (seconds < 60) return `${Math.floor(seconds)}s`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h`
  return `${Math.floor(seconds / 86400)}d`
}

// ===== COMPUTED =====

const isWorkerFormValid = computed(() => {
  return (
    workerForm.value?.name?.trim() !== '' &&
    workerForm.value?.ip_address?.trim() !== '' &&
    (workerForm.value?.port || 0) > 0 &&
    (workerForm.value?.port || 0) <= 65535
  )
})

// ===== METHODS =====

/**
 * Load workers with proper type safety
 * Fixes C1: Type Safety Violation
 */
const loadWorkers = async () => {
  try {
    isLoading.value = true
    const response = await axios.get<NPUWorkerAPIResponse[]>('/api/npu/workers')

    // Transform nested API response to flat structure with proper typing
    workers.value = response.data.map((worker: NPUWorkerAPIResponse): NPUWorker => {
      const { ip, port } = parseWorkerURL(worker.config.url)

      return {
        id: worker.config.id,
        name: worker.config.name,
        platform: worker.config.platform,
        ip_address: ip,
        port: port,
        status: worker.status.status || 'unknown',
        current_load: worker.status.current_load || 0,
        max_capacity: worker.config.max_concurrent_tasks || 4,
        uptime: worker.status.uptime_seconds ? formatUptime(worker.status.uptime_seconds) : 'N/A',
        performance_metrics: worker.metrics || {},
        priority: worker.config.priority,
        weight: worker.config.weight,
        last_heartbeat: worker.status.last_heartbeat
          ? new Date(worker.status.last_heartbeat).toLocaleString()
          : 'Never',
        created_at: new Date().toISOString(),
        enabled: worker.config.enabled !== false  // Default to true if not specified
      }
    })
  } catch (error) {
    logger.error('Failed to load NPU workers:', error)
    workerFormError.value = 'Failed to load workers. Please try again.'
    notify('Failed to load NPU workers', 'error')
  } finally {
    isLoading.value = false
  }
}

const loadLoadBalancingConfig = async () => {
  try {
    const response = await axios.get('/api/npu/load-balancing')
    loadBalancingConfig.value = response.data
  } catch (error) {
    logger.error('Failed to load load balancing config:', error)
    notify('Failed to load load balancing config', 'error')
  }
}

const handleConfigChange = async () => {
  try {
    await axios.put('/api/npu/load-balancing', loadBalancingConfig.value)
    emit('change')
    notify('Load balancing config updated', 'success')
  } catch (error) {
    logger.error('Failed to update load balancing config:', error)
    notify('Failed to update load balancing config', 'error')
  }
}

const editWorker = (worker: NPUWorker) => {
  editingWorker.value = worker
  workerForm.value = {
    name: worker.name,
    platform: worker.platform,
    ip_address: worker.ip_address,
    port: worker.port,
    priority: worker.priority,
    weight: worker.weight
  }
  openEditWorkerDialog()
}

/**
 * Save worker with operation locking and validation
 * Issue #641: New workers are added via /pair endpoint (main host contacts worker)
 * Fixes C3: Race Condition, C5: Silent Error Failures
 */
const saveWorker = async () => {
  if (operationInProgress.value) {
    workerFormError.value = 'Another operation is in progress. Please wait.'
    return
  }

  // Validate IP address before submission
  if (!validateIPAddress(workerForm.value.ip_address)) {
    workerFormError.value = 'Invalid IP address format'
    return
  }

  try {
    operationInProgress.value = true
    isSavingWorker.value = true
    workerFormError.value = null

    if (showEditWorkerDialog.value && editingWorker.value) {
      // Update existing worker - use PUT endpoint
      const workerPayload = {
        id: editingWorker.value.id,
        name: workerForm.value.name,
        url: `http://${workerForm.value.ip_address}:${workerForm.value.port}`,
        platform: workerForm.value.platform,
        enabled: true,
        priority: workerForm.value.priority,
        weight: workerForm.value.weight,
        max_concurrent_tasks: 4
      }
      await axios.put(`/api/npu/workers/${editingWorker.value.id}`, workerPayload)
      notify(`Worker "${workerForm.value.name}" updated`, 'success')
    } else {
      // Issue #641: Add new worker via /pair endpoint
      // Main host contacts worker and assigns permanent ID
      const pairPayload = {
        url: `http://${workerForm.value.ip_address}:${workerForm.value.port}`,
        name: workerForm.value.name,
        enabled: true
      }

      const response = await axios.post('/api/npu/workers/pair', pairPayload)

      if (response.data.success) {
        notify(`Worker "${workerForm.value.name}" paired successfully (ID: ${response.data.worker_id})`, 'success')
      } else {
        throw new Error(response.data.message || 'Pairing failed')
      }
    }

    emit('change')
    closeWorkerDialog()
    await loadWorkers()
  } catch (error: unknown) {
    logger.error('Failed to save worker:', error)

    // Extract error message from response
    const axiosError = error as { response?: { data?: { detail?: string; message?: string } }; message?: string }
    const errorMessage = axiosError.response?.data?.detail ||
                        axiosError.response?.data?.message ||
                        axiosError.message ||
                        'Failed to save worker'

    workerFormError.value = errorMessage
    notify(errorMessage, 'error')
  } finally {
    isSavingWorker.value = false
    operationInProgress.value = false
  }
}

const confirmDeleteWorker = (worker: NPUWorker) => {
  workerToDelete.value = worker
  openDeleteDialog()
}

/**
 * Delete worker with operation locking
 * Fixes C3: Race Condition
 */
const deleteWorker = async () => {
  if (!workerToDelete.value) return

  if (operationInProgress.value) {
    logger.warn('Operation already in progress')
    return
  }

  const workerName = workerToDelete.value.name

  try {
    operationInProgress.value = true
    isDeletingWorker.value = true
    await axios.delete(`/api/npu/workers/${workerToDelete.value.id}`)
    emit('change')
    showDeleteDialog.value = false
    workerToDelete.value = null
    notify(`Worker "${workerName}" deleted`, 'success')
    await loadWorkers()
  } catch (error) {
    logger.error('Failed to delete worker:', error)
    const axiosError = error as { response?: { data?: { detail?: string; message?: string } }; message?: string }
    const errorMessage = axiosError.response?.data?.detail ||
                        axiosError.response?.data?.message ||
                        axiosError.message ||
                        'Failed to delete worker'
    workerFormError.value = errorMessage
    notify(errorMessage, 'error')
  } finally {
    isDeletingWorker.value = false
    operationInProgress.value = false
  }
}

/**
 * Toggle worker enabled/disabled state
 * Calls PUT /api/npu/workers/{id} with updated enabled flag
 */
const toggleWorkerEnabled = async (worker: NPUWorker) => {
  if (operationInProgress.value) {
    logger.warn('Operation already in progress')
    return
  }

  const newEnabledState = !worker.enabled
  const action = newEnabledState ? 'enabled' : 'disabled'

  try {
    operationInProgress.value = true

    // Build worker payload with toggled enabled state
    const workerPayload = {
      id: worker.id,
      name: worker.name,
      url: `http://${worker.ip_address}:${worker.port}`,
      platform: worker.platform,
      enabled: newEnabledState,
      priority: worker.priority,
      weight: worker.weight,
      max_concurrent_tasks: worker.max_capacity
    }

    await axios.put(`/api/npu/workers/${worker.id}`, workerPayload)

    // Update local state immediately for responsive UI
    worker.enabled = newEnabledState

    emit('change')
    notify(`Worker "${worker.name}" ${action}`, 'success')
  } catch (error) {
    logger.error(`Failed to toggle worker ${worker.name}:`, error)
    const axiosError = error as { response?: { data?: { detail?: string; message?: string } }; message?: string }
    const errorMessage = axiosError.response?.data?.detail ||
                        axiosError.response?.data?.message ||
                        axiosError.message ||
                        `Failed to ${action.slice(0, -1)} worker`
    notify(errorMessage, 'error')
  } finally {
    operationInProgress.value = false
  }
}

const testWorker = async (worker: NPUWorker) => {
  try {
    isTestingWorker.value[worker.id] = true
    const response = await axios.post(`/api/npu/workers/${worker.id}/test`)

    if (response.data.success) {
      notify(`Worker "${worker.name}" connection OK`, 'success')
    } else {
      logger.error(`Worker ${worker.name} test failed:`, response.data)
      notify(`Worker "${worker.name}" test failed`, 'warning')
    }
  } catch (error) {
    logger.error(`Failed to test worker ${worker.name}:`, error)
    notify(`Failed to test worker "${worker.name}"`, 'error')
  } finally {
    isTestingWorker.value[worker.id] = false
  }
}

const viewWorkerMetrics = async (worker: NPUWorker) => {
  try {
    const response = await axios.get(`/api/npu/workers/${worker.id}/metrics`)
    selectedWorkerMetrics.value = { ...worker, performance_metrics: response.data }
    openMetricsDialog()
  } catch (error) {
    logger.error('Failed to load worker metrics:', error)
    notify(`Failed to load metrics for "${worker.name}"`, 'error')
  }
}

/**
 * Open log level configuration dialog for a worker
 * Fetches current log level from the worker
 */
const openLogLevelDialog = async (worker: NPUWorker) => {
  selectedLogLevelWorker.value = worker
  currentLogLevel.value = 'INFO' // Default while fetching

  try {
    const response = await axios.get(`/api/npu/workers/${worker.id}/logging`)
    currentLogLevel.value = response.data.level || 'INFO'
    openLogLevelDialogModal()
  } catch (error) {
    logger.error('Failed to get worker log level:', error)
    notify(`Failed to get log level for "${worker.name}"`, 'error')
    // Still open dialog with default level
    openLogLevelDialogModal()
  }
}

/**
 * Set log level for the selected worker
 */
const setLogLevel = async (level: string) => {
  if (!selectedLogLevelWorker.value || isSettingLogLevel.value) return

  try {
    isSettingLogLevel.value = true
    await axios.put(`/api/npu/workers/${selectedLogLevelWorker.value.id}/logging?level=${level}`)
    currentLogLevel.value = level
    notify(`Log level set to ${level} for "${selectedLogLevelWorker.value.name}"`, 'success')
  } catch (error) {
    logger.error('Failed to set worker log level:', error)
    const axiosError = error as { response?: { data?: { detail?: string } }; message?: string }
    const errorMessage = axiosError.response?.data?.detail || axiosError.message || 'Failed to set log level'
    notify(errorMessage, 'error')
  } finally {
    isSettingLogLevel.value = false
  }
}

/**
 * Close log level dialog
 */
const closeLogLevelDialog = () => {
  closeLogLevelDialogModal()
  selectedLogLevelWorker.value = null
  currentLogLevel.value = 'INFO'
}

const closeWorkerDialog = () => {
  closeAddWorkerDialog()
  closeEditWorkerDialog()
  editingWorker.value = null
  workerFormError.value = null
  workerForm.value = {
    name: '',
    platform: 'linux',
    ip_address: '',
    port: 8081,
    priority: 5,
    weight: 1
  }
}

// ===== STYLING HELPERS =====

const getPlatformIcon = (platform: string) => {
  const icons: Record<string, string> = {
    linux: 'fab fa-linux',
    windows: 'fab fa-windows',
    macos: 'fab fa-apple'
  }
  return icons[platform] || 'fas fa-server'
}

const getPlatformClass = (platform: string) => {
  const classes: Record<string, string> = {
    linux: 'platform-linux',
    windows: 'platform-windows',
    macos: 'platform-macos'
  }
  return classes[platform] || ''
}

const getStatusClass = (status: string) => {
  const classes: Record<string, string> = {
    online: 'status-online',
    offline: 'status-offline',
    busy: 'status-busy',
    error: 'status-error'
  }
  return classes[status] || 'status-unknown'
}

const getStatusDotClass = (status: string) => {
  const classes: Record<string, string> = {
    online: 'dot-online',
    offline: 'dot-offline',
    busy: 'dot-busy',
    error: 'dot-error'
  }
  return classes[status] || 'dot-unknown'
}

// StatusBadge variant mapping function
const getStatusVariant = (status: string): 'success' | 'danger' | 'warning' | 'secondary' => {
  const variantMap: Record<string, 'success' | 'danger' | 'warning' | 'secondary'> = {
    'online': 'success',
    'offline': 'secondary',
    'busy': 'warning',
    'error': 'danger'
  }
  return variantMap[status] || 'secondary'
}

const getLoadBarClass = (load: number) => {
  if (load < 50) return 'load-low'
  if (load < 80) return 'load-medium'
  return 'load-high'
}

const getWorkerRowClass = (worker: NPUWorker) => {
  if (!worker.enabled) return 'worker-row-disabled'
  if (worker.status === 'error') return 'worker-row-error'
  return ''
}

// ===== WEBSOCKET =====

let wsConnection: WebSocket | null = null
let reconnectTimer: number | null = null

/**
 * Setup WebSocket with proper cleanup
 * Fixes C6: WebSocket Memory Leak
 */
const setupWebSocket = () => {
  const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const wsUrl = `${wsProtocol}//${window.location.host}/ws/npu-workers`

  wsConnection = new WebSocket(wsUrl)

  wsConnection.onmessage = (event) => {
    const data = JSON.parse(event.data)

    if (data.type === 'worker_update') {
      // Update specific worker
      const index = workers.value.findIndex(w => w.id === data.worker.id)
      if (index !== -1) {
        workers.value[index] = data.worker
      }
    } else if (data.type === 'worker_added') {
      workers.value.push(data.worker)
    } else if (data.type === 'worker_removed') {
      workers.value = workers.value.filter(w => w.id !== data.worker_id)
    }
  }

  wsConnection.onerror = (error) => {
    logger.error('WebSocket error:', error)
  }

  wsConnection.onclose = () => {
    reconnectTimer = window.setTimeout(() => {
      setupWebSocket()
    }, 5000)
  }
}

// ===== LIFECYCLE =====

onMounted(() => {
  loadWorkers()
  loadLoadBalancingConfig()
  setupWebSocket()
})

onUnmounted(() => {
  // Clear reconnect timer to prevent memory leak
  if (reconnectTimer !== null) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }

  // Close WebSocket
  if (wsConnection) {
    wsConnection.close()
    wsConnection = null
  }
})
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */

.npu-workers-settings {
  padding: var(--spacing-6);
}

.settings-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: var(--spacing-8);
}

.config-section,
.workers-section {
  background: var(--bg-card);
  border-radius: var(--radius-xl);
  padding: var(--spacing-6);
  margin-bottom: var(--spacing-6);
  box-shadow: var(--shadow-sm);
}

.section-title {
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  margin-bottom: var(--spacing-5);
  display: flex;
  align-items: center;
}

.config-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: var(--spacing-6);
}

.config-item {
  display: flex;
  flex-direction: column;
}

.config-label {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  margin-bottom: var(--spacing-2);
}

.config-select,
.config-input {
  padding: var(--spacing-2-5) var(--spacing-3-5);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  background: var(--bg-input);
  color: var(--text-primary);
  transition: border-color var(--duration-200);
}

.config-select:focus,
.config-input:focus {
  outline: none;
  border-color: var(--color-primary);
}

.config-help {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  margin-top: var(--spacing-1);
}

/* Workers Table */
.workers-table-container {
  overflow-x: auto;
}

.workers-table {
  width: 100%;
  border-collapse: collapse;
}

.workers-table thead {
  background: var(--bg-secondary);
  border-bottom: 2px solid var(--border-default);
}

.workers-table th {
  padding: var(--spacing-3) var(--spacing-4);
  text-align: left;
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: var(--tracking-wide);
}

.workers-table td {
  padding: var(--spacing-4);
  border-bottom: 1px solid var(--border-light);
}

.workers-table tbody tr:hover {
  background: var(--bg-hover);
}

.worker-row-error {
  background: var(--color-error-bg) !important;
}

.worker-row-disabled {
  background: var(--bg-tertiary) !important;
  opacity: 0.65;
}

.worker-row-disabled .worker-name {
  color: var(--text-muted);
}

.worker-row-disabled .platform-badge {
  opacity: 0.7;
}

.worker-info {
  display: flex;
  flex-direction: column;
}

.worker-name {
  font-weight: var(--font-semibold);
  color: var(--text-primary);
}

.worker-id {
  font-size: 11px;
  color: var(--text-tertiary);
  font-family: var(--font-mono);
}

.platform-badge {
  display: inline-flex;
  align-items: center;
  padding: var(--spacing-1) var(--spacing-3);
  border-radius: var(--radius-full);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
}

.platform-linux {
  background: var(--color-info-bg);
  color: var(--chart-blue);
}

.platform-windows {
  background: var(--color-purple-alpha-10, rgba(147, 51, 234, 0.1));
  color: var(--color-purple);
}

.platform-macos {
  background: var(--color-success-bg);
  color: var(--color-success-dark);
}

.connection-info {
  display: flex;
  flex-direction: column;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: var(--radius-full);
  margin-right: var(--spacing-2);
}

.dot-online {
  background: var(--color-success);
}

.dot-offline {
  background: var(--color-danger);
}

.dot-busy {
  background: var(--color-warning);
}

.dot-error {
  background: var(--color-danger);
}

.load-info {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
}

.load-bar-container {
  width: 100px;
  height: 8px;
  background: var(--bg-tertiary);
  border-radius: var(--radius-default);
  overflow: hidden;
}

.load-bar {
  height: 100%;
  transition: width var(--duration-300) var(--ease-out);
}

.load-low {
  background: var(--color-success);
}

.load-medium {
  background: var(--color-warning);
}

.load-high {
  background: var(--color-danger);
}

.load-text {
  font-size: 11px;
  color: var(--text-tertiary);
}

.priority-info {
  display: flex;
  flex-direction: column;
  font-size: var(--text-sm);
  color: var(--text-primary);
}

.action-buttons {
  display: flex;
  gap: var(--spacing-2);
}

.action-btn {
  padding: var(--spacing-2) var(--spacing-3);
  border: none;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--duration-200);
  font-size: var(--text-sm);
}

.test-btn {
  background: var(--color-info-bg);
  color: var(--color-info);
}

.test-btn:hover:not(:disabled) {
  background: var(--color-info-bg-hover);
}

.metrics-btn {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.metrics-btn:hover:not(:disabled) {
  background: var(--color-success-bg-hover);
}

.edit-btn {
  background: var(--color-warning-bg);
  color: var(--color-warning-dark);
}

.edit-btn:hover:not(:disabled) {
  background: var(--color-warning-bg-hover);
}

.delete-btn {
  background: var(--color-danger-bg);
  color: var(--color-danger);
}

.delete-btn:hover:not(:disabled) {
  background: var(--color-danger-alpha-10);
}

.toggle-btn {
  font-size: 18px;
}

.toggle-enabled {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.toggle-enabled:hover:not(:disabled) {
  background: var(--color-success-bg-hover);
}

.toggle-disabled {
  background: var(--bg-tertiary);
  color: var(--text-muted);
}

.toggle-disabled:hover:not(:disabled) {
  background: var(--bg-hover);
}

.action-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* Loading State */
.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px var(--spacing-5);
}

.form-group {
  margin-bottom: var(--spacing-5);
}

.form-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: var(--spacing-4);
}

.form-label {
  display: block;
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  margin-bottom: var(--spacing-2);
}

.form-input,
.form-select {
  width: 100%;
  padding: var(--spacing-2-5) var(--spacing-3-5);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  background: var(--bg-input);
  color: var(--text-primary);
  transition: border-color var(--duration-200);
}

.form-input:focus,
.form-select:focus {
  outline: none;
  border-color: var(--color-primary);
}

.form-help {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  margin-top: var(--spacing-1);
}

/* Metrics Grid */
.metrics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: var(--spacing-4);
}

.metric-card {
  background: var(--bg-secondary);
  padding: var(--spacing-5);
  border-radius: var(--radius-lg);
  text-align: center;
}

.metric-label {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: var(--tracking-wide);
  margin-bottom: var(--spacing-2);
}

.metric-value {
  font-size: var(--text-2xl);
  font-weight: var(--font-bold);
  color: var(--text-primary);
}

/* Buttons */
.btn-primary {
  background: var(--gradient-primary);
  color: var(--text-on-primary);
  padding: var(--spacing-2-5) var(--spacing-5);
  border: none;
  border-radius: var(--radius-lg);
  font-weight: var(--font-semibold);
  cursor: pointer;
  transition: all var(--duration-200);
  display: inline-flex;
  align-items: center;
}

.btn-primary:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: var(--shadow-primary);
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-secondary {
  background: var(--color-secondary);
  color: var(--text-on-primary);
  padding: var(--spacing-2-5) var(--spacing-5);
  border: none;
  border-radius: var(--radius-lg);
  font-weight: var(--font-semibold);
  cursor: pointer;
  transition: all var(--duration-200);
  display: inline-flex;
  align-items: center;
}

.btn-secondary:hover:not(:disabled) {
  background: var(--color-secondary-hover);
}

.btn-danger {
  background: var(--color-danger);
  color: var(--text-on-error);
  padding: var(--spacing-2-5) var(--spacing-5);
  border: none;
  border-radius: var(--radius-lg);
  font-weight: var(--font-semibold);
  cursor: pointer;
  transition: all var(--duration-200);
  display: inline-flex;
  align-items: center;
}

.btn-danger:hover:not(:disabled) {
  background: var(--color-danger-hover);
}

.btn-danger:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* Log Level Dialog Styles */
.log-level-config {
  padding: var(--spacing-2) 0;
}

.current-level-badge {
  display: inline-block;
  padding: var(--spacing-1-5) var(--spacing-4);
  border-radius: var(--radius-md);
  font-weight: var(--font-semibold);
  font-size: var(--text-sm);
}

.level-debug {
  background: var(--color-warning-bg);
  color: var(--color-warning-dark);
}

.level-info {
  background: var(--color-info-bg);
  color: var(--color-info-dark);
}

.level-warning {
  background: var(--color-warning-bg);
  color: var(--color-warning-dark);
}

.level-error {
  background: var(--color-error-bg);
  color: var(--color-error-dark);
}

.level-critical {
  background: var(--color-danger-bg);
  color: var(--color-danger-dark);
}

.log-level-buttons {
  display: flex;
  gap: var(--spacing-2);
  flex-wrap: wrap;
}

.log-level-btn {
  padding: var(--spacing-2) var(--spacing-4);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  background: var(--bg-input);
  color: var(--text-primary);
  cursor: pointer;
  transition: all var(--duration-200);
  font-weight: var(--font-medium);
  font-size: var(--text-sm);
}

.log-level-btn:hover:not(:disabled) {
  border-color: var(--color-primary);
  background: var(--color-primary-bg);
}

.log-level-btn.active {
  background: var(--color-primary);
  color: var(--text-on-primary);
  border-color: var(--color-primary);
}

.log-level-btn.level-debug:hover:not(:disabled) {
  border-color: var(--color-warning);
  background: var(--color-warning-bg);
}

.log-level-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.log-btn {
  background: var(--color-purple-alpha-10, rgba(147, 51, 234, 0.1));
  color: var(--color-purple);
}

.log-btn:hover:not(:disabled) {
  color: var(--color-purple-hover);
  background: rgba(147, 51, 234, 0.15);
}
</style>
