<template>
  <div class="log-forwarding-settings p-6">
    <h3 class="text-2xl font-semibold text-gray-900 mb-2">Log Forwarding</h3>
    <p class="text-sm text-gray-600 mb-6">
      Forward AutoBot logs to external logging systems for centralized log aggregation and analysis.
    </p>

    <!-- Service Status -->
    <div class="service-status mb-6">
      <div class="status-header">
        <div class="status-info">
          <span class="status-dot" :class="status.running ? 'running' : 'stopped'"></span>
          <span class="status-text">{{ status.running ? 'Service Running' : 'Service Stopped' }}</span>
        </div>
        <div class="status-actions">
          <button
            @click="toggleService"
            class="service-btn"
            :class="status.running ? 'stop-btn' : 'start-btn'"
            :disabled="isToggling"
          >
            <i :class="isToggling ? 'fas fa-spinner fa-spin' : (status.running ? 'fas fa-stop' : 'fas fa-play')"></i>
            {{ status.running ? 'Stop' : 'Start' }}
          </button>
          <button @click="testAllDestinations" class="test-all-btn" :disabled="isTesting">
            <i :class="isTesting ? 'fas fa-spinner fa-spin' : 'fas fa-check-double'"></i>
            Test All
          </button>
          <button @click="fetchStatus" class="refresh-btn" :disabled="isLoading">
            <i :class="isLoading ? 'fas fa-spinner fa-spin' : 'fas fa-sync-alt'"></i>
          </button>
        </div>
      </div>
      <div class="stats-row">
        <div class="stat">
          <span class="stat-value">{{ status.total_destinations || 0 }}</span>
          <span class="stat-label">Total</span>
        </div>
        <div class="stat">
          <span class="stat-value healthy">{{ status.healthy_destinations || 0 }}</span>
          <span class="stat-label">Healthy</span>
        </div>
        <div class="stat">
          <span class="stat-value">{{ status.total_sent || 0 }}</span>
          <span class="stat-label">Sent</span>
        </div>
        <div class="stat">
          <span class="stat-value error">{{ status.total_failed || 0 }}</span>
          <span class="stat-label">Failed</span>
        </div>
      </div>
      <!-- Issue #553: Auto-start toggle -->
      <div class="auto-start-row">
        <label class="auto-start-label">
          <input
            type="checkbox"
            v-model="autoStart"
            @change="toggleAutoStart"
            :disabled="isTogglingAutoStart"
          />
          <span>Auto-start on backend startup</span>
        </label>
        <span v-if="isTogglingAutoStart" class="saving-indicator">
          <i class="fas fa-spinner fa-spin"></i> Saving...
        </span>
      </div>
    </div>

    <!-- Destinations List -->
    <div class="destinations-section">
      <div class="section-header">
        <h4>Destinations</h4>
        <button @click="showAddModal = true" class="add-btn">
          <i class="fas fa-plus"></i>
          Add Destination
        </button>
      </div>

      <div v-if="isLoading" class="loading-state">
        <i class="fas fa-spinner fa-spin"></i>
        <span>Loading destinations...</span>
      </div>

      <div v-else-if="destinations.length === 0" class="empty-state">
        <i class="fas fa-server"></i>
        <p>No log forwarding destinations configured.</p>
        <button @click="showAddModal = true" class="add-btn">
          <i class="fas fa-plus"></i>
          Add Your First Destination
        </button>
      </div>

      <div v-else class="destinations-list">
        <div
          v-for="dest in destinations"
          :key="dest.name"
          class="destination-card"
          :class="{ disabled: !dest.enabled }"
        >
          <div class="dest-header">
            <div class="dest-info">
              <span class="dest-type-badge" :class="dest.type">{{ dest.type.toUpperCase() }}</span>
              <span class="dest-name">{{ dest.name }}</span>
              <span class="health-indicator" :class="dest.healthy ? 'healthy' : 'unhealthy'">
                <i :class="dest.healthy ? 'fas fa-check-circle' : 'fas fa-exclamation-circle'"></i>
              </span>
            </div>
            <div class="dest-actions">
              <button @click="testDestination(dest.name)" class="icon-btn" title="Test Connection">
                <i class="fas fa-plug"></i>
              </button>
              <button @click="editDestination(dest)" class="icon-btn" title="Edit">
                <i class="fas fa-edit"></i>
              </button>
              <button @click="confirmDelete(dest.name)" class="icon-btn delete" title="Delete">
                <i class="fas fa-trash"></i>
              </button>
            </div>
          </div>
          <div class="dest-details">
            <div class="dest-url">
              <i class="fas fa-link"></i>
              {{ dest.url || dest.file_path || 'N/A' }}
            </div>
            <div class="dest-meta">
              <span class="scope-badge" :class="dest.scope">
                <i :class="dest.scope === 'global' ? 'fas fa-globe' : 'fas fa-server'"></i>
                {{ dest.scope }}
              </span>
              <span v-if="dest.type === 'syslog'" class="protocol-badge">
                {{ dest.syslog_protocol.toUpperCase() }}
              </span>
              <span class="level-badge">{{ dest.min_level }}</span>
            </div>
          </div>
          <div class="dest-stats">
            <span class="stat-item">
              <i class="fas fa-paper-plane"></i>
              {{ dest.sent_count }} sent
            </span>
            <span class="stat-item error" v-if="dest.failed_count > 0">
              <i class="fas fa-times-circle"></i>
              {{ dest.failed_count }} failed
            </span>
            <span class="stat-item error" v-if="dest.last_error">
              {{ dest.last_error }}
            </span>
          </div>
          <div v-if="dest.scope === 'per_host' && dest.target_hosts?.length" class="dest-hosts">
            <span class="hosts-label">Hosts:</span>
            <span v-for="host in dest.target_hosts" :key="host" class="host-tag">{{ host }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Add/Edit Modal -->
    <BaseModal
      v-model="showAddModal"
      :title="editingDestination ? 'Edit Destination' : 'Add Destination'"
      size="large"
    >
      <form @submit.prevent="saveDestination" class="destination-form">
        <!-- Basic Info -->
        <div class="form-row">
          <div class="form-group">
            <label for="dest-name">Name *</label>
            <input
              id="dest-name"
              v-model="formData.name"
              type="text"
              class="form-control"
              placeholder="e.g., production-syslog"
              :disabled="!!editingDestination"
              required
            />
          </div>
          <div class="form-group">
            <label for="dest-type">Type *</label>
            <select
              id="dest-type"
              v-model="formData.type"
              class="form-control"
              @change="onTypeChange"
              required
            >
              <option value="">Select type...</option>
              <option v-for="t in destinationTypes" :key="t.value" :value="t.value">
                {{ t.label }}
              </option>
            </select>
          </div>
        </div>

        <!-- URL/Host -->
        <div class="form-group" v-if="formData.type !== 'file'">
          <label for="dest-url">
            {{ formData.type === 'syslog' ? 'Host:Port' : 'URL' }} *
          </label>
          <input
            id="dest-url"
            v-model="formData.url"
            type="text"
            class="form-control"
            :placeholder="getUrlPlaceholder()"
            required
          />
        </div>

        <!-- File Path (for file type) -->
        <div class="form-group" v-if="formData.type === 'file'">
          <label for="dest-file">File Path *</label>
          <input
            id="dest-file"
            v-model="formData.file_path"
            type="text"
            class="form-control"
            placeholder="/var/log/autobot-forwarded.log"
            required
          />
        </div>

        <!-- Syslog-specific options -->
        <div v-if="formData.type === 'syslog'" class="syslog-options">
          <div class="form-row">
            <div class="form-group">
              <label for="syslog-protocol">Protocol</label>
              <select id="syslog-protocol" v-model="formData.syslog_protocol" class="form-control">
                <option value="udp">UDP (unreliable, fast)</option>
                <option value="tcp">TCP (reliable)</option>
                <option value="tcp_tls">TCP + TLS (encrypted)</option>
              </select>
            </div>
            <div class="form-group" v-if="formData.syslog_protocol === 'tcp_tls'">
              <label>
                <input type="checkbox" v-model="formData.ssl_verify" />
                Verify SSL Certificate
              </label>
            </div>
          </div>
          <div v-if="formData.syslog_protocol === 'tcp_tls'" class="form-row">
            <div class="form-group">
              <label for="ssl-ca-cert">CA Certificate Path</label>
              <input
                id="ssl-ca-cert"
                v-model="formData.ssl_ca_cert"
                type="text"
                class="form-control"
                placeholder="/path/to/ca.crt"
              />
            </div>
          </div>
        </div>

        <!-- Authentication -->
        <div v-if="showAuthFields" class="auth-options">
          <h5>Authentication</h5>
          <div class="form-row">
            <div class="form-group" v-if="formData.type === 'seq' || formData.type === 'webhook'">
              <label for="api-key">API Key</label>
              <input
                id="api-key"
                v-model="formData.api_key"
                type="password"
                class="form-control"
                placeholder="Optional API key"
              />
            </div>
            <div class="form-group" v-if="formData.type === 'elasticsearch' || formData.type === 'loki'">
              <label for="username">Username</label>
              <input
                id="username"
                v-model="formData.username"
                type="text"
                class="form-control"
              />
            </div>
            <div class="form-group" v-if="formData.type === 'elasticsearch' || formData.type === 'loki'">
              <label for="password">Password</label>
              <input
                id="password"
                v-model="formData.password"
                type="password"
                class="form-control"
              />
            </div>
          </div>
        </div>

        <!-- Elasticsearch index -->
        <div class="form-group" v-if="formData.type === 'elasticsearch'">
          <label for="es-index">Index Name</label>
          <input
            id="es-index"
            v-model="formData.index"
            type="text"
            class="form-control"
            placeholder="autobot-logs"
          />
        </div>

        <!-- Scope Configuration -->
        <div class="scope-config">
          <h5>Scope</h5>
          <div class="form-row">
            <div class="form-group">
              <label for="scope">Apply To</label>
              <select id="scope" v-model="formData.scope" class="form-control">
                <option value="global">Global (All Hosts)</option>
                <option value="per_host">Per Host (Specific Hosts)</option>
              </select>
            </div>
          </div>
          <div v-if="formData.scope === 'per_host'" class="form-group">
            <label>Target Hosts</label>
            <div class="hosts-selector">
              <div v-for="host in knownHosts" :key="host.hostname" class="host-checkbox">
                <label>
                  <input
                    type="checkbox"
                    :value="host.hostname"
                    v-model="formData.target_hosts"
                  />
                  {{ host.hostname }} ({{ host.ip }})
                </label>
              </div>
            </div>
            <input
              v-model="customHosts"
              type="text"
              class="form-control mt-2"
              placeholder="Additional hosts (comma-separated)"
            />
          </div>
        </div>

        <!-- Advanced Options -->
        <details class="advanced-options">
          <summary>Advanced Options</summary>
          <div class="form-row">
            <div class="form-group">
              <label for="min-level">Minimum Log Level</label>
              <select id="min-level" v-model="formData.min_level" class="form-control">
                <option value="Debug">Debug</option>
                <option value="Information">Information</option>
                <option value="Warning">Warning</option>
                <option value="Error">Error</option>
                <option value="Fatal">Fatal</option>
              </select>
            </div>
            <div class="form-group">
              <label for="batch-size">Batch Size</label>
              <input
                id="batch-size"
                v-model.number="formData.batch_size"
                type="number"
                class="form-control"
                min="1"
                max="1000"
              />
            </div>
          </div>
          <div class="form-row">
            <div class="form-group">
              <label for="batch-timeout">Batch Timeout (seconds)</label>
              <input
                id="batch-timeout"
                v-model.number="formData.batch_timeout"
                type="number"
                class="form-control"
                min="0.1"
                max="60"
                step="0.1"
              />
            </div>
            <div class="form-group">
              <label for="retry-count">Retry Count</label>
              <input
                id="retry-count"
                v-model.number="formData.retry_count"
                type="number"
                class="form-control"
                min="0"
                max="10"
              />
            </div>
          </div>
        </details>

        <div class="form-group">
          <label>
            <input type="checkbox" v-model="formData.enabled" />
            Enabled
          </label>
        </div>
      </form>

      <template #actions>
        <button @click="closeModal" class="cancel-btn">Cancel</button>
        <button @click="saveDestination" class="save-btn" :disabled="isSaving">
          <i :class="isSaving ? 'fas fa-spinner fa-spin' : 'fas fa-save'"></i>
          {{ editingDestination ? 'Update' : 'Create' }}
        </button>
      </template>
    </BaseModal>

    <!-- Delete Confirmation Modal -->
    <BaseModal
      v-model="showDeleteModal"
      title="Delete Destination"
      size="small"
    >
      <p>Are you sure you want to delete <strong>{{ deleteTargetName }}</strong>?</p>
      <p class="text-sm text-gray-500">This action cannot be undone.</p>

      <template #actions>
        <button @click="showDeleteModal = false" class="cancel-btn">Cancel</button>
        <button @click="deleteDestination" class="delete-btn" :disabled="isDeleting">
          <i :class="isDeleting ? 'fas fa-spinner fa-spin' : 'fas fa-trash'"></i>
          Delete
        </button>
      </template>
    </BaseModal>

    <!-- Test Result Toast -->
    <div v-if="testResult" class="test-toast" :class="testResult.healthy ? 'success' : 'error'">
      <i :class="testResult.healthy ? 'fas fa-check-circle' : 'fas fa-times-circle'"></i>
      <span>{{ testResult.message }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch } from 'vue'
import BaseModal from '@/components/ui/BaseModal.vue'
import { createLogger } from '@/utils/debugUtils'
import { getBackendUrl } from '@/config/ssot-config'

const logger = createLogger('LogForwardingSettings')

// State
const isLoading = ref(false)
const isSaving = ref(false)
const isDeleting = ref(false)
const isTesting = ref(false)
const isToggling = ref(false)
const isTogglingAutoStart = ref(false)  // Issue #553: Auto-start toggle state
const autoStart = ref(false)  // Issue #553: Auto-start value
const showAddModal = ref(false)
const showDeleteModal = ref(false)
const editingDestination = ref<any>(null)
const deleteTargetName = ref('')
const testResult = ref<{ healthy: boolean; message: string } | null>(null)

const destinations = ref<any[]>([])
const status = reactive({
  running: false,
  hostname: '',
  queue_size: 0,
  total_destinations: 0,
  enabled_destinations: 0,
  healthy_destinations: 0,
  total_sent: 0,
  total_failed: 0,
})

const destinationTypes = ref([
  { value: 'seq', label: 'Seq' },
  { value: 'elasticsearch', label: 'Elasticsearch' },
  { value: 'loki', label: 'Grafana Loki' },
  { value: 'syslog', label: 'Syslog' },
  { value: 'webhook', label: 'Webhook' },
  { value: 'file', label: 'File' },
])

const knownHosts = ref([
  { hostname: 'autobot-main', ip: '172.16.168.20' },
  { hostname: 'autobot-frontend', ip: '172.16.168.21' },
  { hostname: 'autobot-npu-worker', ip: '172.16.168.22' },
  { hostname: 'autobot-redis', ip: '172.16.168.23' },
  { hostname: 'autobot-ai-stack', ip: '172.16.168.24' },
  { hostname: 'autobot-browser', ip: '172.16.168.25' },
])

const customHosts = ref('')

// Form data
const defaultFormData = {
  name: '',
  type: '',
  enabled: true,
  url: '',
  api_key: '',
  username: '',
  password: '',
  index: 'autobot-logs',
  file_path: '',
  min_level: 'Information',
  batch_size: 10,
  batch_timeout: 5.0,
  retry_count: 3,
  retry_delay: 1.0,
  scope: 'global',
  target_hosts: [] as string[],
  syslog_protocol: 'udp',
  ssl_verify: true,
  ssl_ca_cert: '',
  ssl_client_cert: '',
  ssl_client_key: '',
}

const formData = reactive({ ...defaultFormData })

// Computed
const showAuthFields = computed(() => {
  return ['seq', 'elasticsearch', 'loki', 'webhook'].includes(formData.type)
})

// Methods
const fetchStatus = async () => {
  isLoading.value = true
  try {
    const response = await fetch(`${getBackendUrl()}/api/log-forwarding/status`)
    if (response.ok) {
      const data = await response.json()
      Object.assign(status, data)
    }
  } catch (error) {
    logger.error('Error fetching status:', error)
  } finally {
    isLoading.value = false
  }
}

const fetchDestinations = async () => {
  isLoading.value = true
  try {
    const response = await fetch(`${getBackendUrl()}/api/log-forwarding/destinations`)
    if (response.ok) {
      destinations.value = await response.json()
    }
  } catch (error) {
    logger.error('Error fetching destinations:', error)
  } finally {
    isLoading.value = false
  }
}

const toggleService = async () => {
  isToggling.value = true
  try {
    const endpoint = status.running ? 'stop' : 'start'
    const response = await fetch(`${getBackendUrl()}/api/log-forwarding/${endpoint}`, {
      method: 'POST',
    })
    if (response.ok) {
      await fetchStatus()
    }
  } catch (error) {
    logger.error('Error toggling service:', error)
  } finally {
    isToggling.value = false
  }
}

const testAllDestinations = async () => {
  isTesting.value = true
  try {
    const response = await fetch(`${getBackendUrl()}/api/log-forwarding/test-all`, {
      method: 'POST',
    })
    if (response.ok) {
      const data = await response.json()
      showTestResult(
        data.unhealthy === 0,
        `${data.healthy}/${data.total} destinations healthy`
      )
      await fetchDestinations()
    }
  } catch (error) {
    logger.error('Error testing destinations:', error)
    showTestResult(false, 'Failed to test destinations')
  } finally {
    isTesting.value = false
  }
}

// Issue #553: Toggle auto-start setting
const toggleAutoStart = async () => {
  isTogglingAutoStart.value = true
  try {
    const response = await fetch(`${getBackendUrl()}/api/log-forwarding/auto-start?enabled=${autoStart.value}`, {
      method: 'PUT',
    })
    if (!response.ok) {
      // Revert on failure
      autoStart.value = !autoStart.value
      logger.error('Failed to update auto-start setting')
    }
  } catch (error) {
    // Revert on error
    autoStart.value = !autoStart.value
    logger.error('Error updating auto-start:', error)
  } finally {
    isTogglingAutoStart.value = false
  }
}

// Issue #553: Fetch auto-start setting
const fetchAutoStart = async () => {
  try {
    const response = await fetch(`${getBackendUrl()}/api/log-forwarding/auto-start`)
    if (response.ok) {
      const data = await response.json()
      autoStart.value = data.auto_start || false
    }
  } catch (error) {
    logger.debug('Failed to fetch auto-start setting:', error)
  }
}

const testDestination = async (name: string) => {
  try {
    const response = await fetch(`${getBackendUrl()}/api/log-forwarding/destinations/${name}/test`, {
      method: 'POST',
    })
    if (response.ok) {
      const data = await response.json()
      showTestResult(data.healthy, data.message)
      await fetchDestinations()
    }
  } catch (error) {
    logger.error('Error testing destination:', error)
    showTestResult(false, 'Connection test failed')
  }
}

const showTestResult = (healthy: boolean, message: string) => {
  testResult.value = { healthy, message }
  setTimeout(() => {
    testResult.value = null
  }, 3000)
}

const onTypeChange = () => {
  // Reset type-specific fields when type changes
  formData.url = ''
  formData.file_path = ''
  formData.syslog_protocol = 'udp'
}

const getUrlPlaceholder = () => {
  switch (formData.type) {
    case 'seq':
      return 'http://seq-server:5341'
    case 'elasticsearch':
      return 'http://elasticsearch:9200'
    case 'loki':
      return 'http://loki:3100'
    case 'syslog':
      return '192.168.168.49:514'
    case 'webhook':
      return 'https://webhook.example.com/logs'
    default:
      return ''
  }
}

const editDestination = (dest: any) => {
  editingDestination.value = dest
  Object.assign(formData, {
    ...defaultFormData,
    ...dest,
    target_hosts: dest.target_hosts || [],
  })
  showAddModal.value = true
}

const closeModal = () => {
  showAddModal.value = false
  editingDestination.value = null
  Object.assign(formData, defaultFormData)
  customHosts.value = ''
}

const saveDestination = async () => {
  isSaving.value = true
  try {
    // Add custom hosts to target_hosts
    if (customHosts.value) {
      const additionalHosts = customHosts.value.split(',').map(h => h.trim()).filter(h => h)
      formData.target_hosts = [...new Set([...formData.target_hosts, ...additionalHosts])]
    }

    const url = editingDestination.value
      ? `${getBackendUrl()}/api/log-forwarding/destinations/${formData.name}`
      : `${getBackendUrl()}/api/log-forwarding/destinations`

    const method = editingDestination.value ? 'PUT' : 'POST'

    const response = await fetch(url, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(formData),
    })

    if (response.ok) {
      closeModal()
      await fetchDestinations()
      await fetchStatus()
    } else {
      const error = await response.json()
      showTestResult(false, error.detail || 'Failed to save destination')
    }
  } catch (error) {
    logger.error('Error saving destination:', error)
    showTestResult(false, 'Error saving destination')
  } finally {
    isSaving.value = false
  }
}

