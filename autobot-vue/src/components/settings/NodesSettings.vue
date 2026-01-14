<template>
  <div class="nodes-settings">
    <!-- Header with Add Node button -->
    <div class="nodes-header">
      <div class="header-content">
        <h4>Infrastructure Nodes</h4>
        <p class="description">Manage AutoBot distributed infrastructure nodes with oVirt-style host enrollment.</p>
      </div>
      <button class="add-node-btn" @click="showAddNodeModal = true">
        <i class="fas fa-plus"></i>
        Add Node
      </button>
    </div>

    <!-- Stats Bar -->
    <div class="stats-bar">
      <div class="stat-item">
        <span class="stat-value">{{ stats.total }}</span>
        <span class="stat-label">Total Nodes</span>
      </div>
      <div class="stat-item online">
        <span class="stat-value">{{ stats.online }}</span>
        <span class="stat-label">Online</span>
      </div>
      <div class="stat-item pending">
        <span class="stat-value">{{ stats.pending }}</span>
        <span class="stat-label">Pending</span>
      </div>
      <div class="stat-item error">
        <span class="stat-value">{{ stats.error }}</span>
        <span class="stat-label">Error</span>
      </div>
    </div>

    <!-- Loading State -->
    <div v-if="isLoading" class="loading-state">
      <i class="fas fa-spinner fa-spin"></i>
      <span>Loading nodes...</span>
    </div>

    <!-- Error State -->
    <div v-else-if="loadError" class="error-state">
      <i class="fas fa-exclamation-triangle"></i>
      <div>
        <strong>Failed to load nodes</strong>
        <p>{{ loadError }}</p>
        <button @click="fetchNodes" class="retry-btn">
          <i class="fas fa-redo"></i> Retry
        </button>
      </div>
    </div>

    <!-- Empty State -->
    <div v-else-if="nodes.length === 0" class="empty-state">
      <i class="fas fa-server"></i>
      <h5>No nodes configured</h5>
      <p>Add your first infrastructure node to get started with distributed AutoBot deployment.</p>
      <button @click="showAddNodeModal = true" class="add-first-btn">
        <i class="fas fa-plus"></i>
        Add First Node
      </button>
    </div>

    <!-- Nodes List -->
    <div v-else class="nodes-list">
      <div
        v-for="node in nodes"
        :key="node.id"
        class="node-card"
        :class="{ expanded: expandedNodeId === node.id }"
      >
        <!-- Node Header -->
        <div class="node-header" @click="toggleNodeExpand(node.id)">
          <div class="node-status">
            <span class="status-indicator" :class="node.status"></span>
          </div>
          <div class="node-info">
            <h5 class="node-name">{{ node.name }}</h5>
            <span class="node-ip">{{ node.ip_address }}</span>
            <span class="node-role">{{ getRoleLabel(node.role) }}</span>
          </div>
          <div class="node-metrics" v-if="node.status === 'online'">
            <div class="metric">
              <span class="metric-label">CPU</span>
              <span class="metric-value">{{ node.metrics?.cpu || '—' }}%</span>
            </div>
            <div class="metric">
              <span class="metric-label">RAM</span>
              <span class="metric-value">{{ node.metrics?.ram || '—' }}%</span>
            </div>
            <div class="metric">
              <span class="metric-label">Uptime</span>
              <span class="metric-value">{{ formatUptime(node.metrics?.uptime) }}</span>
            </div>
          </div>
          <div class="node-actions">
            <button
              v-if="node.status !== 'enrolling'"
              @click.stop="testNodeConnection(node)"
              class="action-btn test"
              :disabled="testingNodeId === node.id"
              title="Test Connection"
            >
              <i :class="testingNodeId === node.id ? 'fas fa-spinner fa-spin' : 'fas fa-plug'"></i>
            </button>
            <button @click.stop="toggleNodeExpand(node.id)" class="action-btn expand" title="Expand">
              <i :class="expandedNodeId === node.id ? 'fas fa-chevron-up' : 'fas fa-chevron-down'"></i>
            </button>
          </div>
        </div>

        <!-- Expanded Content -->
        <Transition name="expand">
          <div v-if="expandedNodeId === node.id" class="node-details">
            <div class="details-grid">
              <div class="detail-item">
                <span class="detail-label">SSH User</span>
                <span class="detail-value">{{ node.ssh_user }}</span>
              </div>
              <div class="detail-item">
                <span class="detail-label">SSH Port</span>
                <span class="detail-value">{{ node.ssh_port }}</span>
              </div>
              <div class="detail-item">
                <span class="detail-label">Auth Method</span>
                <span class="detail-value">{{ node.auth_method === 'pki' ? 'PKI (SSH Key)' : 'Password' }}</span>
              </div>
              <div class="detail-item">
                <span class="detail-label">Added</span>
                <span class="detail-value">{{ formatDate(node.created_at) }}</span>
              </div>
              <div class="detail-item">
                <span class="detail-label">Last Seen</span>
                <span class="detail-value">{{ formatDate(node.last_seen) || 'Never' }}</span>
              </div>
              <div class="detail-item" v-if="node.os">
                <span class="detail-label">OS</span>
                <span class="detail-value">{{ node.os }}</span>
              </div>
            </div>

            <!-- Enrollment Progress (if enrolling) -->
            <div v-if="node.status === 'enrolling'" class="enrollment-progress">
              <div class="progress-header">
                <i class="fas fa-spinner fa-spin"></i>
                <span>Enrolling node...</span>
              </div>
              <div class="progress-steps">
                <div
                  v-for="(step, index) in enrollmentSteps"
                  :key="index"
                  class="progress-step"
                  :class="getStepClass(node.enrollment_step, index)"
                >
                  <i :class="getStepIcon(node.enrollment_step, index)"></i>
                  <span>{{ step }}</span>
                </div>
              </div>
            </div>

            <!-- Node Actions -->
            <div class="detail-actions">
              <button
                v-if="node.status === 'pending'"
                @click="enrollNode(node)"
                class="btn-primary"
                :disabled="enrollingNodeId === node.id"
              >
                <i :class="enrollingNodeId === node.id ? 'fas fa-spinner fa-spin' : 'fas fa-play'"></i>
                {{ enrollingNodeId === node.id ? 'Enrolling...' : 'Start Enrollment' }}
              </button>
              <button
                v-if="node.status === 'online'"
                @click="showReassignModal(node)"
                class="btn-secondary"
              >
                <i class="fas fa-exchange-alt"></i>
                Reassign Role
              </button>
              <button
                v-if="node.status === 'error'"
                @click="showReplaceModal(node)"
                class="btn-secondary"
              >
                <i class="fas fa-sync"></i>
                Replace Host
              </button>
              <button @click="confirmRemoveNode(node)" class="btn-danger">
                <i class="fas fa-trash"></i>
                Remove
              </button>
            </div>
          </div>
        </Transition>
      </div>
    </div>

    <!-- Add Node Modal -->
    <AddNodeModal
      :visible="showAddNodeModal"
      :available-roles="availableRoles"
      @close="showAddNodeModal = false"
      @submit="handleAddNode"
    />

    <!-- Reassign Role Modal -->
    <BaseModal
      v-model="showReassignRoleModal"
      title="Reassign Node Role"
      size="small"
    >
      <div class="reassign-modal" v-if="selectedNode">
        <p>Change the role of <strong>{{ selectedNode.name }}</strong> from <strong>{{ getRoleLabel(selectedNode.role) }}</strong> to:</p>
        <select v-model="newRole" class="form-control">
          <option value="" disabled>Select new role</option>
          <option
            v-for="role in availableRoles"
            :key="role.id"
            :value="role.id"
            :disabled="role.id === selectedNode.role"
          >
            {{ role.name }} - {{ role.description }}
          </option>
        </select>
        <div class="alert alert-warning" v-if="newRole">
          <i class="fas fa-exclamation-triangle"></i>
          <span>Services will be migrated. This may cause brief downtime.</span>
        </div>
      </div>
      <template #actions>
        <button @click="showReassignRoleModal = false" class="cancel-btn">Cancel</button>
        <button
          @click="reassignRole"
          class="save-btn"
          :disabled="!newRole || isReassigning"
        >
          <i :class="isReassigning ? 'fas fa-spinner fa-spin' : 'fas fa-exchange-alt'"></i>
          {{ isReassigning ? 'Reassigning...' : 'Reassign Role' }}
        </button>
      </template>
    </BaseModal>

    <!-- Remove Confirmation Modal -->
    <BaseModal
      v-model="showRemoveModal"
      title="Remove Node"
      size="small"
    >
      <div class="remove-modal" v-if="selectedNode">
        <div class="alert alert-danger">
          <i class="fas fa-exclamation-triangle"></i>
          <div>
            <strong>Warning</strong>
            <p>You are about to remove <strong>{{ selectedNode.name }}</strong> ({{ selectedNode.ip_address }}) from the infrastructure.</p>
          </div>
        </div>
        <p>This will:</p>
        <ul>
          <li>Stop all services on this node</li>
          <li>Remove certificates and credentials</li>
          <li>Update configuration to exclude this node</li>
        </ul>
        <div class="form-group">
          <label>
            <input type="checkbox" v-model="forceRemove" />
            Force remove (skip safety checks)
          </label>
        </div>
      </div>
      <template #actions>
        <button @click="showRemoveModal = false" class="cancel-btn">Cancel</button>
        <button @click="removeNode" class="btn-danger" :disabled="isRemoving">
          <i :class="isRemoving ? 'fas fa-spinner fa-spin' : 'fas fa-trash'"></i>
          {{ isRemoving ? 'Removing...' : 'Remove Node' }}
        </button>
      </template>
    </BaseModal>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import BaseModal from '@/components/ui/BaseModal.vue'
