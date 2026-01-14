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
      <!-- Issue #695: Auto-testing indicator -->
      <div v-if="isAutoTesting" class="stat-item testing">
        <i class="fas fa-spinner fa-spin"></i>
        <span class="stat-label">Testing...</span>
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
            <!-- Issue #695: Check for updates button -->
            <button
              v-if="node.status === 'online'"
              @click.stop="checkNodeUpdates(node)"
              class="action-btn check-updates"
              :disabled="checkingUpdatesNodeId === node.id"
              :title="getUpdateTooltip(node)"
            >
              <i :class="checkingUpdatesNodeId === node.id ? 'fas fa-spinner fa-spin' : 'fas fa-search'"></i>
              <span v-if="availableUpdates[node.id]?.count" class="update-badge">
                {{ availableUpdates[node.id].count }}
              </span>
            </button>
            <!-- Issue #695: Per-node update button - opens lifecycle/update history panel -->
            <button
              v-if="node.status === 'online'"
              @click.stop="openLifecyclePanel(node)"
              class="action-btn update"
              title="View Update History"
            >
              <i class="fas fa-history"></i>
              <span v-if="availableUpdates[node.id]?.count" class="update-badge">
                {{ availableUpdates[node.id].count }}
              </span>
            </button>
            <!-- Edit node button -->
            <button
              v-if="node.status !== 'enrolling'"
              @click.stop="openEditModal(node)"
              class="action-btn edit"
              title="Edit Node"
            >
              <i class="fas fa-edit"></i>
            </button>
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
              <!-- Issue #695: Certificate status display -->
              <div class="detail-item certificate-status-item">
                <span class="detail-label">Certificate</span>
                <div class="certificate-status-row">
                  <span
                    class="cert-badge"
                    :class="getCertificateStatusClass(node)"
                  >
                    <i :class="getCertificateIcon(node)"></i>
                    {{ getCertificateLabel(node) }}
                  </span>
                  <button
                    class="cert-manage-btn"
                    @click.stop="openCertificateModal(node)"
                    title="Manage Certificate"
                  >
                    <i class="fas fa-cog"></i>
                  </button>
                </div>
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
              <!-- Issue #695: Replace Host - available for any node to swap hardware -->
              <button
                @click="showReplaceModal(node)"
                class="btn-secondary"
                title="Replace this host with a new machine (same role)"
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

    <!-- Add Node Modal (also used for Edit and Replace) -->
    <AddNodeModal
      :visible="showAddNodeModal"
      :available-roles="availableRoles"
      :edit-node="editNodeData"
      :replace-node="replaceHostNode"
      @close="closeAddNodeModal"
      @submit="handleAddNode"
      @update="handleUpdateNode"
      @replace="handleReplaceNode"
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

    <!-- Issue #695: Lifecycle Panel Modal with Update Actions -->
    <BaseModal
      v-model="showLifecyclePanel"
      :title="'Update History: ' + lifecycleNodeName"
      size="large"
    >
      <NodeLifecyclePanel
        v-if="lifecycleNodeId"
        :nodeId="lifecycleNodeId"
        :nodeName="lifecycleNodeName"
        :availableUpdates="lifecycleNodeId ? availableUpdates[lifecycleNodeId] : undefined"
        :isUpdating="updatingNodeId === lifecycleNodeId"
        :isCheckingUpdates="checkingUpdatesNodeId === lifecycleNodeId"
        @close="closeLifecyclePanel"
        @checkUpdates="handleCheckUpdatesFromPanel"
        @applyUpdates="handleApplyUpdatesFromPanel"
      />
    </BaseModal>

    <!-- Issue #695: Certificate Management Modal -->
    <BaseModal
      v-model="showCertificateModal"
      :title="'Certificate: ' + (certificateNode?.name || '')"
      size="medium"
    >
      <div class="certificate-modal" v-if="certificateNode">
        <!-- Loading State -->
        <div v-if="isCertLoading" class="cert-loading">
          <i class="fas fa-spinner fa-spin"></i>
          <span>Loading certificate information...</span>
        </div>

        <!-- Error State -->
        <div v-else-if="certActionError" class="alert alert-danger">
          <i class="fas fa-exclamation-triangle"></i>
          <span>{{ certActionError }}</span>
        </div>

        <!-- Certificate Info -->
        <div v-else-if="certificateInfo" class="cert-info">
          <div class="cert-status-header">
            <span
              class="cert-badge large"
              :class="'cert-' + certificateInfo.status"
            >
              <i :class="getCertificateIconByStatus(certificateInfo.status)"></i>
              {{ formatCertStatus(certificateInfo.status) }}
            </span>
            <span v-if="certificateInfo.days_remaining !== undefined" class="days-remaining">
              {{ certificateInfo.days_remaining }} days remaining
            </span>
          </div>

          <div class="cert-details" v-if="certificateInfo.status !== 'not_deployed'">
            <div class="cert-detail-row" v-if="certificateInfo.expires_at">
              <span class="cert-detail-label">Expires</span>
              <span class="cert-detail-value">{{ formatDate(certificateInfo.expires_at) }}</span>
            </div>
            <div class="cert-detail-row" v-if="certificateInfo.subject">
              <span class="cert-detail-label">Subject</span>
              <span class="cert-detail-value">{{ certificateInfo.subject }}</span>
            </div>
            <div class="cert-detail-row" v-if="certificateInfo.issuer">
              <span class="cert-detail-label">Issuer</span>
              <span class="cert-detail-value">{{ certificateInfo.issuer }}</span>
            </div>
            <div class="cert-detail-row" v-if="certificateInfo.fingerprint">
              <span class="cert-detail-label">Fingerprint</span>
              <span class="cert-detail-value mono">{{ certificateInfo.fingerprint }}</span>
            </div>
          </div>

          <div v-if="certificateInfo.message" class="cert-message">
            <i class="fas fa-info-circle"></i>
            {{ certificateInfo.message }}
          </div>

          <!-- Auth Method Info -->
          <div class="auth-method-section">
            <h5>Authentication Method</h5>
            <div class="auth-current">
              <i :class="certificateNode.auth_method === 'pki' ? 'fas fa-key' : 'fas fa-lock'"></i>
              <span>{{ certificateNode.auth_method === 'pki' ? 'PKI (SSH Key)' : 'Password' }}</span>
            </div>
            <p v-if="certificateNode.auth_method === 'password'" class="auth-warning">
              <i class="fas fa-exclamation-triangle"></i>
              Password authentication is less secure. Consider switching to PKI.
            </p>
          </div>
        </div>

        <!-- No Certificate Info -->
        <div v-else class="cert-not-loaded">
          <p>Click "Check Status" to load certificate information.</p>
        </div>
      </div>

      <template #actions>
        <button @click="closeCertificateModal" class="cancel-btn">Close</button>
        <button
          @click="checkCertificateStatus"
          class="btn-secondary"
          :disabled="isCertActionInProgress"
        >
          <i :class="isCertActionInProgress ? 'fas fa-spinner fa-spin' : 'fas fa-sync'"></i>
          Check Status
        </button>
        <button
          v-if="certificateInfo?.status === 'expiring_soon' || certificateInfo?.status === 'expired'"
          @click="renewCertificate"
          class="btn-primary"
          :disabled="isCertActionInProgress"
        >
          <i :class="isCertActionInProgress ? 'fas fa-spinner fa-spin' : 'fas fa-redo'"></i>
          Renew
        </button>
        <button
          v-if="certificateInfo?.status === 'not_deployed' || certificateNode?.auth_method === 'password'"
          @click="deployCertificate"
          class="btn-primary"
          :disabled="isCertActionInProgress"
        >
          <i :class="isCertActionInProgress ? 'fas fa-spinner fa-spin' : 'fas fa-upload'"></i>
          Deploy PKI
        </button>
        <button
          v-if="certificateNode?.auth_method === 'password' && certificateInfo?.status === 'valid'"
          @click="switchToPKI"
          class="save-btn"
          :disabled="isCertActionInProgress"
        >
          <i :class="isCertActionInProgress ? 'fas fa-spinner fa-spin' : 'fas fa-exchange-alt'"></i>
          Switch to PKI
        </button>
      </template>
    </BaseModal>

    <!-- Issue #695: Available Updates Modal -->
    <BaseModal
      v-model="showUpdatesModal"
      :title="`Available Updates - ${updatesModalNode?.name || 'Node'}`"
      @close="closeUpdatesModal"
    >
      <div class="updates-modal" v-if="updatesModalNode">
        <div class="updates-summary">
          <div class="summary-item">
            <span class="summary-number">{{ updatesModalPackages.length }}</span>
            <span class="summary-label">Total Updates</span>
          </div>
          <div class="summary-item security">
            <span class="summary-number">{{ updatesModalPackages.filter(p => p.is_security).length }}</span>
            <span class="summary-label">Security</span>
          </div>
        </div>

        <div class="packages-list">
          <div
            v-for="pkg in updatesModalPackages"
            :key="pkg.name"
            class="package-item"
            :class="{ security: pkg.is_security }"
          >
            <div class="package-name">
              {{ pkg.name }}
              <span v-if="pkg.is_security" class="security-badge">Security</span>
            </div>
            <div class="package-versions">
              <span class="version old">{{ pkg.current_version || 'N/A' }}</span>
              <i class="fas fa-arrow-right"></i>
              <span class="version new">{{ pkg.new_version }}</span>
            </div>
          </div>
        </div>
      </div>

      <template #footer>
        <button @click="closeUpdatesModal" class="cancel-btn">Close</button>
        <button
          @click="updateNode(updatesModalNode!); closeUpdatesModal()"
          class="primary-btn"
          :disabled="updatingNodeId === updatesModalNode?.id"
        >
          <i :class="updatingNodeId === updatesModalNode?.id ? 'fas fa-spinner fa-spin' : 'fas fa-download'"></i>
          Apply Updates
        </button>
      </template>
    </BaseModal>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import BaseModal from '@/components/ui/BaseModal.vue'
