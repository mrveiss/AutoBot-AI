<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Agent Management View (Issue #760 Phase 4, #942)
 *
 * Provides UI for viewing and managing agent LLM configurations.
 * Endpoint is selected by fleet node (auto-constructs http://ip:11434)
 * or entered manually via the Custom option.
 */

import { computed, onMounted, ref } from 'vue'
import { useAuthStore } from '@/stores/auth'

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

const OLLAMA_PORT = 11434
const CUSTOM_VALUE = '__custom__'

const authStore = useAuthStore()
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
    const response = await fetch('/api/agents', {
      headers: { Authorization: `Bearer ${authStore.token}` },
    })
    if (!response.ok) throw new Error(`Failed to fetch agents: ${response.status}`)
    const data = await response.json()
    agents.value = data.agents || []
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Failed to fetch agents'
  } finally {
    loading.value = false
  }
}

async function fetchNodes() {
  try {
    const response = await fetch('/api/nodes', {
      headers: { Authorization: `Bearer ${authStore.token}` },
    })
    if (!response.ok) return
    const data = await response.json()
    nodes.value = (data.nodes || data || []).filter(
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
    const response = await fetch(`/api/agents/${selectedAgent.value.agent_id}`, {
      method: 'PUT',
      headers: {
        Authorization: `Bearer ${authStore.token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    })
    if (!response.ok) throw new Error(`Failed to update agent: ${response.status}`)
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
      <h1>Agent Management</h1>
      <p class="subtitle">Configure LLM settings for each agent</p>
    </header>

    <div v-if="error" class="error-banner">
      {{ error }}
      <button @click="error = null">Dismiss</button>
    </div>

    <div class="agents-stats">
      <div class="stat-card">
        <span class="stat-value">{{ agents.length }}</span>
        <span class="stat-label">Total Agents</span>
      </div>
      <div class="stat-card">
        <span class="stat-value">{{ activeAgentCount }}</span>
        <span class="stat-label">Active</span>
      </div>
      <div class="stat-card">
        <span class="stat-value">{{ agents.length - activeAgentCount }}</span>
        <span class="stat-label">Inactive</span>
      </div>
    </div>

    <div class="agents-container">
      <!-- Agent list -->
      <div class="agents-list">
        <h2>Agents</h2>
        <div v-if="loading" class="loading">Loading agents...</div>
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
            <span v-if="agent.is_default" class="default-badge">Default</span>
          </li>
        </ul>
      </div>

      <!-- Agent detail -->
      <div v-if="selectedAgent" class="agent-detail">
        <div class="detail-header">
          <h2>{{ selectedAgent.name }}</h2>
          <div class="actions">
            <button v-if="!isEditing" class="btn-edit" @click="startEditing">Edit</button>
            <template v-else>
              <button class="btn-save" @click="saveAgent">Save</button>
              <button class="btn-cancel" @click="cancelEditing">Cancel</button>
            </template>
          </div>
        </div>

        <p class="description">{{ selectedAgent.description }}</p>

        <div class="config-form">
          <!-- Agent ID (always read-only) -->
          <div class="form-group">
            <label>Agent ID</label>
            <input type="text" :value="selectedAgent.agent_id" disabled />
          </div>

          <!-- LLM Provider -->
          <div class="form-group">
            <label>LLM Provider</label>
            <select v-model="editForm.llm_provider" :disabled="!isEditing">
              <option v-for="p in providers" :key="p" :value="p">{{ p }}</option>
            </select>
          </div>

          <!-- LLM Model -->
          <div class="form-group">
            <label>LLM Model</label>
            <input v-model="editForm.llm_model" :disabled="!isEditing" />
          </div>

          <!-- LLM Endpoint — node selector or custom -->
          <div class="form-group endpoint-group">
            <label>LLM Endpoint</label>

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
                <optgroup label="Fleet Nodes">
                  <option
                    v-for="node in nodes"
                    :key="node.node_id"
                    :value="node.node_id"
                  >
                    {{ node.node_id }} — {{ node.ip_address }}:{{ OLLAMA_PORT }}
                  </option>
                </optgroup>
                <option :value="CUSTOM_VALUE">Custom…</option>
              </select>

              <input
                v-if="isCustomEndpoint"
                v-model="editForm.llm_endpoint"
                class="custom-endpoint-input"
                placeholder="http://host:11434"
              />

              <span v-else class="endpoint-hint">
                → {{ editForm.llm_endpoint }}
              </span>
            </template>
          </div>

          <!-- Timeout -->
          <div class="form-group">
            <label>Timeout (seconds)</label>
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
            <label>Temperature</label>
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
              />
              Active
            </label>
          </div>
        </div>
      </div>

      <div v-else class="agent-detail empty">
        <p>Select an agent to view and edit its configuration</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.agents-view {
  padding: 24px;
  max-width: 1400px;
  margin: 0 auto;
}

.view-header {
  margin-bottom: 24px;
}

.view-header h1 {
  font-size: 28px;
  font-weight: 600;
  color: var(--text-primary, #1a1a2e);
  margin: 0;
}

.subtitle {
  color: var(--text-secondary, #6b7280);
  margin-top: 4px;
}

.error-banner {
  background: #fee2e2;
  border: 1px solid #ef4444;
  color: #b91c1c;
  padding: 12px 16px;
  border-radius: 8px;
  margin-bottom: 16px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.agents-stats {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  margin-bottom: 24px;
}

.stat-card {
  background: white;
  padding: 20px;
  border-radius: 12px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  text-align: center;
}

.stat-value {
  display: block;
  font-size: 32px;
  font-weight: 700;
  color: var(--primary, #6366f1);
}

.stat-label {
  color: var(--text-secondary, #6b7280);
  font-size: 14px;
}

.agents-container {
  display: grid;
  grid-template-columns: 350px 1fr;
  gap: 24px;
}

.agents-list {
  background: white;
  border-radius: 12px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  padding: 16px;
}

.agents-list h2 {
  font-size: 18px;
  font-weight: 600;
  margin: 0 0 16px 0;
  padding-bottom: 12px;
  border-bottom: 1px solid #e5e7eb;
}

.agents-list ul {
  list-style: none;
  padding: 0;
  margin: 0;
  max-height: 600px;
  overflow-y: auto;
}

.agents-list li {
  padding: 12px;
  border-radius: 8px;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 4px;
}

.agents-list li:hover {
  background: #f3f4f6;
}

.agents-list li.selected {
  background: #e0e7ff;
}

.agents-list li.inactive {
  opacity: 0.6;
}

.agent-name {
  font-weight: 500;
  color: var(--text-primary, #1a1a2e);
}

.agent-model {
  font-size: 12px;
  color: var(--text-secondary, #6b7280);
}

.default-badge {
  font-size: 10px;
  background: #6366f1;
  color: white;
  padding: 2px 8px;
  border-radius: 4px;
  align-self: flex-start;
}

.agent-detail {
  background: white;
  border-radius: 12px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  padding: 24px;
}

.agent-detail.empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 400px;
  color: var(--text-secondary, #6b7280);
}

.detail-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.detail-header h2 {
  font-size: 20px;
  font-weight: 600;
  margin: 0;
}

.description {
  color: var(--text-secondary, #6b7280);
  margin-bottom: 24px;
  font-size: 14px;
}

.config-form {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
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
  color: var(--text-secondary, #6b7280);
}

.form-group input,
.form-group select {
  padding: 10px 12px;
  border: 1px solid #d1d5db;
  border-radius: 8px;
  font-size: 14px;
}

.form-group input:disabled,
.form-group select:disabled {
  background: #f9fafb;
  color: var(--text-secondary, #6b7280);
}

.node-select {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid #d1d5db;
  border-radius: 8px;
  font-size: 14px;
  background: white;
  cursor: pointer;
}

.custom-endpoint-input {
  margin-top: 8px;
  width: 100%;
  padding: 10px 12px;
  border: 1px solid #6366f1;
  border-radius: 8px;
  font-size: 14px;
  font-family: monospace;
  box-sizing: border-box;
}

.endpoint-hint {
  display: block;
  margin-top: 6px;
  font-size: 13px;
  font-family: monospace;
  color: var(--text-secondary, #6b7280);
}

.endpoint-readonly {
  padding: 10px 12px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  font-size: 14px;
  background: #f9fafb;
  color: var(--text-secondary, #6b7280);
  font-family: monospace;
}

.checkbox-label {
  flex-direction: row !important;
  align-items: center;
  gap: 8px !important;
}

.checkbox-label input {
  width: auto;
}

.actions {
  display: flex;
  gap: 8px;
}

.btn-edit,
.btn-save,
.btn-cancel {
  padding: 8px 16px;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  border: none;
}

.btn-edit {
  background: #6366f1;
  color: white;
}

.btn-save {
  background: #10b981;
  color: white;
}

.btn-cancel {
  background: #e5e7eb;
  color: #374151;
}

.loading {
  text-align: center;
  color: var(--text-secondary, #6b7280);
  padding: 40px;
}
</style>