import AddNodeModal from './AddNodeModal.vue'
import { createLogger } from '@/utils/debugUtils'
import { getBackendUrl } from '@/config/ssot-config'

const logger = createLogger('NodesSettings')

// Types
interface NodeMetrics {
  cpu: number
  ram: number
  uptime: number  // seconds
}

interface InfrastructureNode {
  id: string
  name: string
  ip_address: string
  ssh_user: string
  ssh_port: number
  auth_method: 'password' | 'pki'
  role: string
  status: 'pending' | 'enrolling' | 'online' | 'offline' | 'error'
  enrollment_step?: number
  metrics?: NodeMetrics
  os?: string
  created_at: string
  last_seen?: string
}

interface NodeRole {
  id: string
  name: string
  description: string
  services: string[]
  default_port?: number
}

// Props
interface Props {
  isSettingsLoaded?: boolean
}

defineProps<Props>()

// Emits
const emit = defineEmits<{
  'change': []
}>()

// State
const nodes = ref<InfrastructureNode[]>([])
const availableRoles = ref<NodeRole[]>([])
const isLoading = ref(true)
const loadError = ref<string | null>(null)
const expandedNodeId = ref<string | null>(null)
const testingNodeId = ref<string | null>(null)
const enrollingNodeId = ref<string | null>(null)