import AddNodeModal from './AddNodeModal.vue'
import NodeLifecyclePanel from './NodeLifecyclePanel.vue'
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
  certificate?: CertificateInfo
}

interface NodeRole {
  id: string
  name: string
  description: string
  services: string[]
  default_port?: number
}

// Issue #695: Certificate status types
type CertificateStatus = 'valid' | 'expiring_soon' | 'expired' | 'invalid' | 'not_deployed' | 'unknown'

interface CertificateInfo {
  status: CertificateStatus
  expires_at?: string
  days_remaining?: number
  subject?: string
  issuer?: string
  serial_number?: string
  fingerprint?: string
  message?: string
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
const isAutoTesting = ref(false)  // Issue #695: Track auto-test phase
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

// Edit node state
interface EditNodeData {
  id: string
  name: string
  ip_address: string
  ssh_user: string
  ssh_port: number
  auth_method: 'password' | 'pki'
  role: string
}
const editNodeData = ref<EditNodeData | null>(null)
const forceRemove = ref(false)

// Issue #695: Replace host state - tracks node being replaced
const replaceHostNode = ref<InfrastructureNode | null>(null)
const isReassigning = ref(false)
const isRemoving = ref(false)

// Issue #695: Lifecycle and update state
const showLifecyclePanel = ref(false)
const lifecycleNodeId = ref<string | null>(null)
const lifecycleNodeName = ref('')
const updatingNodeId = ref<string | null>(null)
const checkingUpdatesNodeId = ref<string | null>(null)
const updateType = ref<'dependencies' | 'system'>('dependencies')
// Issue #695: Available updates per node (keyed by node_id)
const availableUpdates = ref<Record<string, { count: number; security: number; lastCheck: string }>>({})
const showUpdatesModal = ref(false)
const updatesModalNode = ref<InfrastructureNode | null>(null)
const updatesModalPackages = ref<Array<{ name: string; current_version: string; new_version: string; is_security: boolean }>>([])

// Issue #695: Certificate management state
const showCertificateModal = ref(false)
const certificateNode = ref<InfrastructureNode | null>(null)
const certificateInfo = ref<CertificateInfo | null>(null)
const isCertLoading = ref(false)
const isCertActionInProgress = ref(false)
const certActionError = ref<string | null>(null)

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

// Open modal in edit mode
function openEditModal(node: InfrastructureNode) {
  editNodeData.value = {
    id: node.id,
    name: node.name,
    ip_address: node.ip_address,
    ssh_user: node.ssh_user,
    ssh_port: node.ssh_port,
    auth_method: node.auth_method,
    role: node.role,
  }
  showAddNodeModal.value = true
}

// Close add/edit modal and reset edit data
function closeAddNodeModal() {
  showAddNodeModal.value = false
  editNodeData.value = null
  replaceHostNode.value = null  // Issue #695: Also reset replace mode
}

// Handle node update from edit modal
async function handleUpdateNode(formData: {
  id: string
  hostname: string
  ip_address: string
  ssh_user: string
  ssh_port: number
  auth_method: 'password' | 'pki'
  password?: string
  ssh_key?: string
  role: string
  deploy_pki: boolean
  run_enrollment: boolean
}) {
  closeAddNodeModal()

  try {
    const backendUrl = getBackendUrl()
    const response = await fetch(`${backendUrl}/api/infrastructure/nodes/${formData.id}`, {
      method: 'PUT',
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
        deploy_pki: formData.deploy_pki,
        run_enrollment: formData.run_enrollment,
      }),
    })

    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || 'Failed to update node')
    }

    const updatedNode = await response.json()

    // Update local state
    const idx = nodes.value.findIndex(n => n.id === formData.id)
    if (idx !== -1) {
      nodes.value[idx] = {
        ...nodes.value[idx],
        name: updatedNode.name || formData.hostname,
        ip_address: updatedNode.ip_address || formData.ip_address,
        ssh_user: updatedNode.ssh_user || formData.ssh_user,
        ssh_port: updatedNode.ssh_port || formData.ssh_port,
        auth_method: updatedNode.auth_method || formData.auth_method,
        role: updatedNode.role || formData.role,
      }
    }

    emit('change')
    logger.info('Node updated: %s', formData.hostname)

    // If run_enrollment was requested, start it
    if (formData.run_enrollment) {
      const node = nodes.value.find(n => n.id === formData.id)
      if (node) {
        enrollNode(node)
      }
    }
  } catch (error) {
    logger.error('Failed to update node:', error)
  }
}

