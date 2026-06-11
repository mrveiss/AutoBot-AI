<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<!--
  Setup Wizard View (Issue #1294)

  Multi-step guided setup for configuring fleet nodes after fresh SLM install.
  Steps: Welcome → Add Nodes → Test Connections → Enroll → Assign Roles →
         Provision → Verify → Complete
-->
<template>
  <div class="setup-wizard">
    <!-- Header -->
    <div class="wizard-header">
      <h1>{{ $t('setupWizardView.autoBotSetupWizard') }}</h1>
      <p class="subtitle">{{ $t('setupWizardView.configureYourFleetIn') }}</p>
      <div class="header-actions">
        <button
          v-if="currentStep !== 'complete'"
          class="skip-btn"
          @click="skipWizard"
        >
          {{ $t('setupWizardView.skipSetup') }}
        </button>
        <button
          class="close-btn"
          @click="exitWizard"
          title="Exit wizard without completing"
          aria-label="Exit setup wizard"
        >
          &#10005;
        </button>
      </div>
    </div>

    <!-- Progress bar -->
    <div class="progress-bar">
      <div
        v-for="(step, i) in steps"
        :key="step.name"
        class="progress-step"
        :class="{
          completed: step.completed,
          current: step.current,
          upcoming: !step.completed && !step.current,
        }"
      >
        <div class="step-indicator">
          <span v-if="step.completed" class="check">&#10003;</span>
          <span v-else>{{ i + 1 }}</span>
        </div>
        <span class="step-label">{{ stepLabels[step.name] || step.name }}</span>
      </div>
    </div>

    <!-- Step content -->
    <div class="step-content">
      <!-- Welcome -->
      <div v-if="currentStep === 'welcome'" class="step-panel">
        <h2>{{ $t('setupWizardView.welcomeToAutoBot') }}</h2>
        <p>
          {{ $t('setupWizardView.yourSLMServiceLifecycle') }}
        </p>
        <div class="info-box">
          <h3>{{ $t('setupWizardView.whatYouLlNeed') }}</h3>
          <ul>
            <li>{{ $t('setupWizardView.iPAddressesOfYour') }}</li>
            <li>{{ $t('setupWizardView.sSHAccessCredentialsKey') }}</li>
            <li>{{ $t('setupWizardView.knowledgeOfWhichServices') }}</li>
          </ul>
        </div>
        <button class="btn-primary" @click="completeStep('welcome')">
          {{ $t('setupWizardView.getStarted') }}
        </button>
      </div>

      <!-- Add Nodes -->
      <div v-if="currentStep === 'add_nodes'" class="step-panel">
        <h2>{{ $t('setupWizardView.addFleetNodes') }}</h2>
        <p>{{ $t('setupWizardView.addTheVMsThat') }}</p>

        <div class="nodes-list" v-if="nodes.length > 0">
          <div v-for="node in nodes" :key="node.node_id" class="node-card">
            <div class="node-info">
              <strong>{{ node.hostname }}</strong>
              <span class="ip">{{ node.ip_address }}</span>
            </div>
            <span
              class="status-badge"
              :class="node.status"
            >{{ node.status }}</span>
          </div>
        </div>
        <p v-else class="empty-state">{{ $t('setupWizardView.noNodesAddedYet') }}</p>

        <div class="add-node-form">
          <h3>{{ $t('setupWizardView.addANode') }}</h3>
          <div class="form-row">
            <label class="field">
              <span class="field-label">{{ $t('setupWizardView.hostname') }}</span>
              <input
                v-model="newNode.hostname"
                placeholder="e.g. frontend-01"
                autocomplete="off"
              />
            </label>
            <label class="field">
              <span class="field-label">{{ $t('setupWizardView.iPAddress') }}</span>
              <input
                v-model="newNode.ip_address"
                placeholder="e.g. 10.0.0.21"
                autocomplete="off"
              />
            </label>
          </div>
          <div class="form-row">
            <label class="field">
              <span class="field-label">{{ $t('setupWizardView.sSHUser') }}</span>
              <input
                v-model="newNode.ssh_user"
                placeholder="default: autobot"
                autocomplete="username"
              />
            </label>
            <label class="field">
              <span class="field-label">{{ $t('setupWizardView.authMethod') }}</span>
              <select v-model="newNode.auth_method">
                <option value="key">{{ $t('setupWizardView.sSHKey') }}</option>
                <option value="password">{{ $t('setupWizardView.password') }}</option>
              </select>
            </label>
          </div>
          <label
            v-if="newNode.auth_method === 'password'"
            class="field full-width"
          >
            <span class="field-label">{{ $t('setupWizardView.sSHPassword') }}</span>
            <input
              v-model="newNode.ssh_password"
              type="password"
              placeholder="Enter SSH password"
              autocomplete="current-password"
            />
          </label>
          <button class="btn-secondary" @click="addNode" :disabled="addingNode">
            {{ addingNode ? 'Adding...' : 'Add Node' }}
          </button>
        </div>

        <button
          class="btn-primary"
          @click="completeStep('add_nodes')"
          :disabled="nodes.length === 0"
        >
          {{ $t('setupWizardView.continue') }}
        </button>
      </div>

      <!-- Test Connections -->
      <div v-if="currentStep === 'test_connections'" class="step-panel">
        <h2>{{ $t('setupWizardView.testConnections') }}</h2>
        <p>{{ $t('setupWizardView.verifySSHConnectivityTo') }}</p>

        <div class="nodes-list">
          <div v-for="node in nodes" :key="node.node_id" class="node-card">
            <div class="node-info">
              <strong>{{ node.hostname }}</strong>
              <span class="ip">{{ node.ip_address }}</span>
            </div>
            <span
              class="status-badge"
              :class="connectionResults[node.node_id] || 'pending'"
            >{{ connectionResults[node.node_id] || 'untested' }}</span>
          </div>
        </div>

        <button class="btn-secondary" @click="testAllConnections" :disabled="testingConnections">
          {{ testingConnections ? 'Testing...' : 'Test All Connections' }}
        </button>
        <button
          class="btn-primary"
          @click="completeStep('test_connections')"
          :disabled="!allConnectionsTested"
        >
          {{ $t('setupWizardView.continue') }}
        </button>
      </div>

      <!-- Enroll Agents -->
      <div v-if="currentStep === 'enroll_agents'" class="step-panel">
        <h2>{{ $t('setupWizardView.enrollSLMAgents') }}</h2>
        <p>{{ $t('setupWizardView.deployTheSLMMonitoring') }}</p>

        <div class="nodes-list">
          <div v-for="node in nodes" :key="node.node_id" class="node-card">
            <div class="node-info">
              <strong>{{ node.hostname }}</strong>
              <span class="ip">{{ node.ip_address }}</span>
            </div>
            <span
              class="status-badge"
              :class="node.status"
            >{{ node.status }}</span>
          </div>
        </div>

        <button class="btn-secondary" @click="enrollAllNodes" :disabled="enrolling">
          {{ enrolling ? 'Enrolling...' : 'Enroll All Nodes' }}
        </button>
        <button
          class="btn-primary"
          @click="completeStep('enroll_agents')"
          :disabled="!allNodesEnrolled"
        >
          {{ $t('setupWizardView.continue') }}
        </button>
      </div>

      <!-- Assign Roles -->
      <div v-if="currentStep === 'assign_roles'" class="step-panel">
        <h2>{{ $t('setupWizardView.assignRoles') }}</h2>
        <p>{{ $t('setupWizardView.chooseWhichServicesEach') }}</p>

        <div class="role-assignment" v-for="node in nodes" :key="node.node_id">
          <h3>{{ node.hostname }} ({{ node.ip_address }})</h3>

          <!-- Core Services (required) — grouped by deployment category (#1350, #3192) -->
          <div class="role-section">
            <span class="section-header">{{ $t('setupWizardView.coreServices') }}</span>
            <div
              v-for="group in groupedRolesForNode(node.node_id, requiredRoles)"
              :key="group.label"
              class="role-group"
            >
              <div class="role-group-header">
                <span class="role-group-label">{{ group.label }}</span>
                <span v-if="group.description" class="role-group-desc">{{ group.description }}</span>
              </div>
              <div class="role-chips">
                <label
                  v-for="role in group.roles"
                  :key="role.name"
                  class="role-chip"
                  :class="[
                    { selected: (nodeRoles[node.node_id] || []).includes(role.name) },
                    `state-${roleState(node, role.name)}`,
                  ]"
                  :title="roleState(node, role.name) === 'running'
                    ? role.display_name + ' (running)'
                    : role.display_name"
                >
                  <input
                    type="checkbox"
                    :value="role.name"
                    :checked="(nodeRoles[node.node_id] || []).includes(role.name)"
                    @change="toggleRole(node.node_id, role.name)"
                  />
                  <span class="state-dot"></span>
                  {{ role.display_name || role.name }}
                </label>
              </div>
            </div>
          </div>

          <!-- Optional Services — grouped by deployment category (#1350, #3192) -->
          <div class="role-section" v-if="rolesForNode(node.node_id, optionalRoles).length">
            <span class="section-header optional-header">{{ $t('setupWizardView.optionalServices') }}</span>
            <div
              v-for="group in groupedRolesForNode(node.node_id, optionalRoles)"
              :key="group.label"
              class="role-group"
            >
              <div class="role-group-header">
                <span class="role-group-label">{{ group.label }}</span>
                <span v-if="group.description" class="role-group-desc">{{ group.description }}</span>
              </div>
              <div class="role-chips">
                <label
                  v-for="role in group.roles"
                  :key="role.name"
                  class="role-chip optional-chip"
                  :class="[
                    { selected: (nodeRoles[node.node_id] || []).includes(role.name) },
                    `state-${roleState(node, role.name)}`,
                  ]"
                  :title="roleState(node, role.name) === 'running'
                    ? role.display_name + ' (running)'
                    : role.degraded_without.length
                      ? 'Without: ' + role.degraded_without.join('; ')
                      : role.display_name"
                >
                  <input
                    type="checkbox"
                    :value="role.name"
                    :checked="(nodeRoles[node.node_id] || []).includes(role.name)"
                    @change="toggleRole(node.node_id, role.name)"
                  />
                  <span class="state-dot"></span>
                  {{ role.display_name || role.name }}
                </label>
              </div>
            </div>
          </div>

          <!-- SLM services: shown as locked on manager node only (#1455, #2900) -->
          <div
            v-if="node.node_id === '00-SLM-Manager' && node.detected_roles.some(r => SLM_ROLES.includes(r))"
            class="infra-roles-row"
          >
            <span class="infra-label">{{ $t('setupWizardView.sLMServices') }}</span>
            <span
              v-for="slm in SLM_ROLES.filter(r => node.detected_roles.includes(r))"
              :key="slm"
              class="role-chip infra-chip state-running"
            >
              <span class="state-dot"></span>
              {{ slm }}
            </span>
          </div>

          <!-- Infra roles: auto-deployed, shown as locked (#1344) -->
          <div
            v-if="(nodeRoles[node.node_id] || []).some(r => !INFRA_ROLES.includes(r) && !SLM_ROLES.includes(r))"
            class="infra-roles-row"
          >
            <span class="infra-label">{{ $t('setupWizardView.autoDeployed') }}</span>
            <span
              v-for="infra in INFRA_ROLES"
              :key="infra"
              class="role-chip infra-chip"
            >
              {{ infra === 'autobot_shared' ? 'Shared Library' : 'SLM Agent' }}
            </span>
          </div>
        </div>

        <button class="btn-primary" @click="saveAndContinueRoles" :disabled="savingRoles">
          {{ savingRoles ? 'Saving...' : 'Save & Continue' }}
        </button>
      </div>

      <!-- Configure Secrets / API Keys (#3079) -->
      <div v-if="currentStep === 'configure_secrets'" class="step-panel">
        <h2>{{ $t('setupWizardView.aPIKeysAmpTokens') }}</h2>
        <p>
          {{ $t('setupWizardView.someServicesRequireAPI') }}
        </p>

        <div class="secrets-form">
          <div class="secret-entry">
            <h3>{{ $t('setupWizardView.huggingFaceToken') }}</h3>
            <p class="secret-desc">
              {{ $t('setupWizardView.requiredForTTSVoice') }}
              <a href="https://huggingface.co/SWivid/F5-TTS" target="_blank" rel="noopener">{{ $t('setupWizardView.acceptLicense') }}</a>
              then
              <a href="https://huggingface.co/settings/tokens" target="_blank" rel="noopener">{{ $t('setupWizardView.createAToken') }}</a>.
            </p>
            <input
              v-model="secretValues.hf_token"
              type="password"
              placeholder="hf_..."
              class="full-width"
            />
          </div>
        </div>

        <div v-if="secretsSaved" class="info-box success-box">
          {{ $t('setupWizardView.secretsSavedTheyWill') }}
        </div>

        <button class="btn-secondary" @click="saveSecrets" :disabled="savingSecrets">
          {{ savingSecrets ? 'Saving...' : 'Save API Keys' }}
        </button>
        <button class="btn-primary" @click="completeStep('configure_secrets')">
          {{ Object.values(secretValues).some(v => v) ? 'Continue' : 'Skip' }}
        </button>
      </div>

      <!-- Provision Fleet -->
      <div v-if="currentStep === 'provision_fleet'" class="step-panel">
        <h2>{{ $t('setupWizardView.provisionFleet') }}</h2>
        <p>
          {{ $t('setupWizardView.deployAllAssignedServices') }}
        </p>

        <!-- Phase & status bar -->
        <div v-if="provisioning || provisionComplete" class="provision-status-bar">
          <span class="provision-stage">{{ provisionStage }}</span>
          <span class="provision-elapsed">{{ formatElapsed(provisionElapsed) }}</span>
        </div>

        <!-- Phase progress chips -->
        <div v-if="provisioning || provisionComplete" class="provision-phases">
          <span
            v-for="phase in knownPhases"
            :key="phase.id"
            class="provision-phase"
            :class="{
              'phase-done': completedPhases.has(phase.id),
              'phase-active': currentPhase === phase.id
            }"
          >
            {{ completedPhases.has(phase.id) ? '✓' : currentPhase === phase.id ? '→' : '·' }}
            {{ phase.label }}
          </span>
        </div>

        <!-- Current task (heartbeat in-place — does not flood the log) -->
        <div v-if="currentTask" class="provision-current-task">
          <span class="task-spinner">⟳</span>{{ currentTask }}
        </div>

        <!-- Streaming log panel -->
        <div
          v-if="provisionLogs.length > 0"
          ref="logContainerRef"
          class="provision-log"
        >
          <div
            v-for="(entry, idx) in provisionLogs"
            :key="idx"
            class="log-entry"
            :class="`log-${entry.type}`"
          >
            {{ entry.message }}
          </div>
        </div>

        <button
          class="btn-primary"
          @click="provisionFleet"
          :disabled="provisioning"
        >
          {{ provisioning ? 'Provisioning...' : 'Start Provisioning' }}
        </button>
        <button
          v-if="provisionComplete"
          class="btn-primary"
          @click="completeStep('provision_fleet')"
        >
          {{ $t('setupWizardView.continue') }}
        </button>
      </div>

      <!-- Verify Health -->
      <div v-if="currentStep === 'verify_health'" class="step-panel">
        <h2>{{ $t('setupWizardView.verifyFleetHealth') }}</h2>
        <p>{{ $t('setupWizardView.checkingThatAllServices') }}</p>

        <div v-if="fleetHealth" class="health-summary">
          <div
            class="health-badge"
            :class="fleetHealth.health"
          >
            {{ fleetHealth.health }}
          </div>
          <ul>
            <li>Total nodes: {{ fleetHealth.total_nodes }}</li>
            <li>Online nodes: {{ fleetHealth.online_nodes }}</li>
            <li v-if="fleetHealth.missing_required_roles.length > 0">
              Missing roles: {{ fleetHealth.missing_required_roles.join(', ') }}
            </li>
          </ul>
        </div>

        <button class="btn-secondary" @click="checkFleetHealth" :disabled="checkingHealth">
          {{ checkingHealth ? 'Checking...' : 'Check Fleet Health' }}
        </button>
        <button
          class="btn-primary"
          @click="completeStep('verify_health')"
          :disabled="!fleetHealth || !fleetHealth.ready"
        >
          {{ $t('setupWizardView.continue') }}
        </button>
      </div>

      <!-- Complete -->
      <div v-if="currentStep === 'complete'" class="step-panel complete-panel">
        <div class="success-icon">&#10003;</div>
        <h2>{{ $t('setupWizardView.setupComplete') }}</h2>
        <p>{{ $t('setupWizardView.yourAutoBotFleetIs') }}</p>
        <button class="btn-primary" @click="goToDashboard">
          {{ $t('setupWizardView.goToDashboard') }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { ref, computed, nextTick, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useSlmApi } from '@/composables/useSlmApi'
import { useProvisionStore } from '@/stores/provision'
import type { NodeRole } from '@/types/slm'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('SetupWizard')

const router = useRouter()
const {
  getNodes: fetchNodes,
  getRoles: fetchRoles,
  registerNode,
  testConnection,
  enrollNode,
  updateNodeRoles,
  upsertSecret,
  getSecretValue,
  getWizardStatus,
  completeWizardStep,
  skipWizardSetup,
  provisionWizardFleet,
  validateWizardFleet,
} = useSlmApi()

// #7096: provision state lives in a Pinia store so it survives component
// unmount (user navigates to another page during provisioning), browser
// refresh (state recovers via getProvisionStatus), and WS disconnect.
const provisionStore = useProvisionStore()

// ── Wizard state ──────────────────────────────────────────────────────────

interface WizardStep {
  name: string
  index: number
  completed: boolean
  current: boolean
}

const steps = ref<WizardStep[]>([])
const currentStep = ref('welcome')
const currentStepIndex = ref(0)
const loading = ref(true)

const stepLabels: Record<string, string> = {
  welcome: 'Welcome',
  add_nodes: 'Add Nodes',
  test_connections: 'Test',
  enroll_agents: 'Enroll',
  assign_roles: 'Roles',
  configure_secrets: 'API Keys',
  provision_fleet: 'Provision',
  verify_health: 'Verify',
  complete: 'Done',
}

// ── Node management ───────────────────────────────────────────────────────

interface Node {
  node_id: string
  hostname: string
  ip_address: string
  status: string
  roles: string[]
  detected_roles: string[]
  ssh_user?: string
  ssh_port?: number
  auth_method?: string
}

type RoleState = 'running' | 'assigned' | 'available'

const nodes = ref<Node[]>([])
const newNode = ref({
  hostname: '',
  ip_address: '',
  ssh_user: 'autobot',
  auth_method: 'key',
  ssh_password: '',
})
const addingNode = ref(false)

// ── Connection testing ────────────────────────────────────────────────────

const connectionResults = ref<Record<string, string>>({})
const testingConnections = ref(false)
const allConnectionsTested = computed(() =>
  nodes.value.length > 0 &&
  nodes.value.every(n => connectionResults.value[n.node_id] === 'success')
)

// ── Enrollment ────────────────────────────────────────────────────────────

const enrolling = ref(false)
const allNodesEnrolled = computed(() =>
  nodes.value.length > 0 &&
  nodes.value.every(n => n.status === 'online')
)

// ── Role assignment ───────────────────────────────────────────────────────

interface RoleInfo {
  name: string
  display_name: string
  required: boolean
  degraded_without: string[]
}

const INFRA_ROLES = ['autobot_shared', 'slm-agent']
const SLM_ROLES = ['slm-backend', 'slm-frontend', 'slm-database', 'slm-monitoring']

const availableRoles = ref<RoleInfo[]>([])
const nodeRoles = ref<Record<string, string[]>>({})
const savingRoles = ref(false)

const requiredRoles = computed(() => availableRoles.value.filter(r => r.required))
const optionalRoles = computed(() => availableRoles.value.filter(r => !r.required))

/** Roles visible for a given node: unassigned or assigned to this node (#1455). */
function rolesForNode(nodeId: string, roles: RoleInfo[]): RoleInfo[] {
  return roles.filter(r => {
    const assignedTo = nodes.value.find(
      n => n.node_id !== nodeId && (nodeRoles.value[n.node_id] || []).includes(r.name)
    )
    return !assignedTo
  })
}

/** Deployment group definitions for wizard role assignment UI (#3192). */
interface DeploymentGroup {
  label: string
  description: string
  roles: string[]
}

const DEPLOYMENT_GROUPS: DeploymentGroup[] = [
  {
    label: 'Backend Stack',
    description: 'API server, task queue, and beat scheduler',
    roles: ['backend', 'celery', 'scheduler'],
  },
  {
    label: 'Frontend',
    description: 'Vue frontend and nginx reverse proxy',
    roles: ['frontend'],
  },
  {
    label: 'Database',
    description: 'Redis Stack and PostgreSQL persistence layers',
    roles: ['redis', 'postgres'],
  },
  {
    label: 'AI Stack',
    description: 'AI processing service and ChromaDB vector store',
    roles: ['ai-stack', 'chromadb'],
  },
  {
    label: 'NPU Worker',
    description: 'OpenVINO NPU inference worker',
    roles: ['npu-worker'],
  },
  {
    label: 'TTS Worker',
    description: 'Text-to-speech synthesis service',
    roles: ['tts-worker'],
  },
  {
    label: 'Browser Worker',
    description: 'Playwright browser automation service',
    roles: ['browser-service'],
  },
  {
    label: 'LLM Nodes',
    description: 'Local LLM inference via Ollama',
    roles: ['autobot-llm-cpu', 'autobot-llm-gpu'],
  },
  {
    label: 'VNC / Desktop',
    description: 'VNC remote desktop server',
    roles: ['vnc'],
  },
]

/**
 * Group a filtered role list by deployment category (#3192).
 * Roles not matched by any group appear under "Other".
 */
function groupedRolesForNode(
  nodeId: string,
  roles: RoleInfo[],
): Array<{ label: string; description: string; roles: RoleInfo[] }> {
  const visible = rolesForNode(nodeId, roles)
  const placed = new Set<string>()
  const result: Array<{ label: string; description: string; roles: RoleInfo[] }> = []

  for (const group of DEPLOYMENT_GROUPS) {
    const matched = visible.filter(r => group.roles.includes(r.name))
    if (matched.length > 0) {
      result.push({ label: group.label, description: group.description, roles: matched })
      for (const r of matched) placed.add(r.name)
    }
  }

  const ungrouped = visible.filter(r => !placed.has(r.name))
  if (ungrouped.length > 0) {
    result.push({ label: 'Other', description: '', roles: ungrouped })
  }

  return result
}

/** Determine per-chip state for a role on a given node (#1353). */
function roleState(node: Node, roleName: string): RoleState {
  if (node.detected_roles.includes(roleName)) return 'running'
  if ((nodeRoles.value[node.node_id] || []).includes(roleName)) return 'assigned'
  return 'available'
}

// ── Secrets / API keys (#3079) ────────────────────────────────────────────

const secretValues = ref<Record<string, string>>({ hf_token: '' })
const savingSecrets = ref(false)
const secretsSaved = ref(false)

async function loadExistingSecrets() {
  for (const key of Object.keys(secretValues.value)) {
    const val = await getSecretValue(key)
    if (val) secretValues.value[key] = val
  }
}

async function saveSecrets() {
  savingSecrets.value = true
  secretsSaved.value = false
  try {
    for (const [key, value] of Object.entries(secretValues.value)) {
      if (value.trim()) {
        await upsertSecret(key, value.trim(), 'api_key', 'Set via setup wizard')
      }
    }
    secretsSaved.value = true
  } catch (err) {
    logger.error('Failed to save secrets:', err)
    alert('Failed to save API keys. Check the console for details.')
  } finally {
    savingSecrets.value = false
  }
}

// ── Provisioning ──────────────────────────────────────────────────────────

// #7096: provision state proxied from store (survives component unmount).
// Names preserved to minimize template churn; the underlying refs live in
// useProvisionStore() and persist across navigation.
const provisioning = computed(() => provisionStore.isRunning)
const provisionComplete = computed(() => provisionStore.isComplete)
const provisionLogs = computed(() => provisionStore.logs)
const provisionStage = computed(() => formatStage(provisionStore.stage))
const provisionElapsed = computed(() => provisionStore.elapsedSeconds)
const currentTask = computed(() => provisionStore.currentTask)
const currentPhase = computed(() => provisionStore.currentPhase)
const completedPhases = computed(() => provisionStore.completedPhases)
const logContainerRef = ref<HTMLElement | null>(null)

const knownPhases = [
  { id: '0', label: 'Shared Deps' },
  { id: '1', label: 'Common' },
  { id: '2', label: 'SLM Agent' },
  { id: '3', label: 'Data Layer' },
  { id: '4a', label: 'Backend' },
  { id: '4b', label: 'Frontend' },
  { id: '5', label: 'Verify' },
  { id: '6', label: 'AI Stack' },
]

// ── Health check ──────────────────────────────────────────────────────────

const checkingHealth = ref(false)
const fleetHealth = ref<{
  health: string
  total_nodes: number
  online_nodes: number
  missing_required_roles: string[]
  ready: boolean
} | null>(null)

// ── API calls ─────────────────────────────────────────────────────────────

async function loadWizardStatus() {
  try {
    const data = await getWizardStatus()
    steps.value = data.steps
    currentStep.value = data.current_step
    currentStepIndex.value = data.current_step_index
  } catch {
    // Default to welcome on error
    currentStep.value = 'welcome'
  } finally {
    loading.value = false
  }
}

async function loadNodes() {
  try {
    const result = await fetchNodes()
    nodes.value = result.map(n => ({
      node_id: n.node_id,
      hostname: n.hostname,
      ip_address: n.ip_address,
      status: n.status,
      roles: n.roles as string[],
      detected_roles: n.detected_roles ?? [],
      ssh_user: n.ssh_user,
      ssh_port: n.ssh_port,
      auth_method: n.auth_method,
    }))
    // Initialize role map from current node roles
    for (const node of nodes.value) {
      nodeRoles.value[node.node_id] = node.roles || []
    }
  } catch {
    nodes.value = []
  }
}

async function loadRoles() {
  try {
    const result = await fetchRoles()
    // Filter out infra + SLM roles (SLM already on manager) (#1349, #1344, #1455)
    availableRoles.value = result
      .filter(r => !INFRA_ROLES.includes(r.name) && !SLM_ROLES.includes(r.name))
      .map(r => ({
        name: r.name,
        display_name: r.description || r.name,
        required: r.required ?? false,
        degraded_without: r.degraded_without ?? [],
      }))
  } catch {
    availableRoles.value = []
  }
}

async function completeStep(step: string) {
  try {
    await completeWizardStep(step)
    await loadWizardStatus()
    // Load data needed for the next step
    if (currentStep.value === 'add_nodes' || currentStep.value === 'test_connections') {
      await loadNodes()
    }
    if (currentStep.value === 'assign_roles') {
      await loadNodes()
      await loadRoles()
    }
  } catch (err) {
    logger.error('Failed to complete step:', err)
  }
}

async function skipWizard() {
  if (confirm('Skip the setup wizard? You can configure nodes later from the Fleet page.')) {
    try {
      await skipWizardSetup()
      router.push({ name: 'fleet' })
    } catch (err) {
      logger.error('Failed to skip wizard:', err)
    }
  }
}

async function addNode() {
  if (!newNode.value.hostname || !newNode.value.ip_address) return
  addingNode.value = true
  try {
    await registerNode({
      hostname: newNode.value.hostname,
      ip_address: newNode.value.ip_address,
      ssh_user: newNode.value.ssh_user || 'autobot',
      auth_method: newNode.value.auth_method as 'key' | 'password',
      ssh_password: newNode.value.auth_method === 'password' ? newNode.value.ssh_password : undefined,
      roles: [],
    })
    newNode.value = { hostname: '', ip_address: '', ssh_user: 'autobot', auth_method: 'key', ssh_password: '' }
    await loadNodes()
  } catch (err: unknown) {
    const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 'Failed to add node'
    alert(msg)
  } finally {
    addingNode.value = false
  }
}

async function testAllConnections() {
  testingConnections.value = true
  for (const node of nodes.value) {
    try {
      connectionResults.value[node.node_id] = 'testing'
      await testConnection({
        ip_address: node.ip_address,
        ssh_user: node.ssh_user || 'autobot',
        ssh_port: node.ssh_port || 22,
        auth_method: (node.auth_method || 'key') as 'key' | 'password',
      })
      connectionResults.value[node.node_id] = 'success'
    } catch {
      connectionResults.value[node.node_id] = 'failed'
    }
  }
  testingConnections.value = false
}

async function enrollAllNodes() {
  enrolling.value = true
  for (const node of nodes.value) {
    if (node.status === 'online') continue
    try {
      await enrollNode(node.node_id)
    } catch (err) {
      logger.error(`Failed to enroll ${node.hostname}:`, err)
    }
  }
  // Reload after a brief delay to let enrollment start
  setTimeout(async () => {
    await loadNodes()
    enrolling.value = false
  }, 3000)
}

function toggleRole(nodeId: string, roleName: string) {
  let current = nodeRoles.value[nodeId] || []
  if (current.includes(roleName)) {
    current = current.filter(r => r !== roleName)
  } else {
    // Enforce uniqueness: unassign this role from any other node (#1384)
    if (!INFRA_ROLES.includes(roleName)) {
      for (const node of nodes.value) {
        if (node.node_id !== nodeId) {
          const otherRoles = nodeRoles.value[node.node_id] || []
          if (otherRoles.includes(roleName)) {
            let updated = otherRoles.filter(r => r !== roleName)
            // Remove infra roles if no user roles remain
            const hasUser = updated.some(r => !INFRA_ROLES.includes(r))
            if (!hasUser) {
              updated = updated.filter(r => !INFRA_ROLES.includes(r))
            }
            nodeRoles.value[node.node_id] = updated
          }
        }
      }
    }
    current = [...current, roleName]
  }
  // Auto-inject/remove infra roles (#1344)
  const hasUserRoles = current.some(r => !INFRA_ROLES.includes(r))
  if (hasUserRoles) {
    for (const infra of INFRA_ROLES) {
      if (!current.includes(infra)) current.push(infra)
    }
  } else {
    current = current.filter(r => !INFRA_ROLES.includes(r))
  }
  nodeRoles.value[nodeId] = current
}

async function saveRoles() {
  savingRoles.value = true
  try {
    for (const node of nodes.value) {
      const roles = nodeRoles.value[node.node_id] || []
      await updateNodeRoles(node.node_id, roles as NodeRole[])
    }
  } catch (err) {
    logger.error('Failed to save roles:', err)
    throw err
  } finally {
    savingRoles.value = false
  }
}

async function saveAndContinueRoles() {
  await saveRoles()
  await completeStep('assign_roles')
}

// #7096: WebSocket + polling moved to useProvisionStore() so connection
// survives component unmount (user navigates away mid-provision). The view
// only consumes the store's reactive state via the computed proxies above.

function formatElapsed(seconds: number): string {
  if (seconds < 60) return `${seconds}s`
  const m = Math.floor(seconds / 60), s = seconds % 60
  if (m < 60) return `${m}m ${s}s`
  return `${Math.floor(m / 60)}h ${m % 60}m ${s}s`
}

function formatStage(stage: string): string {
  const stageLabels: Record<string, string> = {
    starting: 'Starting...',
    slm_starting: 'Preparing SLM server',
    slm_syncing: 'Syncing SLM backend',
    slm_restarting: 'Restarting SLM backend',
    slm_waiting: 'Waiting for SLM backend',
    slm_complete: 'SLM server updated',
    play1_start: 'Phase 1: SLM Server',
    play2_start: 'Phase 2: Infrastructure',
    nodes_starting: 'Updating infrastructure nodes',
    node_backend: 'Syncing backend node',
    node_frontend: 'Syncing frontend node',
    node_npu: 'Syncing NPU worker',
    node_browser: 'Syncing browser automation',
    node_complete: 'Node update complete',
    complete: 'Complete',
  }
  return stageLabels[stage] || stage.replace(/_/g, ' ')
}

function scrollProvisionLog() {
  nextTick(() => {
    if (logContainerRef.value) {
      logContainerRef.value.scrollTop = logContainerRef.value.scrollHeight
    }
  })
}

// #7096: log appends now happen in the store; watch + auto-scroll here
watch(() => provisionStore.logs.length, () => scrollProvisionLog())

async function provisionFleet() {
  // #7096: store handles state reset, WS connection, and survives unmount
  provisionStore.start()
  provisionStore.logs.push({ type: 'info', message: 'Starting fleet provisioning...' })

  try {
    await provisionWizardFleet(nodes.value.map(n => n.node_id))
  } catch (err: unknown) {
    const detail =
      (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
      'Unknown error'
    provisionStore.logs.push({ type: 'error', message: `ERROR: ${detail}` })
    provisionStore.disconnectWs()
  }
}

// #7096: NO disconnectProvisionWs() on unmount — store keeps the WebSocket
// alive across navigation so users can leave the wizard and return without
// losing provision visibility.

async function checkFleetHealth() {
  checkingHealth.value = true
  try {
    fleetHealth.value = await validateWizardFleet()
  } catch {
    fleetHealth.value = null
  } finally {
    checkingHealth.value = false
  }
}

function goToDashboard() {
  router.push({ name: 'fleet' })
}

function exitWizard() {
  router.push({ name: 'fleet' })
}

// ── Lifecycle ─────────────────────────────────────────────────────────────

onMounted(async () => {
  await loadWizardStatus()
  await loadNodes()
  await loadRoles()
  await loadExistingSecrets()
  // #7096: pick up any in-flight or recently-finished provision state
  // so the user sees live progress even after navigating away and back.
  await provisionStore.restoreFromBackend()
})
</script>

<style scoped>
.setup-wizard {
  max-width: 800px;
  margin: 0 auto;
  padding: 2rem;
  color: var(--text-primary, #e0e0e0);
}

.wizard-header {
  text-align: center;
  margin-bottom: 2rem;
  position: relative;
}

.wizard-header h1 {
  font-size: 1.8rem;
  font-weight: 600;
  margin: 0;
}

.wizard-header .subtitle {
  color: var(--text-secondary, #a0a0a0);
  margin-top: 0.25rem;
}

.header-actions {
  position: absolute;
  top: 0;
  right: 0;
  display: flex;
  gap: 0.5rem;
  align-items: center;
}

.skip-btn {
  background: none;
  border: 1px solid var(--border-color, #444);
  color: var(--text-secondary, #a0a0a0);
  padding: 0.4rem 0.8rem;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.85rem;
}

.skip-btn:hover {
  border-color: var(--text-primary, #e0e0e0);
  color: var(--text-primary, #e0e0e0);
}

.close-btn {
  background: none;
  border: 1px solid var(--border-color, #444);
  color: var(--text-secondary, #a0a0a0);
  width: 32px;
  height: 32px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 1rem;
  display: flex;
  align-items: center;
  justify-content: center;
}

.close-btn:hover {
  border-color: var(--color-danger, #ef4444);
  color: var(--color-danger, #ef4444);
}

/* Progress bar */
.progress-bar {
  display: flex;
  justify-content: space-between;
  margin-bottom: 2rem;
  padding: 0 1rem;
}

.progress-step {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex: 1;
  position: relative;
}

.step-indicator {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.8rem;
  font-weight: 600;
  margin-bottom: 0.4rem;
  transition: all 0.2s;
}

.progress-step.completed .step-indicator {
  background: var(--color-success, #22c55e);
  color: #fff;
}

.progress-step.current .step-indicator {
  background: var(--color-primary, #3b82f6);
  color: #fff;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.3);
}

.progress-step.upcoming .step-indicator {
  background: var(--bg-secondary, #2a2a2a);
  color: var(--text-secondary, #a0a0a0);
  border: 1px solid var(--border-color, #444);
}

.step-label {
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-secondary, #a0a0a0);
}

.progress-step.current .step-label {
  color: var(--color-primary, #3b82f6);
  font-weight: 600;
}

.check {
  font-size: 1rem;
}

/* Step content */
.step-panel {
  background: var(--bg-secondary, #1e1e1e);
  border: 1px solid var(--border-color, #333);
  border-radius: 8px;
  padding: 2rem;
}

.step-panel h2 {
  margin: 0 0 0.5rem;
  font-size: 1.4rem;
}

.step-panel > p {
  color: var(--text-secondary, #a0a0a0);
  margin-bottom: 1.5rem;
}

.info-box {
  background: var(--bg-tertiary, #252525);
  border: 1px solid var(--border-color, #444);
  border-radius: 6px;
  padding: 1rem 1.5rem;
  margin-bottom: 1.5rem;
}

.info-box h3 {
  margin: 0 0 0.5rem;
  font-size: 1rem;
}

.info-box ul {
  margin: 0;
  padding-left: 1.2rem;
}

.info-box li {
  margin-bottom: 0.3rem;
  color: var(--text-secondary, #a0a0a0);
}

/* Buttons */
.btn-primary,
.btn-secondary {
  padding: 0.6rem 1.5rem;
  border-radius: 6px;
  font-size: 0.9rem;
  font-weight: 500;
  cursor: pointer;
  border: none;
  transition: all 0.15s;
  margin-top: 1rem;
  margin-right: 0.5rem;
}

.btn-primary {
  background: var(--color-primary, #3b82f6);
  color: #fff;
}

.btn-primary:hover:not(:disabled) {
  background: #2563eb;
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-secondary {
  background: var(--bg-tertiary, #2a2a2a);
  color: var(--text-primary, #e0e0e0);
  border: 1px solid var(--border-color, #444);
}

.btn-secondary:hover:not(:disabled) {
  background: var(--bg-hover, #333);
}

.btn-secondary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Nodes list */
.nodes-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  margin-bottom: 1.5rem;
}

.node-card {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.75rem 1rem;
  background: var(--bg-tertiary, #252525);
  border: 1px solid var(--border-color, #333);
  border-radius: 6px;
}

.node-info {
  display: flex;
  gap: 1rem;
  align-items: center;
}

.node-info .ip {
  color: var(--text-secondary, #a0a0a0);
  font-family: monospace;
  font-size: 0.85rem;
}

.status-badge {
  padding: 0.2rem 0.6rem;
  border-radius: 12px;
  font-size: 0.75rem;
  font-weight: 500;
  text-transform: uppercase;
}

.status-badge.online,
.status-badge.success {
  background: rgba(34, 197, 94, 0.15);
  color: #22c55e;
}

.status-badge.pending,
.status-badge.untested,
.status-badge.testing {
  background: rgba(234, 179, 8, 0.15);
  color: #eab308;
}

.status-badge.failed,
.status-badge.error,
.status-badge.offline {
  background: rgba(239, 68, 68, 0.15);
  color: #ef4444;
}

.status-badge.enrolling {
  background: rgba(59, 130, 246, 0.15);
  color: #3b82f6;
}

.empty-state {
  text-align: center;
  color: var(--text-secondary, #a0a0a0);
  padding: 2rem;
  font-style: italic;
}

/* Add node form */
.add-node-form {
  background: var(--bg-tertiary, #252525);
  border: 1px solid var(--border-color, #444);
  border-radius: 6px;
  padding: 1rem 1.5rem;
  margin-bottom: 1rem;
}

.add-node-form h3 {
  margin: 0 0 0.75rem;
  font-size: 1rem;
}

.form-row {
  display: flex;
  gap: 0.75rem;
  margin-bottom: 0.75rem;
}

.form-row input,
.form-row select,
.form-row > .field {
  flex: 1;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.field > input,
.field > select {
  width: 100%;
}

.field.full-width {
  width: 100%;
  margin-bottom: 0.75rem;
}

.field-label {
  font-size: 0.75rem;
  font-weight: 500;
  color: var(--text-secondary, #a0a0a0);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

input,
select {
  background: var(--bg-primary, #1a1a1a);
  border: 1px solid var(--border-color, #444);
  color: var(--text-primary, #e0e0e0);
  padding: 0.5rem 0.75rem;
  border-radius: 4px;
  font-size: 0.9rem;
}

input:focus,
select:focus {
  outline: none;
  border-color: var(--color-primary, #3b82f6);
}

input.full-width {
  width: 100%;
  margin-bottom: 0.75rem;
}

/* Role assignment */
.role-assignment {
  margin-bottom: 1.5rem;
  padding-bottom: 1rem;
  border-bottom: 1px solid var(--border-color, #333);
}

.role-assignment h3 {
  margin: 0 0 0.5rem;
  font-size: 1rem;
}

.role-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.role-chip {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  padding: 0.3rem 0.7rem;
  background: var(--bg-tertiary, #252525);
  border: 1px solid var(--border-color, #444);
  border-radius: 16px;
  font-size: 0.8rem;
  cursor: pointer;
  transition: all 0.15s;
}

.role-chip.selected {
  background: rgba(59, 130, 246, 0.15);
  border-color: var(--color-primary, #3b82f6);
  color: var(--color-primary, #3b82f6);
}

.role-chip input[type="checkbox"] {
  display: none;
}

.role-section {
  margin-bottom: 0.75rem;
}

.section-header {
  display: block;
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-secondary, #aaa);
  margin-bottom: 0.4rem;
}

.optional-header {
  color: var(--text-muted, #888);
}

.optional-chip {
  opacity: 0.85;
}

.optional-chip.selected {
  opacity: 1;
}

/* Deployment group sub-headers within role sections (#3192) */
.role-group {
  margin-bottom: 0.6rem;
}

.role-group-header {
  display: flex;
  align-items: baseline;
  gap: 0.5rem;
  margin-bottom: 0.3rem;
}

.role-group-label {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--text-primary, #ccc);
}

.role-group-desc {
  font-size: 0.68rem;
  color: var(--text-muted, #888);
  font-style: italic;
}

.infra-roles-row {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  margin-top: 0.4rem;
  font-size: 0.75rem;
  color: var(--text-muted, #888);
}

.infra-label {
  font-style: italic;
}

.infra-chip {
  background: var(--bg-tertiary, #252525);
  border-color: var(--border-color, #555);
  opacity: 0.7;
  cursor: default;
  font-size: 0.75rem;
}

/* Role state indicators (#1353) */
.state-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--border-color, #555);
  flex-shrink: 0;
}

.state-running .state-dot {
  background: #22c55e;
  box-shadow: 0 0 4px rgba(34, 197, 94, 0.5);
}

.state-assigned .state-dot {
  background: var(--color-primary, #3b82f6);
}

.state-available .state-dot {
  background: var(--border-color, #555);
}

.state-running {
  border-color: rgba(34, 197, 94, 0.4);
}

/* Provision log */
.provision-log {
  background: #0d0d0d;
  border: 1px solid var(--border-color, #333);
  border-radius: 6px;
  padding: 1rem;
  max-height: 400px;
  overflow-y: auto;
  margin-bottom: 1rem;
  font-family: monospace;
  font-size: 0.8rem;
}

.log-entry {
  padding: 2px 0;
  white-space: pre-wrap;
  word-break: break-all;
}

.log-info {
  color: #a0d0a0;
}

.log-task {
  color: #60a5fa;
  font-weight: 600;
}

.log-success {
  color: #4ade80;
}

.log-error {
  color: #f87171;
}

.log-warning {
  color: #fbbf24;
}

.provision-status-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.5rem 1rem;
  margin-bottom: 0.5rem;
  background: rgba(96, 165, 250, 0.1);
  border: 1px solid rgba(96, 165, 250, 0.3);
  border-radius: 6px;
  font-size: 0.85rem;
}

.provision-stage {
  color: #60a5fa;
  font-weight: 600;
}

.provision-elapsed {
  color: var(--text-secondary, #999);
}

.provision-phases {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  margin-bottom: 0.5rem;
}

.provision-phase {
  padding: 0.2rem 0.6rem;
  border-radius: 4px;
  font-size: 0.75rem;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: var(--text-secondary, #666);
}

.phase-active {
  border-color: rgba(96, 165, 250, 0.5);
  color: #60a5fa;
  font-weight: 600;
}

.phase-done {
  border-color: rgba(74, 222, 128, 0.3);
  color: #4ade80;
}

.provision-current-task {
  padding: 0.35rem 0.75rem;
  margin-bottom: 0.5rem;
  background: rgba(96, 165, 250, 0.06);
  border: 1px solid rgba(96, 165, 250, 0.2);
  border-radius: 4px;
  font-family: monospace;
  font-size: 0.78rem;
  color: #93c5fd;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.task-spinner {
  display: inline-block;
  margin-right: 0.4rem;
  animation: spin 1.5s linear infinite;
}

.log-phase {
  color: #a78bfa;
  font-weight: 600;
  margin-top: 0.25rem;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* Health summary */
.health-summary {
  margin-bottom: 1.5rem;
}

.health-badge {
  display: inline-block;
  padding: 0.3rem 1rem;
  border-radius: 16px;
  font-weight: 600;
  text-transform: uppercase;
  font-size: 0.85rem;
  margin-bottom: 0.75rem;
}

.health-badge.healthy {
  background: rgba(34, 197, 94, 0.15);
  color: #22c55e;
}

.health-badge.degraded {
  background: rgba(234, 179, 8, 0.15);
  color: #eab308;
}

.health-badge.critical {
  background: rgba(239, 68, 68, 0.15);
  color: #ef4444;
}

/* Complete panel */
.complete-panel {
  text-align: center;
}

.success-icon {
  width: 64px;
  height: 64px;
  border-radius: 50%;
  background: var(--color-success, #22c55e);
  color: #fff;
  font-size: 2rem;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 1rem;
}

/* Secrets / API Keys (#3079) */
.secrets-form {
  margin-bottom: 1.5rem;
}

.secret-entry {
  background: var(--bg-tertiary, #252525);
  border: 1px solid var(--border-color, #444);
  border-radius: 6px;
  padding: 1rem 1.5rem;
  margin-bottom: 1rem;
}

.secret-entry h3 {
  margin: 0 0 0.25rem;
  font-size: 1rem;
}

.secret-desc {
  color: var(--text-secondary, #a0a0a0);
  font-size: 0.85rem;
  margin-bottom: 0.75rem;
}

.secret-desc a {
  color: var(--color-accent, #4fc3f7);
}

.success-box {
  border-color: var(--color-success, #4caf50);
  color: var(--color-success, #4caf50);
}
</style>
