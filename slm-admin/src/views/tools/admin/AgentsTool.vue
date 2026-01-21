// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

<script setup lang="ts">
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('AgentsTool')
/**
 * AgentsTool - Agent Registry Manager
 *
 * Manage and monitor AutoBot's AI agent system.
 * Migrated from main AutoBot frontend - Issue #729.
 */

import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useAutobotApi } from '@/composables/useAutobotApi'

const api = useAutobotApi()

// State
const loading = ref(false)
const error = ref<string | null>(null)

interface Agent {
  id: string
  name: string
  type: string
  status: 'active' | 'idle' | 'error' | 'stopped'
  description: string
  capabilities: string[]
  last_activity: string
  tasks_completed: number
  success_rate: number
}

interface AgentStats {
  total_agents: number
  active_agents: number
  total_tasks: number
  avg_success_rate: number
}

const agents = ref<Agent[]>([])
const stats = ref<AgentStats>({ total_agents: 0, active_agents: 0, total_tasks: 0, avg_success_rate: 0 })
const selectedAgent = ref<Agent | null>(null)
const filterStatus = ref<string>('all')
const searchQuery = ref('')

let refreshInterval: ReturnType<typeof setInterval> | null = null

// Computed
const filteredAgents = computed(() => {
  let result = agents.value

  if (filterStatus.value !== 'all') {
    result = result.filter(a => a.status === filterStatus.value)
  }

  if (searchQuery.value) {
    const query = searchQuery.value.toLowerCase()
    result = result.filter(a =>
      a.name.toLowerCase().includes(query) ||
      a.type.toLowerCase().includes(query) ||
      a.description.toLowerCase().includes(query)
    )
  }

  return result
})

// Methods
function getStatusClass(status: string): string {
  switch (status) {
    case 'active': return 'bg-green-100 text-green-800'
    case 'idle': return 'bg-blue-100 text-blue-800'
    case 'error': return 'bg-red-100 text-red-800'
    case 'stopped': return 'bg-gray-100 text-gray-800'
    default: return 'bg-gray-100 text-gray-800'
  }
}

function getStatusDot(status: string): string {
  switch (status) {
    case 'active': return 'bg-green-500'
    case 'idle': return 'bg-blue-500'
    case 'error': return 'bg-red-500'
    case 'stopped': return 'bg-gray-500'
    default: return 'bg-gray-500'
  }
}

function formatDate(dateStr: string): string {
  const date = new Date(dateStr)
  return date.toLocaleString()
}

async function loadAgents(): Promise<void> {
  loading.value = true
  error.value = null

  try {
    const data = await api.get('/agents')
    agents.value = data.agents || []
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to load agents'
  } finally {
    loading.value = false
  }
}

async function loadStats(): Promise<void> {
  try {
    const data = await api.get('/agents/stats')
    stats.value = data || { total_agents: 0, active_agents: 0, total_tasks: 0, avg_success_rate: 0 }
  } catch (e) {
    logger.error('Failed to load stats:', e)
  }
}

async function refreshData(): Promise<void> {
  await Promise.all([loadAgents(), loadStats()])
}

async function startAgent(agentId: string): Promise<void> {
  try {
    await api.post(`/agents/${agentId}/start`)
    await loadAgents()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to start agent'
  }
}

async function stopAgent(agentId: string): Promise<void> {
  try {
    await api.post(`/agents/${agentId}/stop`)
    await loadAgents()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to stop agent'
  }
}

async function restartAgent(agentId: string): Promise<void> {
  try {
    await api.post(`/agents/${agentId}/restart`)
    await loadAgents()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to restart agent'
  }
}

function selectAgent(agent: Agent): void {
  selectedAgent.value = selectedAgent.value?.id === agent.id ? null : agent
}

onMounted(() => {
  refreshData()
  refreshInterval = setInterval(() => refreshData(), 30000)
})

onUnmounted(() => {
  if (refreshInterval) {
    clearInterval(refreshInterval)
  }
})
</script>