// Issue #695: Handle replace host - add new node, then remove old node on success
async function handleReplaceNode(formData: {
  oldNodeId: string
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
  closeAddNodeModal()
  logger.info('Replacing node %s with new host %s', formData.oldNodeId, formData.hostname)

  try {
    const backendUrl = getBackendUrl()

    // Step 1: Add the new node
    const addResponse = await fetch(`${backendUrl}/api/infrastructure/nodes`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: formData.hostname,
        ip_address: formData.ip_address,
        ssh_port: formData.ssh_port,
        ssh_user: formData.ssh_user,
        auth_method: formData.auth_method,
        password: formData.password,
        ssh_key: formData.ssh_key,
        role: formData.role,
        auto_enroll: formData.auto_enroll,
      }),
    })

    if (!addResponse.ok) {
      const error = await addResponse.json()
      throw new Error(error.detail || 'Failed to add replacement node')
    }

    const newNode = await addResponse.json()
    logger.info('Replacement node added: %s', newNode.name)

    // Add to local list
    nodes.value.push({
      ...newNode,
      metrics: null,
    })

    // Step 2: Remove the old node (force=true to bypass safety checks during replacement)
    const deleteResponse = await fetch(
      `${backendUrl}/api/infrastructure/nodes/${formData.oldNodeId}?force=true`,
      { method: 'DELETE' }
    )

    if (!deleteResponse.ok) {
      logger.warn('Failed to remove old node %s - new node still added', formData.oldNodeId)
    } else {
      logger.info('Old node %s removed', formData.oldNodeId)
      // Remove from local list
      const oldIdx = nodes.value.findIndex(n => n.id === formData.oldNodeId)
      if (oldIdx !== -1) {
        nodes.value.splice(oldIdx, 1)
      }
    }

    emit('change')
    logger.info('Host replacement completed: %s', formData.hostname)
  } catch (error) {
    logger.error('Failed to replace host:', error)
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
  // Issue #695: Replace Host - opens add modal with role pre-selected
  // After new host enrolls successfully, the old node will be removed
  logger.info('Replace host initiated for node: %s (role: %s)', node.name, node.role)
  replaceHostNode.value = node
  selectedNode.value = node
  // Clear edit mode - this is a new node addition with role pre-selected
  editNodeData.value = null
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

// Issue #695: Lifecycle panel functions
function openLifecyclePanel(node: InfrastructureNode) {
  lifecycleNodeId.value = node.id
  lifecycleNodeName.value = node.name
  showLifecyclePanel.value = true
}

function closeLifecyclePanel() {
  showLifecyclePanel.value = false
  lifecycleNodeId.value = null
}

// Handle check updates from lifecycle panel
function handleCheckUpdatesFromPanel() {
  if (!lifecycleNodeId.value) return
  const node = nodes.value.find(n => n.id === lifecycleNodeId.value)
  if (node) {
    checkNodeUpdates(node)
  }
}

// Handle apply updates from lifecycle panel
function handleApplyUpdatesFromPanel() {
  logger.info('handleApplyUpdatesFromPanel called, lifecycleNodeId: %s', lifecycleNodeId.value)
  if (!lifecycleNodeId.value) {
    logger.warn('No lifecycleNodeId set, cannot apply updates')
    return
  }
  const node = nodes.value.find(n => n.id === lifecycleNodeId.value)
  logger.info('Found node for update: %s', node?.name || 'NOT FOUND')
  if (node) {
    // Issue #695: Use 'system' update type for lifecycle panel since we check apt packages
    updateNode(node, 'system')
  }
}

// Issue #695: Per-node update function
async function updateNode(node: InfrastructureNode, type?: 'dependencies' | 'system') {
  const effectiveType = type || updateType.value
  logger.info('updateNode called for: %s (id: %s), type: %s', node.name, node.id, effectiveType)
  if (updatingNodeId.value === node.id) {
    logger.warn('Update already in progress for node %s, skipping', node.id)
    return
  }

  updatingNodeId.value = node.id
  logger.info('Starting update for node %s, updateType: %s', node.name, effectiveType)

  try {
    const backendUrl = getBackendUrl()
    logger.info('Calling POST %s/api/infrastructure/nodes/%s/update', backendUrl, node.id)
    const response = await fetch(`${backendUrl}/api/infrastructure/nodes/${node.id}/update`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        update_type: effectiveType,
        dry_run: false,
        force: false,
      }),
    })

    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || 'Failed to start update')
    }

    const result = await response.json()
    logger.info('Update started for %s: task %s', node.name, result.task_id)

    // The update progress will be tracked via lifecycle events
  } catch (error) {
    logger.error('Failed to update node %s:', node.name, error)
  } finally {
    // Don't clear updatingNodeId immediately - wait for lifecycle event
    setTimeout(() => {
      if (updatingNodeId.value === node.id) {
        updatingNodeId.value = null
      }
    }, 2000)
  }
}