// Modal State
const showAddNodeModal = ref(false)
const showReassignRoleModal = ref(false)
const showRemoveModal = ref(false)
const selectedNode = ref<InfrastructureNode | null>(null)
const newRole = ref('')
const forceRemove = ref(false)
const isReassigning = ref(false)
const isRemoving = ref(false)

// Enrollment steps for progress display
const enrollmentSteps = [
  'Validating SSH connectivity',
  'Checking OS compatibility',
  'Installing dependencies',
  'Deploying PKI certificates',
  'Configuring services',
  'Registering node',
  'Starting monitoring'
]

// Computed
const stats = computed(() => ({
  total: nodes.value.length,
  online: nodes.value.filter(n => n.status === 'online').length,
  pending: nodes.value.filter(n => n.status === 'pending' || n.status === 'enrolling').length,
  error: nodes.value.filter(n => n.status === 'error' || n.status === 'offline').length,
}))

// WebSocket for real-time updates
let ws: WebSocket | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null

// Methods
async function fetchNodes() {
  isLoading.value = true
  loadError.value = null

  try {
    const backendUrl = getBackendUrl()
    const response = await fetch(`${backendUrl}/api/infrastructure/nodes`)

    if (!response.ok) {
      throw new Error(`Failed to fetch nodes: ${response.statusText}`)
    }

    const data = await response.json()
    nodes.value = data.nodes || []
  } catch (error) {
    logger.error('Failed to fetch nodes:', error)
    loadError.value = error instanceof Error ? error.message : 'Unknown error'
  } finally {
    isLoading.value = false
  }
}

