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
.npu-workers-settings {
  padding: 24px;
}

.settings-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 32px;
}

.config-section, .workers-section {
  background: white;
  border-radius: 12px;
  padding: 24px;
  margin-bottom: 24px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.section-title {
  font-size: 16px;
  font-weight: 600;
  color: #2c3e50;
  margin-bottom: 20px;
  display: flex;
  align-items: center;
}

.config-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 24px;
}

.config-item {
  display: flex;
  flex-direction: column;
}

.config-label {
  font-size: 14px;
  font-weight: 600;
  color: #495057;
  margin-bottom: 8px;
}

.config-select, .config-input {
  padding: 10px 14px;
  border: 1px solid #dee2e6;
  border-radius: 6px;
  font-size: 14px;
  transition: border-color 0.2s;
}

.config-select:focus, .config-input:focus {
  outline: none;
  border-color: #667eea;
}

.config-help {
  font-size: 12px;
  color: #6c757d;
  margin-top: 4px;
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
  background: #f8f9fa;
  border-bottom: 2px solid #dee2e6;
}

.workers-table th {
  padding: 12px 16px;
  text-align: left;
  font-size: 12px;
  font-weight: 600;
  color: #495057;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.workers-table td {
  padding: 16px;
  border-bottom: 1px solid #e9ecef;
}

.workers-table tbody tr:hover {
  background: #f8f9fa;
}

.worker-row-error {
  background: #fff5f5 !important;
}

.worker-row-disabled {
  background: #f5f5f5 !important;
  opacity: 0.65;
}

.worker-row-disabled .worker-name {
  color: #999;
}

.worker-row-disabled .platform-badge {
  opacity: 0.7;
}

.worker-info {
  display: flex;
  flex-direction: column;
}

.worker-name {
  font-weight: 600;
  color: #2c3e50;
}

.worker-id {
  font-size: 11px;
  color: #6c757d;
  font-family: monospace;
}

.platform-badge {
  display: inline-flex;
  align-items: center;
  padding: 4px 12px;
  border-radius: 20px;
  font-size: 12px;
  font-weight: 600;
}

.platform-linux {
  background: #e3f2fd;
  color: #1565c0;
}

.platform-windows {
  background: #f3e5f5;
  color: #6a1b9a;
}

.platform-macos {
  background: #f1f8e9;
  color: #558b2f;
}

.connection-info {
  display: flex;
  flex-direction: column;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-right: 8px;
}

.dot-online {
  background: #28a745;
}

.dot-offline {
  background: #dc3545;
}

.dot-busy {
  background: #ffc107;
}

.dot-error {
  background: #dc3545;
}

.load-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.load-bar-container {
  width: 100px;
  height: 8px;
  background: #e9ecef;
  border-radius: 4px;
  overflow: hidden;
}

.load-bar {
  height: 100%;
  transition: width 0.3s ease;
}

.load-low {
  background: #28a745;
}

.load-medium {
  background: #ffc107;
}

.load-high {
  background: #dc3545;
}

.load-text {
  font-size: 11px;
  color: #6c757d;
}

.priority-info {
  display: flex;
  flex-direction: column;
  font-size: 13px;
  color: #495057;
}

.action-buttons {
  display: flex;
  gap: 8px;
}

.action-btn {
  padding: 8px 12px;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
  font-size: 14px;
}

.test-btn {
  background: #e7f3ff;
  color: #0066cc;
}

.test-btn:hover:not(:disabled) {
  background: #cce5ff;
}

.metrics-btn {
  background: #e8f5e9;
  color: #2e7d32;
}

.metrics-btn:hover {
  background: #c8e6c9;
}

.edit-btn {
  background: #fff3e0;
  color: #e65100;
}

.edit-btn:hover {
  background: #ffe0b2;
}

.delete-btn {
  background: #ffebee;
  color: #c62828;
}

.delete-btn:hover {
  background: #ffcdd2;
}

.toggle-btn {
  font-size: 18px;
}

