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
      <h1>AutoBot Setup Wizard</h1>
      <p class="subtitle">Configure your fleet in a few easy steps</p>
      <div class="header-actions">
        <button
          v-if="currentStep !== 'complete'"
          class="skip-btn"
          @click="skipWizard"
        >
          Skip Setup
        </button>
        <button
          class="close-btn"
          @click="exitWizard"
          title="Exit wizard without completing"
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
        <h2>Welcome to AutoBot</h2>
        <p>
          Your SLM (Service Lifecycle Manager) is up and running. This wizard
          will guide you through adding and configuring your fleet nodes.
        </p>
        <div class="info-box">
          <h3>What you'll need:</h3>
          <ul>
            <li>IP addresses of your fleet VMs</li>
            <li>SSH access credentials (key or password)</li>
            <li>Knowledge of which services each node should run</li>
          </ul>
        </div>
        <button class="btn-primary" @click="completeStep('welcome')">
          Get Started
        </button>
      </div>

      <!-- Add Nodes -->
      <div v-if="currentStep === 'add_nodes'" class="step-panel">
        <h2>Add Fleet Nodes</h2>
        <p>Add the VMs that will form your AutoBot fleet.</p>

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
        <p v-else class="empty-state">No nodes added yet.</p>

        <div class="add-node-form">
          <h3>Add a Node</h3>
          <div class="form-row">
            <input v-model="newNode.hostname" placeholder="Hostname (e.g. frontend-01)" />
            <input v-model="newNode.ip_address" placeholder="IP Address (e.g. 172.16.168.21)" />
          </div>
          <div class="form-row">
            <input v-model="newNode.ssh_user" placeholder="SSH User (default: autobot)" />
            <select v-model="newNode.auth_method">
              <option value="key">SSH Key</option>
              <option value="password">Password</option>
            </select>
          </div>
          <input
            v-if="newNode.auth_method === 'password'"
            v-model="newNode.ssh_password"
            type="password"
            placeholder="SSH Password"
            class="full-width"
          />
          <button class="btn-secondary" @click="addNode" :disabled="addingNode">
            {{ addingNode ? 'Adding...' : 'Add Node' }}
          </button>
        </div>

        <button
          class="btn-primary"
          @click="completeStep('add_nodes')"
          :disabled="nodes.length === 0"
        >
          Continue
        </button>
      </div>

      <!-- Test Connections -->
      <div v-if="currentStep === 'test_connections'" class="step-panel">
        <h2>Test Connections</h2>
        <p>Verify SSH connectivity to all nodes before proceeding.</p>

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
          Continue
        </button>
      </div>

      <!-- Enroll Agents -->
      <div v-if="currentStep === 'enroll_agents'" class="step-panel">
        <h2>Enroll SLM Agents</h2>
        <p>Deploy the SLM monitoring agent to each node.</p>

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
          Continue
        </button>
      </div>

      <!-- Assign Roles -->
      <div v-if="currentStep === 'assign_roles'" class="step-panel">
        <h2>Assign Roles</h2>
        <p>Choose which services each node should run.</p>

        <div class="role-assignment" v-for="node in nodes" :key="node.node_id">
          <h3>{{ node.hostname }} ({{ node.ip_address }})</h3>

          <!-- Core Services (required) (#1350) -->
          <div class="role-section">
            <span class="section-header">Core Services</span>
            <div class="role-chips">
              <label
                v-for="role in requiredRoles"
                :key="role.name"
                class="role-chip"
                :class="{ selected: (nodeRoles[node.node_id] || []).includes(role.name) }"
                :title="role.display_name"
              >
                <input
                  type="checkbox"
                  :value="role.name"
                  :checked="(nodeRoles[node.node_id] || []).includes(role.name)"
                  @change="toggleRole(node.node_id, role.name)"
                />
                {{ role.display_name || role.name }}
              </label>
            </div>
          </div>

          <!-- Optional Services (#1350) -->
          <div class="role-section" v-if="optionalRoles.length">
            <span class="section-header optional-header">Optional Services</span>
            <div class="role-chips">
              <label
                v-for="role in optionalRoles"
                :key="role.name"
                class="role-chip optional-chip"
                :class="{ selected: (nodeRoles[node.node_id] || []).includes(role.name) }"
                :title="role.degraded_without.length
                  ? 'Without: ' + role.degraded_without.join('; ')
                  : role.display_name"
              >
                <input
                  type="checkbox"
                  :value="role.name"
                  :checked="(nodeRoles[node.node_id] || []).includes(role.name)"
                  @change="toggleRole(node.node_id, role.name)"
                />
                {{ role.display_name || role.name }}
              </label>
            </div>
          </div>

          <!-- Infra roles: auto-deployed, shown as locked (#1344) -->
          <div
            v-if="(nodeRoles[node.node_id] || []).some(r => !INFRA_ROLES.includes(r))"
            class="infra-roles-row"
          >
            <span class="infra-label">Auto-deployed:</span>
            <span
              v-for="infra in INFRA_ROLES"
              :key="infra"
              class="role-chip infra-chip"
            >
              {{ infra === 'autobot-shared' ? 'Shared Library' : 'SLM Agent' }}
            </span>
          </div>
        </div>

        <button class="btn-secondary" @click="saveRoles" :disabled="savingRoles">
          {{ savingRoles ? 'Saving...' : 'Save Role Assignments' }}
        </button>
        <button class="btn-primary" @click="completeStep('assign_roles')">
          Continue
        </button>
      </div>

      <!-- Provision Fleet -->
      <div v-if="currentStep === 'provision_fleet'" class="step-panel">
        <h2>Provision Fleet</h2>
        <p>
          Deploy all assigned services to your fleet nodes via Ansible.
          This may take several minutes.
        </p>

        <div v-if="provisionOutput" class="provision-log">
          <pre>{{ provisionOutput }}</pre>
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
          Continue
        </button>
      </div>

      <!-- Verify Health -->
      <div v-if="currentStep === 'verify_health'" class="step-panel">
        <h2>Verify Fleet Health</h2>
        <p>Checking that all services are running correctly.</p>

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
          Continue
        </button>
      </div>

      <!-- Complete -->
      <div v-if="currentStep === 'complete'" class="step-panel complete-panel">
        <div class="success-icon">&#10003;</div>
        <h2>Setup Complete!</h2>
        <p>Your AutoBot fleet is configured and ready to use.</p>
        <button class="btn-primary" @click="goToDashboard">
          Go to Dashboard
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useSlmApi } from '@/composables/useSlmApi'
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
  getWizardStatus,
  completeWizardStep,
  skipWizardSetup,
  provisionWizardFleet,
  validateWizardFleet,
} = useSlmApi()

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
  ssh_user?: string
  ssh_port?: number
  auth_method?: string
}

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