async function fetchRoles() {
  try {
    const backendUrl = getBackendUrl()
    const response = await fetch(`${backendUrl}/api/infrastructure/nodes/roles`)

    if (response.ok) {
      availableRoles.value = await response.json()
    }
  } catch (error) {
    logger.error('Failed to fetch roles:', error)
    // Use default roles if API fails
    availableRoles.value = [
      { id: 'frontend', name: 'Frontend Server', description: 'Vue.js frontend (Vite)', services: ['vite-dev', 'nginx'], default_port: 5173 },
      { id: 'npu-worker', name: 'NPU Worker', description: 'Intel OpenVINO acceleration', services: ['npu-service'], default_port: 8081 },
      { id: 'redis', name: 'Redis Stack', description: 'Redis database layer', services: ['redis-stack'], default_port: 6379 },
      { id: 'ai-stack', name: 'AI Stack', description: 'LLM and AI processing', services: ['llm-server'], default_port: 8080 },
      { id: 'browser', name: 'Browser Automation', description: 'Playwright/VNC', services: ['playwright', 'vnc'], default_port: 3000 },
      { id: 'custom', name: 'Custom', description: 'Custom service configuration', services: [] },
    ]
  }
}

function toggleNodeExpand(nodeId: string) {
  expandedNodeId.value = expandedNodeId.value === nodeId ? null : nodeId
}

async function testNodeConnection(node: InfrastructureNode) {
  testingNodeId.value = node.id

  try {
    const backendUrl = getBackendUrl()
    const response = await fetch(`${backendUrl}/api/infrastructure/nodes/${node.id}/test`, {
      method: 'POST',
    })

    const result = await response.json()

    if (result.success) {
      // Update node status
      const idx = nodes.value.findIndex(n => n.id === node.id)
      if (idx !== -1) {
        nodes.value[idx].status = 'online'
        nodes.value[idx].last_seen = new Date().toISOString()
      }
      logger.info('Connection test successful for %s', node.name)
    } else {
      logger.warn('Connection test failed for %s: %s', node.name, result.error)
    }
  } catch (error) {
    logger.error('Connection test error for %s:', node.name, error)
  } finally {
    testingNodeId.value = null
  }
}

async function handleAddNode(formData: {
  hostname: string
  ip_address: string
  ssh_user: string
  ssh_port: number
  auth_method: 'password' | 'pki'
  password?: string
  ssh_key?: string
  role: string
  auto_enroll: boolean
}) {
  showAddNodeModal.value = false

  try {
    const backendUrl = getBackendUrl()
    const response = await fetch(`${backendUrl}/api/infrastructure/nodes`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: formData.hostname,
        ip_address: formData.ip_address,
        ssh_user: formData.ssh_user,
        ssh_port: formData.ssh_port,
        auth_method: formData.auth_method,
        password: formData.password,
        ssh_key: formData.ssh_key,
        role: formData.role,
        auto_enroll: formData.auto_enroll,
      }),
    })

    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || 'Failed to add node')
    }

    const newNode = await response.json()
    nodes.value.push(newNode)
    emit('change')

    // Auto-enroll if requested
    if (formData.auto_enroll) {
      enrollNode(newNode)
    }

    logger.info('Node added: %s', formData.hostname)
  } catch (error) {
    logger.error('Failed to add node:', error)
  }
}

async function enrollNode(node: InfrastructureNode) {
  enrollingNodeId.value = node.id

  // Update local status
  const idx = nodes.value.findIndex(n => n.id === node.id)
  if (idx !== -1) {
    nodes.value[idx].status = 'enrolling'
    nodes.value[idx].enrollment_step = 0
  }

  try {
    const backendUrl = getBackendUrl()
    const response = await fetch(`${backendUrl}/api/infrastructure/nodes/${node.id}/enroll`, {
      method: 'POST',
    })

    if (!response.ok) {
      throw new Error('Enrollment failed')
    }

    // Enrollment started - updates will come via WebSocket
    logger.info('Enrollment started for %s', node.name)
  } catch (error) {
    logger.error('Failed to start enrollment for %s:', node.name, error)
    if (idx !== -1) {
      nodes.value[idx].status = 'error'
    }
  } finally {
    enrollingNodeId.value = null
  }
}

