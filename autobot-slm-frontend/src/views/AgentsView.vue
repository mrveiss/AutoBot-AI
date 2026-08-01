<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Agent Management View (Issue #760 Phase 4, #942)
 *
 * Provides UI for viewing and managing agent LLM configurations.
 * Endpoint is selected by fleet node (auto-constructs http://ip:<ollama-port>)
 * or entered manually via the Custom option.
 */

import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import config from '@/config/ssot-config'
import { slmApiClient } from '@/utils/ApiClient'
import ExternalAgentsView from '@/views/ExternalAgentsView.vue'
import OrgChartTab from '@/components/agents/OrgChartTab.vue'
import ConfigHistoryTab from '@/components/agents/ConfigHistoryTab.vue'
import ProcessMonitorTab from '@/components/agents/ProcessMonitorTab.vue'

interface Agent {
  agent_id: string
  name: string
  description: string
  llm_provider: string
  llm_model: string
  llm_endpoint: string
  llm_timeout: number
  llm_temperature: number
  is_active: boolean
  is_default: boolean
}

interface FleetNode {
  node_id: string
  hostname: string
  ip_address: string
  status: string
  roles: string[]
}

const OLLAMA_PORT = config.port.ollama
const CUSTOM_VALUE = '__custom__'

const route = useRoute()
const router = useRouter()

// Active tab — route-based (#1404, #1405, #1406: added admin tabs)
type AgentTab = 'local-agents' | 'external-agents' | 'org-chart' | 'config-history' | 'processes'
const validTabs: AgentTab[] = ['local-agents', 'external-agents', 'org-chart', 'config-history', 'processes']
function resolveAgentTab(param: unknown): AgentTab {
  return validTabs.includes(param as AgentTab) ? (param as AgentTab) : 'local-agents'
}
const activeTab = computed(() => resolveAgentTab(route.params.tab))
function navigateToTab(tab: AgentTab): void {
  router.push({ name: 'agents', params: { tab } })
}
const agents = ref<Agent[]>([])
const nodes = ref<FleetNode[]>([])
const loading = ref(true)
const error = ref<string | null>(null)
const selectedAgent = ref<Agent | null>(null)
const isEditing = ref(false)

const editForm = ref({
  llm_provider: '',
  llm_model: '',
  llm_endpoint: '',
  endpoint_node: '' as string, // node_id or CUSTOM_VALUE
  llm_timeout: 30,
  llm_temperature: 0.7,
  is_active: true,
})

const providers = ['ollama', 'openai', 'anthropic']

// ── helpers ────────────────────────────────────────────────────────────────

function endpointForNode(node: FleetNode): string {
  return `http://${node.ip_address}:${OLLAMA_PORT}`
}

/** Return the node whose Ollama URL matches the stored endpoint, or null. */
function nodeForEndpoint(endpoint: string): FleetNode | null {
  return nodes.value.find((n) => endpointForNode(n) === endpoint) ?? null
}

/** Human-readable label for the endpoint in read-only mode. */
function endpointLabel(endpoint: string): string {
  const match = nodeForEndpoint(endpoint)
  if (match) return `${match.node_id} (${match.ip_address}:${OLLAMA_PORT})`
  return endpoint || '—'
}

// ── data fetching ──────────────────────────────────────────────────────────

async function fetchAgents() {
  loading.value = true
  error.value = null
  try {
    // The three calls in this view built `Bearer ${authStore.token}`
    // UNCONDITIONALLY, so with no session they sent the literal string
    // `Bearer null` — a malformed credential rather than an absent one. The
    // client omits the header when there is no token, which also lets its 401
    // handler tell "session rejected" (clear + redirect to /login) apart from
    // "never had one" (log only); and it reads the token from storage per
    // request rather than from a ref seeded there once, at store construction
    // (`stores/auth.ts:66`), which goes stale the moment a token lands in
    // storage through any other path (#13140).
    const data = await slmApiClient.get<{ agents?: Agent[] }>('/agents')
    agents.value = data.agents || []
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Failed to fetch agents'
  } finally {
    loading.value = false
  }
}

async function fetchNodes() {
  try {
    // A non-OK response used to `return` silently; `get()` rejects, so it now
    // lands in the catch below — the same outcome (fall back to Custom mode)
    // reached by one code path instead of two.
    const data = await slmApiClient.get<{ nodes?: FleetNode[] }>('/nodes')
    nodes.value = (data.nodes || []).filter(
      (n: FleetNode) => n.status === 'online',
    )
  } catch {
    // Non-critical — fall back to Custom mode
  }
}

// ── selection ──────────────────────────────────────────────────────────────

function selectAgent(agent: Agent) {
  selectedAgent.value = agent
  const matchedNode = nodeForEndpoint(agent.llm_endpoint)
  editForm.value = {
    llm_provider: agent.llm_provider,
    llm_model: agent.llm_model,
    llm_endpoint: agent.llm_endpoint,
    endpoint_node: matchedNode ? matchedNode.node_id : CUSTOM_VALUE,
    llm_timeout: agent.llm_timeout,
    llm_temperature: agent.llm_temperature,
    is_active: agent.is_active,
  }
  isEditing.value = false
}

function startEditing() {
  isEditing.value = true
}

function cancelEditing() {
  if (selectedAgent.value) selectAgent(selectedAgent.value)
}

// ── endpoint node watcher ──────────────────────────────────────────────────

function onEndpointNodeChange(val: string) {
  if (val === CUSTOM_VALUE) return
  const node = nodes.value.find((n) => n.node_id === val)
  if (node) editForm.value.llm_endpoint = endpointForNode(node)
}

// ── save ───────────────────────────────────────────────────────────────────

async function saveAgent() {
  if (!selectedAgent.value) return
  try {
    const payload = {
      llm_provider: editForm.value.llm_provider,
      llm_model: editForm.value.llm_model,
      llm_endpoint: editForm.value.llm_endpoint,
      llm_timeout: editForm.value.llm_timeout,
      llm_temperature: editForm.value.llm_temperature,
      is_active: editForm.value.is_active,
    }
    await slmApiClient.put(`/agents/${selectedAgent.value.agent_id}`, payload)
    await fetchAgents()
    const updated = agents.value.find(
      (a) => a.agent_id === selectedAgent.value?.agent_id,
    )
    if (updated) selectAgent(updated)
    isEditing.value = false
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Failed to save agent'
  }
}

// ── computed ───────────────────────────────────────────────────────────────

const activeAgentCount = computed(() => agents.value.filter((a) => a.is_active).length)
const isCustomEndpoint = computed(() => editForm.value.endpoint_node === CUSTOM_VALUE)

onMounted(() => {
  fetchAgents()
  fetchNodes()
})
</script>

<template>
  <div class="agents-view">
    <header class="view-header">
      <h1>{{ $t('agentsView.agentManagement') }}</h1>
      <p class="subtitle">{{ $t('agentsView.configureLLMSettingsFor') }}</p>
    </header>

    <!-- Tab navigation -->
    <div class="border-b border-gray-200 mb-6">
      <nav class="flex gap-4">
        <button
          @click="navigateToTab('local-agents')"
          :class="[
            'py-4 px-1 border-b-2 font-medium text-sm',
            activeTab === 'local-agents'
              ? 'border-primary-500 text-primary-600'
              : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300',
          ]"
        >{{ $t('agentsView.localAgents') }}</button>
        <button
          @click="navigateToTab('external-agents')"
          :class="[
            'py-4 px-1 border-b-2 font-medium text-sm',
            activeTab === 'external-agents'
              ? 'border-primary-500 text-primary-600'
              : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300',
          ]"
        >{{ $t('agentsView.externalAgents') }}</button>
        <button
          @click="navigateToTab('org-chart')"
          :class="[
            'py-4 px-1 border-b-2 font-medium text-sm',
            activeTab === 'org-chart'
              ? 'border-primary-500 text-primary-600'
              : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300',
          ]"
        >{{ $t('agentsView.orgChart') }}</button>
        <button
          @click="navigateToTab('config-history')"
          :class="[
            'py-4 px-1 border-b-2 font-medium text-sm',
            activeTab === 'config-history'
              ? 'border-primary-500 text-primary-600'
              : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300',
          ]"
        >{{ $t('agentsView.configHistory') }}</button>
        <button
          @click="navigateToTab('processes')"
          :class="[
            'py-4 px-1 border-b-2 font-medium text-sm',
            activeTab === 'processes'
              ? 'border-primary-500 text-primary-600'
              : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300',
          ]"
        >{{ $t('agentsView.processes') }}</button>
      </nav>
    </div>

    <!-- Local Agents -->
    <div v-if="activeTab === 'local-agents'">

    <div v-if="error" class="error-banner">
      {{ error }}
      <button @click="error = null">{{ $t('agentsView.dismiss') }}</button>
    </div>

    <div class="agents-stats">
      <div class="stat-card">
        <span class="stat-value">{{ agents.length }}</span>
        <span class="stat-label">{{ $t('agentsView.totalAgents') }}</span>
      </div>
      <div class="stat-card">
        <span class="stat-value">{{ activeAgentCount }}</span>
        <span class="stat-label">{{ $t('agentsView.active') }}</span>
      </div>
      <div class="stat-card">
        <span class="stat-value">{{ agents.length - activeAgentCount }}</span>
        <span class="stat-label">{{ $t('agentsView.inactive') }}</span>
      </div>
    </div>

    <div class="agents-container">
      <!-- Agent list -->
      <div class="agents-list">
        <h2>{{ $t('agentsView.agents') }}</h2>
        <div v-if="loading" class="loading">{{ $t('agentsView.loadingAgents') }}</div>
        <ul v-else>
          <li
            v-for="agent in agents"
            :key="agent.agent_id"
            :class="{
              selected: selectedAgent?.agent_id === agent.agent_id,
              inactive: !agent.is_active,
            }"
            @click="selectAgent(agent)"
          >
            <span class="agent-name">{{ agent.name }}</span>
            <span class="agent-model">{{ agent.llm_model }}</span>
            <span v-if="agent.is_default" class="default-badge">{{ $t('agentsView.default') }}</span>
          </li>
        </ul>
      </div>

      <!-- Agent detail -->
      <div v-if="selectedAgent" class="agent-detail">
        <div class="detail-header">
          <h2>{{ selectedAgent.name }}</h2>
          <div class="actions">
            <button v-if="!isEditing" class="btn-edit" @click="startEditing">{{ $t('agentsView.edit') }}</button>
            <template v-else>
              <button class="btn-save" @click="saveAgent">{{ $t('agentsView.save') }}</button>
              <button class="btn-cancel" @click="cancelEditing">{{ $t('agentsView.cancel') }}</button>
            </template>
          </div>
        </div>

        <p class="description">{{ selectedAgent.description }}</p>

        <div class="config-form">
          <!-- Agent ID (always read-only) -->
          <div class="form-group">
            <label>{{ $t('agentsView.agentID') }}</label>
            <input type="text" :value="selectedAgent.agent_id" disabled />
          </div>

          <!-- LLM Provider -->
          <div class="form-group">
            <label>{{ $t('agentsView.lLMProvider') }}</label>
            <select v-model="editForm.llm_provider" :disabled="!isEditing">
              <option v-for="p in providers" :key="p" :value="p">{{ p }}</option>
            </select>
          </div>

          <!-- LLM Model -->
          <div class="form-group">
            <label>{{ $t('agentsView.lLMModel') }}</label>
            <input v-model="editForm.llm_model" :disabled="!isEditing" />
          </div>

          <!-- LLM Endpoint — node selector or custom -->
          <div class="form-group endpoint-group">
            <label>{{ $t('agentsView.lLMEndpoint') }}</label>

            <!-- Read-only view -->
            <div v-if="!isEditing" class="endpoint-readonly">
              {{ endpointLabel(selectedAgent.llm_endpoint) }}
            </div>

            <!-- Edit view -->
            <template v-else>
              <select
                v-model="editForm.endpoint_node"
                class="node-select"
                @change="onEndpointNodeChange(editForm.endpoint_node)"
              >
                <optgroup :label="$t('agentsView.fleetNodes')">
                  <option
                    v-for="node in nodes"
                    :key="node.node_id"
                    :value="node.node_id"
                  >
                    {{ node.node_id }} — {{ node.ip_address }}:{{ OLLAMA_PORT }}
                  </option>
                </optgroup>
                <option :value="CUSTOM_VALUE">{{ $t('agentsView.custom') }}</option>
              </select>

              <input
                v-if="isCustomEndpoint"
                v-model="editForm.llm_endpoint"
                class="custom-endpoint-input"
                :placeholder="`http://host:${config.port.ollama}`"
              />

              <span v-else class="endpoint-hint">
                → {{ editForm.llm_endpoint }}
              </span>
            </template>
          </div>

          <!-- Timeout -->
          <div class="form-group">
            <label>{{ $t('agentsView.timeoutSeconds') }}</label>
            <input
              v-model.number="editForm.llm_timeout"
              type="number"
              :disabled="!isEditing"
              min="1"
              max="300"
            />
          </div>

          <!-- Temperature -->
          <div class="form-group">
            <label>{{ $t('agentsView.temperature') }}</label>
            <input
              v-model.number="editForm.llm_temperature"
              type="number"
              :disabled="!isEditing"
              min="0"
              max="2"
              step="0.1"
            />
          </div>

          <!-- Active -->
          <div class="form-group">
            <label class="checkbox-label">
              <input
                v-model="editForm.is_active"
                type="checkbox"
                :disabled="!isEditing"
              />{{ $t('agentsView.active') }}</label>
          </div>
        </div>
      </div>

      <div v-else class="agent-detail empty">
        <p>{{ $t('agentsView.selectAnAgentToViewAnd') }}</p>
      </div>
    </div>

    </div><!-- /local-agents -->

    <!-- External Agents -->
    <div v-else-if="activeTab === 'external-agents'">
      <ExternalAgentsView />
    </div>

    <!-- Org Chart (#1405) -->
    <div v-else-if="activeTab === 'org-chart'">
      <OrgChartTab />
    </div>

    <!-- Config History (#1404) -->
    <div v-else-if="activeTab === 'config-history'">
      <ConfigHistoryTab />
    </div>

    <!-- Processes (#1406) -->
    <div v-else-if="activeTab === 'processes'">
      <ProcessMonitorTab />
    </div>

  </div>
</template>

<style scoped>
.agents-view {
  padding: var(--spacing-6);
  max-width: var(--content-max-width);
  margin: 0 auto;
}

.view-header {
  margin-bottom: var(--spacing-6);
}

.view-header h1 {
  font-size: 28px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.subtitle {
  color: var(--text-secondary);
  margin-top: var(--spacing-1);
}

.error-banner {
  background: var(--slm-red-100);
  border: 1px solid var(--color-danger-500);
  color: var(--slm-red-700);
  padding: var(--spacing-3) var(--spacing-4);
  border-radius: var(--radius-lg);
  margin-bottom: var(--spacing-4);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.agents-stats {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--spacing-4);
  margin-bottom: var(--spacing-6);
}

.stat-card {
  background: var(--color-white);
  padding: var(--spacing-5);
  border-radius: var(--radius-xl);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  text-align: center;
}

.stat-value {
  display: block;
  font-size: 32px;
  font-weight: 700;
  color: var(--primary);
}

.stat-label {
  color: var(--text-secondary);
  font-size: var(--text-sm);
}

.agents-container {
  display: grid;
  grid-template-columns: 350px 1fr;
  gap: var(--spacing-6);
}

.agents-list {
  background: var(--color-white);
  border-radius: var(--radius-xl);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  padding: var(--spacing-4);
}

.agents-list h2 {
  font-size: var(--text-lg);
  font-weight: 600;
  margin: 0 0 var(--spacing-4) 0;
  padding-bottom: var(--spacing-3);
  border-bottom: 1px solid var(--slm-gray-200);
}

.agents-list ul {
  list-style: none;
  padding: 0;
  margin: 0;
  max-height: 600px;
  overflow-y: auto;
}

.agents-list li {
  padding: var(--spacing-3);
  border-radius: var(--radius-lg);
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
  margin-bottom: var(--spacing-1);
}

.agents-list li:hover {
  background: var(--slm-gray-100);
}

.agents-list li.selected {
  background: var(--slm-indigo-100);
}

.agents-list li.inactive {
  opacity: 0.6;
}

.agent-name {
  font-weight: 500;
  color: var(--text-primary);
}

.agent-model {
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.default-badge {
  font-size: 10px;
  background: var(--slm-indigo-500);
  color: var(--color-white);
  padding: 2px var(--spacing-2);
  border-radius: var(--radius-default);
  align-self: flex-start;
}

.agent-detail {
  background: var(--color-white);
  border-radius: var(--radius-xl);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  padding: var(--spacing-6);
}

.agent-detail.empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 400px;
  color: var(--text-secondary);
}

.detail-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-3);
}

.detail-header h2 {
  font-size: var(--text-xl);
  font-weight: 600;
  margin: 0;
}

.description {
  color: var(--text-secondary);
  margin-bottom: var(--spacing-6);
  font-size: var(--text-sm);
}

.config-form {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--spacing-4);
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.endpoint-group {
  grid-column: 1 / -1;
}

.form-group label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
}

.form-group input,
.form-group select {
  padding: 10px var(--spacing-3);
  border: 1px solid var(--slm-gray-300);
  border-radius: var(--radius-lg);
  font-size: var(--text-sm);
}

.form-group input:disabled,
.form-group select:disabled {
  background: var(--slm-gray-50);
  color: var(--text-secondary);
}

.node-select {
  width: 100%;
  padding: 10px var(--spacing-3);
  border: 1px solid var(--slm-gray-300);
  border-radius: var(--radius-lg);
  font-size: var(--text-sm);
  background: var(--color-white);
  cursor: pointer;
}

.custom-endpoint-input {
  margin-top: var(--spacing-2);
  width: 100%;
  padding: 10px var(--spacing-3);
  border: 1px solid var(--slm-indigo-500);
  border-radius: var(--radius-lg);
  font-size: var(--text-sm);
  font-family: monospace;
  box-sizing: border-box;
}

.endpoint-hint {
  display: block;
  margin-top: 6px;
  font-size: 13px;
  font-family: monospace;
  color: var(--text-secondary);
}

.endpoint-readonly {
  padding: 10px var(--spacing-3);
  border: 1px solid var(--slm-gray-200);
  border-radius: var(--radius-lg);
  font-size: var(--text-sm);
  background: var(--slm-gray-50);
  color: var(--text-secondary);
  font-family: monospace;
}

.checkbox-label {
  flex-direction: row !important;
  align-items: center;
  gap: var(--spacing-2) !important;
}

.checkbox-label input {
  width: auto;
}

.actions {
  display: flex;
  gap: var(--spacing-2);
}

.btn-edit,
.btn-save,
.btn-cancel {
  padding: var(--spacing-2) var(--spacing-4);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  border: none;
}

.btn-edit {
  background: var(--slm-indigo-500);
  color: var(--color-white);
}

.btn-save {
  background: var(--slm-emerald-500);
  color: var(--color-white);
}

.btn-cancel {
  background: var(--slm-gray-200);
  color: var(--slm-gray-700);
}

.loading {
  text-align: center;
  color: var(--text-secondary);
  padding: var(--spacing-10);
}
</style>