// Issue #695: Check for available updates function
async function checkNodeUpdates(node: InfrastructureNode) {
  if (checkingUpdatesNodeId.value === node.id) return

  checkingUpdatesNodeId.value = node.id

  try {
    const backendUrl = getBackendUrl()
    const response = await fetch(`${backendUrl}/api/infrastructure/nodes/${node.id}/check-updates`)

    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || 'Failed to check for updates')
    }

    const result = await response.json()

    // Store the update count
    availableUpdates.value[node.id] = {
      count: result.update_count,
      security: result.security_count,
      lastCheck: result.last_check,
    }

    // If updates found, show the modal with package details
    if (result.update_count > 0) {
      updatesModalNode.value = node
      updatesModalPackages.value = result.packages
      showUpdatesModal.value = true
    }

    logger.info('Check updates for %s: %d packages available', node.name, result.update_count)
  } catch (error) {
    logger.error('Failed to check updates for node %s:', node.name, error)
  } finally {
    checkingUpdatesNodeId.value = null
  }
}

// Issue #695: Get tooltip text for update button
function getUpdateTooltip(node: InfrastructureNode): string {
  const updates = availableUpdates.value[node.id]
  if (!updates) return 'Check for Updates'
  if (updates.count === 0) return 'No updates available'
  return `${updates.count} updates available (${updates.security} security)`
}