function showReassignModal(node: InfrastructureNode) {
  selectedNode.value = node
  newRole.value = ''
  showReassignRoleModal.value = true
}

async function reassignRole() {
  if (!selectedNode.value || !newRole.value) return

  isReassigning.value = true

  try {
    const backendUrl = getBackendUrl()
    const response = await fetch(`${backendUrl}/api/infrastructure/nodes/${selectedNode.value.id}/role`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ role: newRole.value }),
    })

    if (!response.ok) {
      throw new Error('Failed to reassign role')
    }

    // Update local state
    const idx = nodes.value.findIndex(n => n.id === selectedNode.value?.id)
    if (idx !== -1) {
      nodes.value[idx].role = newRole.value
    }

    showReassignRoleModal.value = false
    emit('change')
    logger.info('Role reassigned for %s to %s', selectedNode.value.name, newRole.value)
  } catch (error) {
    logger.error('Failed to reassign role:', error)
  } finally {
    isReassigning.value = false
  }
}

function showReplaceModal(node: InfrastructureNode) {
  // For replace host, we show add modal with role pre-selected
  selectedNode.value = node
  showAddNodeModal.value = true
}

function confirmRemoveNode(node: InfrastructureNode) {
  selectedNode.value = node
  forceRemove.value = false
  showRemoveModal.value = true
}

async function removeNode() {
  if (!selectedNode.value) return

  isRemoving.value = true

  try {
    const backendUrl = getBackendUrl()
    const response = await fetch(
      `${backendUrl}/api/infrastructure/nodes/${selectedNode.value.id}?force=${forceRemove.value}`,
      { method: 'DELETE' }
    )

    if (!response.ok) {
      throw new Error('Failed to remove node')
    }

    // Remove from local state
    nodes.value = nodes.value.filter(n => n.id !== selectedNode.value?.id)
    showRemoveModal.value = false
    emit('change')
    logger.info('Node removed: %s', selectedNode.value.name)
  } catch (error) {
    logger.error('Failed to remove node:', error)
  } finally {
    isRemoving.value = false
  }
}

// WebSocket for real-time updates
function connectWebSocket() {
  const backendUrl = getBackendUrl()
  const wsUrl = backendUrl.replace(/^http/, 'ws') + '/ws/infrastructure/nodes'

  try {
    ws = new WebSocket(wsUrl)

    ws.onopen = () => {
      logger.info('WebSocket connected for node updates')
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        handleNodeUpdate(data)
      } catch (e) {
        logger.error('Failed to parse WebSocket message:', e)
      }
    }

    ws.onclose = () => {
      logger.info('WebSocket disconnected, reconnecting in 5s...')
      reconnectTimer = setTimeout(connectWebSocket, 5000)
    }

    ws.onerror = (error) => {
      logger.error('WebSocket error:', error)
    }
  } catch (error) {
    logger.error('Failed to connect WebSocket:', error)
    reconnectTimer = setTimeout(connectWebSocket, 5000)
  }
}

function handleNodeUpdate(data: { type: string; node_id: string; payload: any }) {
  const idx = nodes.value.findIndex(n => n.id === data.node_id)
  if (idx === -1) return

  switch (data.type) {
    case 'status_change':
      nodes.value[idx].status = data.payload.status
      break
    case 'enrollment_progress':
      nodes.value[idx].enrollment_step = data.payload.step
      if (data.payload.status) {
        nodes.value[idx].status = data.payload.status
      }
      break
    case 'metrics_update':
      nodes.value[idx].metrics = data.payload
      nodes.value[idx].last_seen = new Date().toISOString()
      break
  }
}

// Helpers
function getRoleLabel(roleId: string): string {
  const role = availableRoles.value.find(r => r.id === roleId)
  return role?.name || roleId
}

