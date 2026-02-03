<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Agent Management View (Issue #760 Phase 4)
 *
 * Provides UI for viewing and managing agent LLM configurations.
 */

import { ref, onMounted, computed } from 'vue'
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

const authStore = useAuthStore()
const agents = ref<Agent[]>([])
const loading = ref(true)
const error = ref<string | null>(null)
const selectedAgent = ref<Agent | null>(null)
const isEditing = ref(false)

// Edit form state
const editForm = ref({
  llm_provider: '',
  llm_model: '',
  llm_endpoint: '',
  llm_timeout: 30,
  llm_temperature: 0.7,
  is_active: true
})

const providers = ['ollama', 'openai', 'anthropic']

async function fetchAgents() {
  loading.value = true
  error.value = null

  try {
    // Use relative path - SLM Admin is hosted by SLM server
    const response = await fetch('/api/agents', {
      headers: {
        'Authorization': `Bearer ${authStore.token}`,
        'Content-Type': 'application/json'
      }
    })

    if (!response.ok) {
      throw new Error(`Failed to fetch agents: ${response.status}`)
    }

    agents.value = await response.json()
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Failed to fetch agents'
  } finally {
    loading.value = false
  }
}

function selectAgent(agent: Agent) {
  selectedAgent.value = agent
  editForm.value = {
    llm_provider: agent.llm_provider,
    llm_model: agent.llm_model,
    llm_endpoint: agent.llm_endpoint,
    llm_timeout: agent.llm_timeout,
    llm_temperature: agent.llm_temperature,
    is_active: agent.is_active
  }
  isEditing.value = false
}

function startEditing() {
  isEditing.value = true
}

function cancelEditing() {
  if (selectedAgent.value) {
    editForm.value = {
      llm_provider: selectedAgent.value.llm_provider,
      llm_model: selectedAgent.value.llm_model,
      llm_endpoint: selectedAgent.value.llm_endpoint,
      llm_timeout: selectedAgent.value.llm_timeout,
      llm_temperature: selectedAgent.value.llm_temperature,
      is_active: selectedAgent.value.is_active
    }
  }
  isEditing.value = false
}

async function saveAgent() {
  if (!selectedAgent.value) return

  try {
    // Use relative path - SLM Admin is hosted by SLM server
    const response = await fetch(
      `/api/agents/${selectedAgent.value.agent_id}`,
      {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${authStore.token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(editForm.value)
      }
    )

    if (!response.ok) {
      throw new Error(`Failed to update agent: ${response.status}`)
    }

    // Refresh agent list
    await fetchAgents()

    // Re-select updated agent
    const updated = agents.value.find(a => a.agent_id === selectedAgent.value?.agent_id)
    if (updated) {
      selectAgent(updated)
    }

    isEditing.value = false
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Failed to save agent'
  }
}

const activeAgentCount = computed(() => agents.value.filter(a => a.is_active).length)

onMounted(() => {
  fetchAgents()
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
      <div class="agents-list">
        <h2>Agents</h2>
        <div v-if="loading" class="loading">Loading agents...</div>
        <ul v-else>
          <li
            v-for="agent in agents"
            :key="agent.agent_id"
            :class="{ selected: selectedAgent?.agent_id === agent.agent_id, inactive: !agent.is_active }"
            @click="selectAgent(agent)"
          >
            <span class="agent-name">{{ agent.name }}</span>
            <span class="agent-model">{{ agent.llm_model }}</span>
            <span v-if="agent.is_default" class="default-badge">Default</span>
          </li>
        </ul>
      </div>

      <div class="agent-detail" v-if="selectedAgent">
        <div class="detail-header">
          <h2>{{ selectedAgent.name }}</h2>
          <div class="actions">
            <button v-if="!isEditing" @click="startEditing" class="btn-edit">Edit</button>
            <template v-else>
              <button @click="saveAgent" class="btn-save">Save</button>
              <button @click="cancelEditing" class="btn-cancel">Cancel</button>
            </template>
          </div>
        </div>

        <p class="description">{{ selectedAgent.description }}</p>

        <div class="config-form">
          <div class="form-group">
            <label>Agent ID</label>
            <input type="text" :value="selectedAgent.agent_id" disabled />
          </div>

          <div class="form-group">
            <label>LLM Provider</label>
            <select v-model="editForm.llm_provider" :disabled="!isEditing">
              <option v-for="p in providers" :key="p" :value="p">{{ p }}</option>
            </select>
          </div>

          <div class="form-group">
            <label>LLM Model</label>
            <input v-model="editForm.llm_model" :disabled="!isEditing" />
          </div>

          <div class="form-group">
            <label>LLM Endpoint</label>
            <input v-model="editForm.llm_endpoint" :disabled="!isEditing" />
          </div>

          <div class="form-group">
            <label>Timeout (seconds)</label>
            <input
              type="number"
              v-model.number="editForm.llm_timeout"
              :disabled="!isEditing"
              min="1"
              max="300"
            />
          </div>

          <div class="form-group">
            <label>Temperature</label>
            <input
              type="number"
              v-model.number="editForm.llm_temperature"
              :disabled="!isEditing"
              min="0"
              max="2"
              step="0.1"
            />
          </div>

          <div class="form-group">
            <label class="checkbox-label">
              <input
                type="checkbox"
                v-model="editForm.is_active"
                :disabled="!isEditing"
              />
              Active
            </label>
          </div>
        </div>
      </div>

      <div class="agent-detail empty" v-else>
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