const confirmDelete = (name: string) => {
  deleteTargetName.value = name
  showDeleteModal.value = true
}

const deleteDestination = async () => {
  isDeleting.value = true
  try {
    const response = await fetch(
      `${getBackendUrl()}/api/log-forwarding/destinations/${deleteTargetName.value}`,
      { method: 'DELETE' }
    )
    if (response.ok) {
      showDeleteModal.value = false
      await fetchDestinations()
      await fetchStatus()
    }
  } catch (error) {
    logger.error('Error deleting destination:', error)
  } finally {
    isDeleting.value = false
  }
}

// Lifecycle
onMounted(async () => {
  await Promise.all([fetchStatus(), fetchDestinations(), fetchAutoStart()])
})
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.log-forwarding-settings {
  min-height: 400px;
}

/* Service Status */
.service-status {
  background: var(--bg-secondary);
  border-radius: 8px;
  padding: 16px;
}

.status-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.status-info {
  display: flex;
  align-items: center;
  gap: 8px;
}

.status-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
}

.status-dot.running {
  background: var(--color-success);
  animation: pulse 2s infinite;
}

.status-dot.stopped {
  background: var(--color-danger);
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.status-text {
  font-weight: 600;
  color: var(--text-primary);
}

.status-actions {
  display: flex;
  gap: 8px;
}

.service-btn, .test-all-btn, .refresh-btn {
  padding: 8px 16px;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 6px;
  transition: all 0.2s;
}

.start-btn {
  background: var(--color-success);
  color: var(--bg-primary);
}

.start-btn:hover:not(:disabled) {
  background: var(--color-success-hover);
}

.stop-btn {
  background: var(--color-danger);
  color: var(--bg-primary);
}

.stop-btn:hover:not(:disabled) {
  background: var(--color-danger-hover);
}

.test-all-btn {
  background: var(--color-info);
  color: var(--bg-primary);
}

.test-all-btn:hover:not(:disabled) {
  background: var(--color-info-hover);
}

.refresh-btn {
  background: var(--text-tertiary);
  color: var(--bg-primary);
  padding: 8px 12px;
}

.refresh-btn:hover:not(:disabled) {
  background: var(--text-secondary);
}

.stats-row {
  display: flex;
  gap: 24px;
}

/* Issue #553: Auto-start toggle */
.auto-start-row {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--border-light);
  display: flex;
  align-items: center;
  gap: 12px;
}