function formatUptime(seconds?: number): string {
  if (!seconds) return '—'
  const days = Math.floor(seconds / 86400)
  if (days > 0) return `${days}d`
  const hours = Math.floor(seconds / 3600)
  if (hours > 0) return `${hours}h`
  const minutes = Math.floor(seconds / 60)
  return `${minutes}m`
}

function formatDate(dateStr?: string): string {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function getStepClass(currentStep: number | undefined, stepIndex: number): string {
  if (currentStep === undefined) return ''
  if (stepIndex < currentStep) return 'completed'
  if (stepIndex === currentStep) return 'active'
  return 'pending'
}

function getStepIcon(currentStep: number | undefined, stepIndex: number): string {
  if (currentStep === undefined) return 'fas fa-circle'
  if (stepIndex < currentStep) return 'fas fa-check-circle'
  if (stepIndex === currentStep) return 'fas fa-spinner fa-spin'
  return 'fas fa-circle'
}

// Lifecycle
onMounted(async () => {
  await Promise.all([fetchNodes(), fetchRoles()])
  connectWebSocket()
})

onUnmounted(() => {
  if (ws) {
    ws.close()
  }
  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
  }
})
</script>

<style scoped>
.nodes-settings {
  padding: 0;
}

/* Header */
.nodes-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 24px;
}

.header-content h4 {
  margin: 0 0 4px 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
}

.header-content .description {
  margin: 0;
  font-size: 14px;
  color: var(--text-tertiary);
}

.add-node-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  background: var(--color-primary);
  color: white;
  border: none;
  border-radius: 6px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.2s;
}

.add-node-btn:hover {
  background: var(--color-primary-hover);
}

/* Stats Bar */
.stats-bar {
  display: flex;
  gap: 16px;
  margin-bottom: 24px;
  padding: 16px;
  background: var(--bg-secondary);
  border-radius: 8px;
}

.stat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 0 16px;
  border-right: 1px solid var(--border-light);
}

.stat-item:last-child {
  border-right: none;
}

.stat-value {
  font-size: 24px;
  font-weight: 600;
  color: var(--text-primary);
}

.stat-label {
  font-size: 12px;
  color: var(--text-tertiary);
  text-transform: uppercase;
}

.stat-item.online .stat-value {
  color: var(--color-success);
}

.stat-item.pending .stat-value {
  color: var(--color-warning);
}

.stat-item.error .stat-value {
  color: var(--color-danger);
}

/* Loading/Error/Empty States */
.loading-state,
.error-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px;
  text-align: center;
  color: var(--text-tertiary);
}

.loading-state i,
.error-state i,
.empty-state i {
  font-size: 48px;
  margin-bottom: 16px;
}

.error-state i {
  color: var(--color-danger);
}

.empty-state i {
  color: var(--text-tertiary);
}

.retry-btn,
.add-first-btn {
  margin-top: 16px;
  padding: 10px 20px;
  background: var(--color-primary);
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
}

/* Nodes List */
.nodes-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.node-card {
  background: var(--bg-secondary);
  border-radius: 8px;
  border: 1px solid var(--border-light);
  overflow: hidden;
  transition: box-shadow 0.2s;
}

.node-card:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.node-card.expanded {
  border-color: var(--color-primary);
}

/* Node Header */
.node-header {
  display: flex;
  align-items: center;
  padding: 16px;
  cursor: pointer;
  gap: 16px;
}

.node-status {
  flex-shrink: 0;
}

.status-indicator {
  display: block;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: var(--text-tertiary);
}

.status-indicator.online {
  background: var(--color-success);
  box-shadow: 0 0 8px var(--color-success);
}

.status-indicator.pending,
.status-indicator.enrolling {
  background: var(--color-warning);
  animation: pulse 2s infinite;
}