// Issue #695: Auto-test all nodes on page load to update their status
async function autoTestAllNodes() {
  // Only test nodes that are in pending/unknown state or haven't been seen recently
  const nodesToTest = nodes.value.filter(n =>
    n.status === 'pending' ||
    n.status === 'offline' ||
    !n.last_seen ||
    // Also test nodes not seen in the last 5 minutes
    (n.last_seen && (Date.now() - new Date(n.last_seen).getTime()) > 5 * 60 * 1000)
  )

  if (nodesToTest.length === 0) {
    logger.info('No nodes need auto-testing')
    return
  }

  isAutoTesting.value = true
  logger.info('Auto-testing %d nodes on page load', nodesToTest.length)

  try {
    // Test all nodes in parallel (limit concurrent tests to avoid overwhelming)
    const batchSize = 5
    for (let i = 0; i < nodesToTest.length; i += batchSize) {
      const batch = nodesToTest.slice(i, i + batchSize)
      await Promise.all(batch.map(node => testNodeConnectionSilent(node)))
    }

    logger.info('Auto-test completed for all nodes')
  } finally {
    isAutoTesting.value = false
  }
}

// Issue #695: Silent version of testNodeConnection for auto-testing (no UI feedback during batch)
async function testNodeConnectionSilent(node: InfrastructureNode) {
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
        // Also update OS info if returned
        if (result.os) {
          nodes.value[idx].os = result.os
        }
        // Update metrics if returned
        if (result.metrics) {
          nodes.value[idx].metrics = result.metrics
        }
      }
      logger.debug('Auto-test: %s is online', node.name)
    } else {
      // Mark as offline if test fails
      const idx = nodes.value.findIndex(n => n.id === node.id)
      if (idx !== -1 && nodes.value[idx].status !== 'enrolling') {
        nodes.value[idx].status = 'offline'
      }
      logger.debug('Auto-test: %s is offline (%s)', node.name, result.error)
    }
  } catch (error) {
    // Mark as offline on error
    const idx = nodes.value.findIndex(n => n.id === node.id)
    if (idx !== -1 && nodes.value[idx].status !== 'enrolling') {
      nodes.value[idx].status = 'offline'
    }
    logger.debug('Auto-test: %s connection error', node.name, error)
  }
}