.toggle-enabled {
  background: #e8f5e9;
  color: #2e7d32;
}

.toggle-enabled:hover:not(:disabled) {
  background: #c8e6c9;
}

.toggle-disabled {
  background: #f5f5f5;
  color: #9e9e9e;
}

.toggle-disabled:hover:not(:disabled) {
  background: #e0e0e0;
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
  padding: 60px 20px;
}

.form-group {
  margin-bottom: 20px;
}

.form-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 16px;
}

.form-label {
  display: block;
  font-size: 14px;
  font-weight: 600;
  color: #495057;
  margin-bottom: 8px;
}

.form-input, .form-select {
  width: 100%;
  padding: 10px 14px;
  border: 1px solid #ced4da;
  border-radius: 6px;
  font-size: 14px;
  transition: border-color 0.2s;
}

.form-input:focus, .form-select:focus {
  outline: none;
  border-color: #667eea;
}

.form-help {
  font-size: 12px;
  color: #6c757d;
  margin-top: 4px;
}


/* Metrics Grid */
.metrics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
}

.metric-card {
  background: #f8f9fa;
  padding: 20px;
  border-radius: 8px;
  text-align: center;
}

.metric-label {
  font-size: 12px;
  color: #6c757d;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 8px;
}

.metric-value {
  font-size: 24px;
  font-weight: 700;
  color: #2c3e50;
}

/* Buttons */
.btn-primary {
  background: linear-gradient(45deg, #667eea, #764ba2);
  color: white;
  padding: 10px 20px;
  border: none;
  border-radius: 8px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  display: inline-flex;
  align-items: center;
}

.btn-primary:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-secondary {
  background: #6c757d;
  color: white;
  padding: 10px 20px;
  border: none;
  border-radius: 8px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  display: inline-flex;
  align-items: center;
}

.btn-secondary:hover {
  background: #5a6268;
}

.btn-danger {
  background: #dc3545;
  color: white;
  padding: 10px 20px;
  border: none;
  border-radius: 8px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  display: inline-flex;
  align-items: center;
}

.btn-danger:hover:not(:disabled) {
  background: #c82333;
}

.btn-danger:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* Dark theme support */
@media (prefers-color-scheme: dark) {
  .config-section, .workers-section {
    background: #2d2d2d;
  }

  .section-title {
    color: #ffffff;
  }

  .workers-table thead {
    background: #383838;
  }

  .workers-table th {
    color: #ccc;
  }

  .workers-table tbody tr:hover {
    background: #383838;
  }

  .modal-dialog {
    background: #2d2d2d;
  }

  .modal-title {
    color: #ffffff;
  }

  .metric-card {
    background: #383838;
  }

  .metric-value {
    color: #ffffff;
  }
}

/* Log Level Dialog Styles */
.log-level-config {
  padding: 8px 0;
}

.current-level-badge {
  display: inline-block;
  padding: 6px 16px;
  border-radius: 6px;
  font-weight: 600;
  font-size: 14px;
}

.level-debug {
  background: #fef3c7;
  color: #92400e;
}

.level-info {
  background: #dbeafe;
  color: #1e40af;
}

.level-warning {
  background: #fed7aa;
  color: #c2410c;
}

.level-error {
  background: #fecaca;
  color: #b91c1c;
}

.level-critical {
  background: #fca5a5;
  color: #7f1d1d;
}

.log-level-buttons {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.log-level-btn {
  padding: 8px 16px;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  background: white;
  cursor: pointer;
  transition: all 0.2s;
  font-weight: 500;
  font-size: 13px;
}

.log-level-btn:hover:not(:disabled) {
  border-color: #667eea;
  background: #f5f3ff;
}

.log-level-btn.active {
  background: #667eea;
  color: white;
  border-color: #667eea;
}

.log-level-btn.level-debug:hover:not(:disabled) {
  border-color: #f59e0b;
  background: #fffbeb;
}

.log-level-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.log-btn:hover:not(:disabled) {
  color: #7c3aed;
  background: #ede9fe;
}
</style>