.status-indicator.offline,
.status-indicator.error {
  background: var(--color-danger);
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.node-info {
  flex: 1;
  min-width: 0;
}

.node-name {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.node-ip {
  font-size: 13px;
  color: var(--text-secondary);
  font-family: monospace;
  margin-right: 12px;
}

.node-role {
  font-size: 12px;
  padding: 2px 8px;
  background: var(--bg-tertiary);
  border-radius: 4px;
  color: var(--text-secondary);
}

/* Node Metrics */
.node-metrics {
  display: flex;
  gap: 24px;
}

.metric {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.metric-label {
  font-size: 10px;
  text-transform: uppercase;
  color: var(--text-tertiary);
}

.metric-value {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

/* Node Actions */
.node-actions {
  display: flex;
  gap: 8px;
}

.action-btn {
  padding: 8px;
  background: transparent;
  border: 1px solid var(--border-default);
  border-radius: 4px;
  cursor: pointer;
  color: var(--text-secondary);
  transition: all 0.2s;
}

.action-btn:hover:not(:disabled) {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Node Details */
.node-details {
  padding: 0 16px 16px;
  border-top: 1px solid var(--border-light);
}

.details-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 16px;
  padding: 16px 0;
}

.detail-item {
  display: flex;
  flex-direction: column;
}

.detail-label {
  font-size: 11px;
  text-transform: uppercase;
  color: var(--text-tertiary);
  margin-bottom: 4px;
}

.detail-value {
  font-size: 14px;
  color: var(--text-primary);
}

/* Enrollment Progress */
.enrollment-progress {
  padding: 16px;
  background: var(--color-info-bg);
  border-radius: 6px;
  margin: 16px 0;
}

.progress-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 500;
  margin-bottom: 12px;
}

.progress-steps {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.progress-step {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--text-tertiary);
}

.progress-step.completed {
  color: var(--color-success);
}

.progress-step.active {
  color: var(--color-info);
  font-weight: 500;
}

/* Detail Actions */
.detail-actions {
  display: flex;
  gap: 12px;
  padding-top: 16px;
  border-top: 1px solid var(--border-light);
}

.btn-primary {
  padding: 8px 16px;
  background: var(--color-primary);
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 500;
}

.btn-secondary {
  padding: 8px 16px;
  background: var(--bg-tertiary);
  color: var(--text-primary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
}

.btn-danger {
  padding: 8px 16px;
  background: var(--color-danger);
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
}

.btn-primary:disabled,
.btn-secondary:disabled,
.btn-danger:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* Transition */
.expand-enter-active,
.expand-leave-active {
  transition: all 0.3s ease;
  overflow: hidden;
}

.expand-enter-from,
.expand-leave-to {
  opacity: 0;
  max-height: 0;
}

/* Modal Styles */
.reassign-modal,
.remove-modal {
  padding: 8px 0;
}

.reassign-modal p,
.remove-modal p {
  margin: 0 0 16px 0;
}

.remove-modal ul {
  margin: 8px 0 16px 20px;
  color: var(--text-secondary);
}

.form-control {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--border-default);
  border-radius: 6px;
  font-size: 14px;
  background: var(--bg-primary);
  color: var(--text-primary);
}

.form-group {
  margin-top: 16px;
}

.form-group label {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}

.alert {
  display: flex;
  gap: 12px;
  padding: 12px 16px;
  border-radius: 6px;
  margin: 16px 0;
}

.alert-warning {
  background: var(--color-warning-bg);
  border: 1px solid var(--color-warning);
  color: var(--color-warning-text);
}

.alert-danger {
  background: var(--color-danger-bg);
  border: 1px solid var(--color-danger);
  color: var(--color-danger-text);
}

.cancel-btn {
  padding: 10px 16px;
  background: var(--text-tertiary);
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
}

.save-btn {
  padding: 10px 16px;
  background: var(--color-success);
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
}

.save-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* Responsive */
@media (max-width: 768px) {
  .nodes-header {
    flex-direction: column;
    gap: 16px;
  }

  .add-node-btn {
    width: 100%;
    justify-content: center;
  }

  .stats-bar {
    flex-wrap: wrap;
  }

  .stat-item {
    flex: 1;
    min-width: 80px;
    border-right: none;
    border-bottom: 1px solid var(--border-light);
    padding-bottom: 12px;
  }

  .node-header {
    flex-wrap: wrap;
  }

  .node-metrics {
    width: 100%;
    justify-content: space-around;
    margin-top: 12px;
    padding-top: 12px;
    border-top: 1px solid var(--border-light);
  }

  .detail-actions {
    flex-wrap: wrap;
  }

  .btn-primary,
  .btn-secondary,
  .btn-danger {
    flex: 1;
    justify-content: center;
  }
}
</style>