const INFRA_ROLES = ['autobot-shared', 'slm-agent']

const availableRoles = ref<RoleInfo[]>([])
const nodeRoles = ref<Record<string, string[]>>({})
const savingRoles = ref(false)

const requiredRoles = computed(() => availableRoles.value.filter(r => r.required))
const optionalRoles = computed(() => availableRoles.value.filter(r => !r.required))

// ── Provisioning ──────────────────────────────────────────────────────────

const provisioning = ref(false)
const provisionOutput = ref('')
const provisionComplete = ref(false)

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
    // Filter out SLM-internal and infra roles (#1349, #1344)
    availableRoles.value = result
      .filter(r => !r.name.startsWith('slm-') && !INFRA_ROLES.includes(r.name))
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
      await updateNodeRoles(node.node_id, roles as any)
    }
  } catch (err) {
    logger.error('Failed to save roles:', err)
  } finally {
    savingRoles.value = false
  }
}

async function provisionFleet() {
  provisioning.value = true
  provisionOutput.value = 'Starting fleet provisioning...\n'
  try {
    const data = await provisionWizardFleet(
      nodes.value.map(n => n.node_id)
    )
    provisionOutput.value += data.output || 'Provisioning completed.\n'
    provisionComplete.value = true
  } catch (err: unknown) {
    const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 'Unknown error'
    provisionOutput.value += `\nERROR: ${detail}\n`
  } finally {
    provisioning.value = false
  }
}

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
.form-row select {
  flex: 1;
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

/* Provision log */
.provision-log {
  background: #0d0d0d;
  border: 1px solid var(--border-color, #333);
  border-radius: 6px;
  padding: 1rem;
  max-height: 300px;
  overflow-y: auto;
  margin-bottom: 1rem;
}

.provision-log pre {
  margin: 0;
  font-family: monospace;
  font-size: 0.8rem;
  white-space: pre-wrap;
  color: #a0d0a0;
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
</style>