.auto-start-label {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  font-size: 14px;
  color: var(--text-primary);
}

.auto-start-label input[type="checkbox"] {
  width: 18px;
  height: 18px;
  cursor: pointer;
}

.saving-indicator {
  font-size: 12px;
  color: var(--text-tertiary);
}

.stat {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.stat-value {
  font-size: 24px;
  font-weight: 700;
  color: var(--text-primary);
}

.stat-value.healthy {
  color: var(--color-success);
}

.stat-value.error {
  color: var(--color-danger);
}

.stat-label {
  font-size: 12px;
  color: var(--text-tertiary);
  text-transform: uppercase;
}

/* Destinations Section */
.destinations-section {
  margin-top: 24px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.section-header h4 {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.add-btn {
  background: var(--color-primary);
  color: var(--bg-primary);
  border: none;
  padding: 10px 16px;
  border-radius: 6px;
  cursor: pointer;
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 8px;
}

.add-btn:hover {
  background: var(--color-primary-hover);
}

.loading-state, .empty-state {
  text-align: center;
  padding: 48px;
  color: var(--text-tertiary);
}

.empty-state i {
  font-size: 48px;
  margin-bottom: 16px;
  opacity: 0.5;
}

/* Destination Cards */
.destinations-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.destination-card {
  background: var(--bg-primary);
  border: 1px solid var(--border-light);
  border-radius: 8px;
  padding: 16px;
  transition: all 0.2s;
}

.destination-card:hover {
  border-color: var(--color-primary);
  box-shadow: var(--shadow-sm);
}

.destination-card.disabled {
  opacity: 0.6;
  background: var(--bg-secondary);
}

.dest-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.dest-info {
  display: flex;
  align-items: center;
  gap: 8px;
}

.dest-type-badge {
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
}

.dest-type-badge.seq { background: var(--color-purple, #6f42c1); color: var(--bg-primary); }
.dest-type-badge.elasticsearch { background: var(--color-warning); color: var(--text-primary); }
.dest-type-badge.loki { background: var(--color-orange, #fd7e14); color: var(--bg-primary); }
.dest-type-badge.syslog { background: var(--color-teal, #20c997); color: var(--bg-primary); }
.dest-type-badge.webhook { background: var(--color-pink, #e83e8c); color: var(--bg-primary); }
.dest-type-badge.file { background: var(--text-tertiary); color: var(--bg-primary); }

.dest-name {
  font-weight: 600;
  color: var(--text-primary);
}

.health-indicator {
  font-size: 14px;
}

.health-indicator.healthy {
  color: var(--color-success);
}

.health-indicator.unhealthy {
  color: var(--color-danger);
}

.dest-actions {
  display: flex;
  gap: 4px;
}

.icon-btn {
  background: transparent;
  border: none;
  padding: 8px;
  cursor: pointer;
  color: var(--text-tertiary);
  border-radius: 4px;
  transition: all 0.2s;
}

.icon-btn:hover {
  background: var(--border-light);
  color: var(--text-primary);
}

.icon-btn.delete:hover {
  background: var(--color-danger-bg);
  color: var(--color-danger);
}

.dest-details {
  margin-bottom: 8px;
}

.dest-url {
  font-size: 13px;
  color: var(--text-tertiary);
  margin-bottom: 8px;
}

.dest-url i {
  margin-right: 4px;
}

.dest-meta {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.scope-badge, .protocol-badge, .level-badge {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 500;
}

.scope-badge {
  background: var(--color-info-bg, #e3f2fd);
  color: var(--color-info, #1565c0);
}

.scope-badge.per_host {
  background: var(--color-warning-bg);
  color: var(--color-warning-text, #e65100);
}

.protocol-badge {
  background: var(--color-success-bg);
  color: var(--color-success-text, #2e7d32);
}

.level-badge {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
}

.dest-stats {
  display: flex;
  gap: 16px;
  font-size: 12px;
  color: var(--text-tertiary);
}

.stat-item {
  display: flex;
  align-items: center;
  gap: 4px;
}

.stat-item.error {
  color: var(--color-danger);
}

.dest-hosts {
  margin-top: 8px;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
}

.hosts-label {
  font-size: 12px;
  color: var(--text-tertiary);
}

.host-tag {
  background: var(--border-light);
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
}

/* Form Styles */
.destination-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.form-group label {
  font-weight: 500;
  color: var(--text-primary);
  font-size: 14px;
}

.form-control {
  padding: 10px 12px;
  border: 1px solid var(--border-default);
  border-radius: 6px;
  font-size: 14px;
  transition: border-color 0.2s;
  background: var(--bg-primary);
  color: var(--text-primary);
}

.form-control:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: 0 0 0 2px var(--color-primary-bg, rgba(0, 123, 255, 0.1));
}

.form-control:disabled {
  background: var(--border-light);
  color: var(--text-tertiary);
}

.syslog-options, .auth-options, .scope-config {
  background: var(--bg-secondary);
  padding: 16px;
  border-radius: 8px;
}

.syslog-options h5, .auth-options h5, .scope-config h5 {
  margin: 0 0 12px 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.hosts-selector {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
}

.host-checkbox label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  cursor: pointer;
}

.advanced-options {
  background: var(--bg-secondary);
  padding: 16px;
  border-radius: 8px;
}

.advanced-options summary {
  cursor: pointer;
  font-weight: 500;
  color: var(--text-primary);
  margin-bottom: 12px;
}

/* Modal Buttons */
.cancel-btn, .save-btn, .delete-btn {
  padding: 10px 20px;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 8px;
}

.cancel-btn {
  background: var(--text-tertiary);
  color: var(--bg-primary);
}

.save-btn {
  background: var(--color-success);
  color: var(--bg-primary);
}

.delete-btn {
  background: var(--color-danger);
  color: var(--bg-primary);
}

button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* Test Toast */
.test-toast {
  position: fixed;
  bottom: 24px;
  right: 24px;
  padding: 12px 20px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 500;
  z-index: 1000;
  animation: slideIn 0.3s ease;
}

.test-toast.success {
  background: var(--color-success-bg);
  color: var(--color-success-text, #155724);
  border: 1px solid var(--color-success-border, #c3e6cb);
}

.test-toast.error {
  background: var(--color-danger-bg);
  color: var(--color-danger-text, #721c24);
  border: 1px solid var(--color-danger-border, #f5c6cb);
}

@keyframes slideIn {
  from {
    transform: translateX(100%);
    opacity: 0;
  }
  to {
    transform: translateX(0);
    opacity: 1;
  }
}

/* Dark theme - now handled by CSS variables */
@media (prefers-color-scheme: dark) {
  /* Variables automatically switch in dark mode via design tokens */
}

/* Responsive */
@media (max-width: 768px) {
  .status-header {
    flex-direction: column;
    gap: 12px;
  }

  .form-row {
    grid-template-columns: 1fr;
  }

  .hosts-selector {
    grid-template-columns: 1fr;
  }

  .stats-row {
    flex-wrap: wrap;
    justify-content: center;
  }
}
</style>