<template>
  <div class="p-6">
    <!-- Stats Cards -->
    <div class="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
      <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-sm text-gray-500">Total Agents</p>
            <p class="text-2xl font-bold text-gray-900">{{ stats.total_agents }}</p>
          </div>
          <div class="p-3 bg-blue-100 rounded-lg">
            <svg class="w-6 h-6 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
            </svg>
          </div>
        </div>
      </div>

      <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-sm text-gray-500">Active Agents</p>
            <p class="text-2xl font-bold text-green-600">{{ stats.active_agents }}</p>
          </div>
          <div class="p-3 bg-green-100 rounded-lg">
            <svg class="w-6 h-6 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
        </div>
      </div>

      <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-sm text-gray-500">Tasks Completed</p>
            <p class="text-2xl font-bold text-gray-900">{{ stats.total_tasks }}</p>
          </div>
          <div class="p-3 bg-purple-100 rounded-lg">
            <svg class="w-6 h-6 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
            </svg>
          </div>
        </div>
      </div>

      <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-sm text-gray-500">Success Rate</p>
            <p class="text-2xl font-bold text-gray-900">{{ (stats.avg_success_rate * 100).toFixed(1) }}%</p>
          </div>
          <div class="p-3 bg-amber-100 rounded-lg">
            <svg class="w-6 h-6 text-amber-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
            </svg>
          </div>
        </div>
      </div>
    </div>

    <!-- Filters -->
    <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4 mb-6">
      <div class="flex items-center gap-4">
        <div class="flex-1">
          <input
            v-model="searchQuery"
            type="text"
            placeholder="Search agents..."
            class="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
          />
        </div>
        <select
          v-model="filterStatus"
          class="px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
        >
          <option value="all">All Status</option>
          <option value="active">Active</option>
          <option value="idle">Idle</option>
          <option value="error">Error</option>
          <option value="stopped">Stopped</option>
        </select>
        <button
          @click="refreshData"
          :disabled="loading"
          class="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors disabled:opacity-50 flex items-center gap-2"
        >
          <svg class="w-4 h-4" :class="{ 'animate-spin': loading }" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          Refresh
        </button>
      </div>
    </div>

    <!-- Error Message -->
    <div v-if="error" class="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700">
      {{ error }}
    </div>

    <!-- Agents Grid -->
    <div v-if="loading && !agents.length" class="text-center py-12">
      <svg class="animate-spin w-8 h-8 mx-auto text-primary-500" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
      </svg>
      <p class="mt-4 text-gray-600">Loading agents...</p>
    </div>

    <div v-else-if="filteredAgents.length === 0" class="text-center py-12">
      <svg class="w-12 h-12 mx-auto text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
      </svg>
      <p class="mt-4 text-gray-600">No agents found</p>
    </div>

    <div v-else class="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <div
        v-for="agent in filteredAgents"
        :key="agent.id"
        @click="selectAgent(agent)"
        :class="[
          'bg-white rounded-lg shadow-sm border border-gray-200 p-6 cursor-pointer transition-all',
          selectedAgent?.id === agent.id ? 'ring-2 ring-primary-500' : 'hover:shadow-md'
        ]"
      >
        <!-- Agent Header -->
        <div class="flex items-start justify-between mb-4">
          <div class="flex items-center gap-3">
            <div class="relative">
              <div class="w-10 h-10 bg-primary-100 rounded-lg flex items-center justify-center">
                <svg class="w-6 h-6 text-primary-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                </svg>
              </div>
              <div :class="['absolute -bottom-1 -right-1 w-3 h-3 rounded-full border-2 border-white', getStatusDot(agent.status)]"></div>
            </div>
            <div>
              <h3 class="font-semibold text-gray-900">{{ agent.name }}</h3>
              <p class="text-sm text-gray-500">{{ agent.type }}</p>
            </div>
          </div>
          <span :class="['px-2 py-1 text-xs font-medium rounded-full', getStatusClass(agent.status)]">
            {{ agent.status }}
          </span>
        </div>

        <!-- Description -->
        <p class="text-sm text-gray-600 mb-4">{{ agent.description }}</p>

        <!-- Stats -->
        <div class="grid grid-cols-2 gap-4 mb-4">
          <div>
            <p class="text-xs text-gray-500">Tasks Completed</p>
            <p class="text-lg font-bold text-gray-900">{{ agent.tasks_completed }}</p>
          </div>
          <div>
            <p class="text-xs text-gray-500">Success Rate</p>
            <p class="text-lg font-bold text-gray-900">{{ (agent.success_rate * 100).toFixed(0) }}%</p>
          </div>
        </div>

        <!-- Capabilities -->
        <div class="mb-4">
          <p class="text-xs text-gray-500 mb-2">Capabilities</p>
          <div class="flex flex-wrap gap-1">
            <span
              v-for="cap in agent.capabilities"
              :key="cap"
              class="px-2 py-1 text-xs bg-gray-100 text-gray-700 rounded"
            >
              {{ cap }}
            </span>
          </div>
        </div>

        <!-- Last Activity -->
        <div class="flex items-center justify-between text-xs text-gray-500 pt-4 border-t border-gray-200">
          <span>Last activity: {{ formatDate(agent.last_activity) }}</span>
        </div>

        <!-- Actions -->
        <div v-if="selectedAgent?.id === agent.id" class="flex gap-2 mt-4 pt-4 border-t border-gray-200">
          <button
            v-if="agent.status === 'stopped'"
            @click.stop="startAgent(agent.id)"
            class="px-3 py-1.5 text-xs bg-green-600 text-white rounded-lg hover:bg-green-700"
          >
            Start
          </button>
          <button
            v-if="agent.status === 'active' || agent.status === 'idle'"
            @click.stop="stopAgent(agent.id)"
            class="px-3 py-1.5 text-xs bg-red-600 text-white rounded-lg hover:bg-red-700"
          >
            Stop
          </button>
          <button
            @click.stop="restartAgent(agent.id)"
            class="px-3 py-1.5 text-xs bg-amber-600 text-white rounded-lg hover:bg-amber-700"
          >
            Restart
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