// Issue #695: Close updates modal
function closeUpdatesModal() {
  showUpdatesModal.value = false
  updatesModalNode.value = null
  updatesModalPackages.value = []
}

// Issue #695: Certificate management functions
function openCertificateModal(node: InfrastructureNode) {
  certificateNode.value = node
  certificateInfo.value = node.certificate || null
  certActionError.value = null
  showCertificateModal.value = true

  // Auto-check status if not already loaded
  if (!certificateInfo.value) {
    checkCertificateStatus()
  }
}

function closeCertificateModal() {
  showCertificateModal.value = false
  certificateNode.value = null
  certificateInfo.value = null
  certActionError.value = null
}

async function checkCertificateStatus() {
  if (!certificateNode.value) return

  isCertLoading.value = true
  certActionError.value = null

  try {
    const backendUrl = getBackendUrl()
    const response = await fetch(
      `${backendUrl}/api/infrastructure/nodes/${certificateNode.value.id}/certificate`
    )

    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || 'Failed to check certificate status')
    }

    const data = await response.json()
    certificateInfo.value = data

    // Update node in the list
    const idx = nodes.value.findIndex(n => n.id === certificateNode.value?.id)
    if (idx !== -1) {
      nodes.value[idx].certificate = data
    }

    logger.info('Certificate status for %s: %s', certificateNode.value.name, data.status)
  } catch (error) {
    logger.error('Failed to check certificate status:', error)
    certActionError.value = error instanceof Error ? error.message : 'Unknown error'
  } finally {
    isCertLoading.value = false
  }
}

async function renewCertificate() {
  await executeCertificateAction('renew')
}

async function deployCertificate() {
  await executeCertificateAction('deploy')
}

async function executeCertificateAction(action: 'renew' | 'deploy' | 'revoke') {
  if (!certificateNode.value) return

  isCertActionInProgress.value = true
  certActionError.value = null

  try {
    const backendUrl = getBackendUrl()
    const response = await fetch(
      `${backendUrl}/api/infrastructure/nodes/${certificateNode.value.id}/certificate`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action }),
      }
    )

    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || `Failed to ${action} certificate`)
    }

    const result = await response.json()
    logger.info('Certificate %s for %s: task %s', action, certificateNode.value.name, result.task_id)

    // Refresh status after a delay
    setTimeout(checkCertificateStatus, 2000)
  } catch (error) {
    logger.error('Certificate action %s failed:', action, error)
    certActionError.value = error instanceof Error ? error.message : 'Unknown error'
  } finally {
    isCertActionInProgress.value = false
  }
}

async function switchToPKI() {
  if (!certificateNode.value) return

  isCertActionInProgress.value = true
  certActionError.value = null

  try {
    const backendUrl = getBackendUrl()
    const response = await fetch(
      `${backendUrl}/api/infrastructure/nodes/${certificateNode.value.id}/auth`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target_method: 'pki' }),
      }
    )

    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || 'Failed to switch to PKI')
    }

    const result = await response.json()
    logger.info('Auth switch to PKI for %s: task %s', certificateNode.value.name, result.task_id)

    // Update local state
    const idx = nodes.value.findIndex(n => n.id === certificateNode.value?.id)
    if (idx !== -1) {
      nodes.value[idx].auth_method = 'pki'
    }
    if (certificateNode.value) {
      certificateNode.value.auth_method = 'pki'
    }

    emit('change')
  } catch (error) {
    logger.error('Failed to switch to PKI:', error)
    certActionError.value = error instanceof Error ? error.message : 'Unknown error'
  } finally {
    isCertActionInProgress.value = false
  }
}

// Certificate status helper functions
function getCertificateStatusClass(node: InfrastructureNode): string {
  const status = node.certificate?.status || 'unknown'
  return `cert-${status}`
}

function getCertificateIcon(node: InfrastructureNode): string {
  return getCertificateIconByStatus(node.certificate?.status || 'unknown')
}

function getCertificateIconByStatus(status: CertificateStatus): string {
  switch (status) {
    case 'valid':
      return 'fas fa-shield-check'
    case 'expiring_soon':
      return 'fas fa-exclamation-triangle'
    case 'expired':
      return 'fas fa-times-circle'
    case 'invalid':
      return 'fas fa-ban'
    case 'not_deployed':
      return 'fas fa-question-circle'
    default:
      return 'fas fa-question'
  }
}

function getCertificateLabel(node: InfrastructureNode): string {
  return formatCertStatus(node.certificate?.status || 'unknown')
}

function formatCertStatus(status: CertificateStatus): string {
  switch (status) {
    case 'valid':
      return 'Valid'
    case 'expiring_soon':
      return 'Expiring Soon'
    case 'expired':
      return 'Expired'
    case 'invalid':
      return 'Invalid'
    case 'not_deployed':
      return 'Not Deployed'
    default:
      return 'Unknown'
  }
}

// WebSocket for real-time updates
function connectWebSocket() {
  const backendUrl = getBackendUrl()
  const wsUrl = backendUrl.replace(/^http/, 'ws') + '/api/ws/infrastructure/nodes'

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
  // Issue #695: Auto-test nodes on page load so they don't show as yellow/pending
  autoTestAllNodes()
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
  /* Let parent settings-content-inner handle scrolling */
  /* Removed max-height to work with flex parent layout */
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

/* Issue #695: Auto-testing indicator */
.stat-item.testing {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--color-info);
  animation: pulse 1.5s ease-in-out infinite;
}

.stat-item.testing i {
  font-size: 18px;
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

/* Issue #695: Update history button styles */
.action-btn.update {
  position: relative;
  border-color: var(--color-info);
  color: var(--color-info);
}

.action-btn.update:hover:not(:disabled) {
  background: var(--color-info-bg);
  color: var(--color-info);
}

.action-btn.edit {
  border-color: var(--color-warning);
  color: var(--color-warning);
}

.action-btn.edit:hover {
  background: var(--color-warning-bg);
  color: var(--color-warning);
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

/* Issue #695: Certificate Status Styles */
.certificate-status-item {
  min-width: 180px;
}

.certificate-status-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.cert-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
}

.cert-badge.large {
  padding: 8px 14px;
  font-size: 14px;
}

.cert-badge i {
  font-size: 12px;
}

.cert-badge.large i {
  font-size: 14px;
}

/* Certificate status colors */
.cert-valid {
  background: var(--color-success-bg, rgba(34, 197, 94, 0.15));
  color: var(--color-success, #22c55e);
}

.cert-expiring_soon {
  background: var(--color-warning-bg, rgba(245, 158, 11, 0.15));
  color: var(--color-warning, #f59e0b);
}

.cert-expired {
  background: var(--color-danger-bg, rgba(239, 68, 68, 0.15));
  color: var(--color-danger, #ef4444);
}

.cert-invalid {
  background: var(--color-danger-bg, rgba(239, 68, 68, 0.15));
  color: var(--color-danger, #ef4444);
}

.cert-not_deployed {
  background: var(--bg-tertiary, rgba(100, 116, 139, 0.15));
  color: var(--text-secondary, #64748b);
}

.cert-unknown {
  background: var(--bg-tertiary, rgba(100, 116, 139, 0.15));
  color: var(--text-tertiary, #94a3b8);
}

.cert-manage-btn {
  padding: 4px 8px;
  background: transparent;
  border: 1px solid var(--border-default);
  border-radius: 4px;
  cursor: pointer;
  color: var(--text-secondary);
  transition: all 0.2s;
}

.cert-manage-btn:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

/* Certificate Modal Styles */
.certificate-modal {
  padding: 8px 0;
}

.cert-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 32px;
  color: var(--text-tertiary);
}

.cert-not-loaded {
  text-align: center;
  padding: 24px;
  color: var(--text-tertiary);
}

.cert-info {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.cert-status-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border-light);
}

.days-remaining {
  font-size: 14px;
  color: var(--text-secondary);
}

.cert-details {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 12px;
  background: var(--bg-secondary);
  border-radius: 6px;
}

.cert-detail-row {
  display: flex;
  justify-content: space-between;
  gap: 16px;
}

.cert-detail-label {
  font-size: 13px;
  color: var(--text-tertiary);
  flex-shrink: 0;
}

.cert-detail-value {
  font-size: 13px;
  color: var(--text-primary);
  text-align: right;
  word-break: break-all;
}

.cert-detail-value.mono {
  font-family: monospace;
  font-size: 12px;
}

.cert-message {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 12px;
  background: var(--color-info-bg, rgba(59, 130, 246, 0.1));
  border-radius: 6px;
  color: var(--color-info, #3b82f6);
  font-size: 13px;
}

.cert-message i {
  flex-shrink: 0;
  margin-top: 2px;
}

.auth-method-section {
  padding-top: 16px;
  border-top: 1px solid var(--border-light);
}

.auth-method-section h5 {
  margin: 0 0 12px 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.auth-current {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: var(--bg-secondary);
  border-radius: 6px;
  font-size: 14px;
  color: var(--text-primary);
}

.auth-current i {
  color: var(--color-primary);
}

.auth-warning {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 12px 0 0 0;
  padding: 10px 14px;
  background: var(--color-warning-bg, rgba(245, 158, 11, 0.1));
  border-radius: 6px;
  font-size: 13px;
  color: var(--color-warning, #f59e0b);
}

.auth-warning i {
  flex-shrink: 0;
}

/* Issue #695: Check Updates Button Styles */
.action-btn.check-updates {
  position: relative;
  background-color: var(--color-info-bg, rgba(59, 130, 246, 0.1));
  color: var(--color-info, #3b82f6);
}

.action-btn.check-updates:hover:not(:disabled) {
  background-color: var(--color-info, #3b82f6);
  color: white;
}

.update-badge {
  position: absolute;
  top: -6px;
  right: -6px;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  background: var(--color-danger, #ef4444);
  color: white;
  font-size: 11px;
  font-weight: 600;
  border-radius: 9px;
  display: flex;
  align-items: center;
  justify-content: center;
}

/* Issue #695: Updates Modal Styles */
.updates-modal {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.updates-summary {
  display: flex;
  gap: 16px;
  padding: 16px;
  background: var(--bg-secondary);
  border-radius: 8px;
}

.summary-item {
  flex: 1;
  text-align: center;
}

.summary-item .summary-number {
  display: block;
  font-size: 28px;
  font-weight: 700;
  color: var(--text-primary);
}

.summary-item .summary-label {
  font-size: 12px;
  color: var(--text-tertiary);
  text-transform: uppercase;
}

.summary-item.security .summary-number {
  color: var(--color-warning, #f59e0b);
}

.packages-list {
  max-height: 300px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.package-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 12px;
  background: var(--bg-secondary);
  border-radius: 6px;
  border-left: 3px solid var(--border-light);
}

.package-item.security {
  border-left-color: var(--color-warning, #f59e0b);
  background: var(--color-warning-bg, rgba(245, 158, 11, 0.05));
}

.package-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: 8px;
}

.security-badge {
  font-size: 10px;
  padding: 2px 6px;
  background: var(--color-warning, #f59e0b);
  color: white;
  border-radius: 4px;
  text-transform: uppercase;
  font-weight: 600;
}

.package-versions {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}

.package-versions .version {
  padding: 2px 6px;
  border-radius: 4px;
  font-family: monospace;
}

.package-versions .version.old {
  background: var(--bg-tertiary);
  color: var(--text-tertiary);
}

.package-versions .version.new {
  background: var(--color-success-bg, rgba(16, 185, 129, 0.1));
  color: var(--color-success, #10b981);
}

.package-versions i {
  color: var(--text-tertiary);
  font-size: 10px;
}
</style>
