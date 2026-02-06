// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

<script setup lang="ts">
/**
 * FleetToolsTab - Fleet tools as a tab component
 *
 * Provides diagnostic and management tools for fleet operations.
 * Extracted from ToolsView for use as a tab in Fleet Overview.
 *
 * Related to Issue #729.
 * Refactored in Issue #737 Phase 2: Removed duplicate tools (Network Test,
 * Health Check, Service Manager) that overlap with NodeCard/Panel functionality.
 */

import { ref, computed } from 'vue'
import { useFleetStore } from '@/stores/fleet'
import { useAuthStore } from '@/stores/auth'
import { useNodeServices } from '@/composables/useNodeServices'

const fleetStore = useFleetStore()
const authStore = useAuthStore()

// Tool definitions - reduced to 3 unique tools per Issue #737
// Removed: network-test (use NodeCard "Test"), health-check (use NodeLifecyclePanel),
//          service-restart (use NodeServicesPanel)
const tools = [
  {
    id: 'log-viewer',
    name: 'Service Logs',
    description: 'View service logs from nodes via journalctl',
    icon: 'document',
    available: true,
  },
  {
    id: 'redis-cli',
    name: 'Redis CLI',
    description: 'Execute Redis commands on the cluster',
    icon: 'database',
    available: true,
  },
  {
    id: 'ansible-runner',
    name: 'Command Runner',
    description: 'Run shell commands on nodes',
    icon: 'terminal',
    available: true,
  },
]

const activeTool = ref<string | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)
const result = ref<string | null>(null)

// Tool-specific state
const selectedNode = ref<string>('')
const selectedService = ref<string>('')
const redisCommand = ref<string>('PING')
const shellCommand = ref<string>('uptime')
const logLines = ref<number>(100)

// Node services composable for log viewer (Issue #737)
const nodeServices = useNodeServices(selectedNode)

// Available nodes for selection
const nodes = computed(() => fleetStore.nodeList)

// Selected node details
const selectedNodeDetails = computed(() => {
  if (!selectedNode.value) return null
  return nodes.value.find(n => n.node_id === selectedNode.value) || null
})

function selectTool(toolId: string): void {
  activeTool.value = toolId
  error.value = null
  result.value = null
}

function closeTool(): void {
  activeTool.value = null
  error.value = null
  result.value = null
}

// Log viewer using useNodeServices composable (Issue #737)
async function getServiceLogs(): Promise<void> {
  if (!selectedNode.value || !selectedService.value) {
    error.value = 'Please select a node and service'
    return
  }

  loading.value = true
  error.value = null
  result.value = null

  try {
    const logs = await nodeServices.getLogs(selectedService.value, logLines.value)
    result.value = logs || 'No logs available'
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to fetch logs'
  } finally {
    loading.value = false
  }
}

async function runRedisCommand(): Promise<void> {
  if (!redisCommand.value.trim()) {
    error.value = 'Please enter a Redis command'
    return
  }

  loading.value = true
  error.value = null
  result.value = null

  try {
    // Use the Redis node if available, otherwise use first available node
    const redisNode = nodes.value.find(n => n.roles?.includes('redis'))
    const targetNode = redisNode || (selectedNode.value ? selectedNodeDetails.value : null)

    if (!targetNode) {
      throw new Error('No node selected and no Redis node found')
    }

    // Execute via SSH
    const response = await fetch(`/api/nodes/${targetNode.node_id}/execute`, {
      method: 'POST',
      headers: {
        ...authStore.getAuthHeaders(),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        command: `redis-cli ${redisCommand.value}`,
      }),
    })

    if (!response.ok) {
      const err = await response.json()
      throw new Error(err.detail || 'Redis command failed')
    }

    const data = await response.json()
    result.value = `Redis Response:\n\n${data.output || data.stdout || 'No output'}`
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Redis command failed'
  } finally {
    loading.value = false
  }
}

async function runShellCommand(): Promise<void> {
  if (!selectedNode.value || !shellCommand.value.trim()) {
    error.value = 'Please select a node and enter a command'
    return
  }

  loading.value = true
  error.value = null
  result.value = null

  try {
    const response = await fetch(`/api/nodes/${selectedNode.value}/execute`, {
      method: 'POST',
      headers: {
        ...authStore.getAuthHeaders(),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        command: shellCommand.value,
      }),
    })

    if (!response.ok) {
      const err = await response.json()
      throw new Error(err.detail || 'Command execution failed')
    }

    const data = await response.json()
    result.value = `Command Output:\n\n${data.output || data.stdout || 'No output'}\n\n` +
      (data.stderr ? `Stderr:\n${data.stderr}` : '')
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Command execution failed'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div>
    <!-- Info Banner -->
    <div class="mb-6 flex items-center gap-2 text-sm text-gray-600 bg-white rounded-lg p-3 border border-gray-200">
      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2" />
      </svg>
      <span>{{ nodes.length }} nodes available for fleet operations</span>
    </div>

    <!-- Tools Grid -->
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-6">
      <button
        v-for="tool in tools"
        :key="tool.id"
        @click="selectTool(tool.id)"
        :disabled="!tool.available"
        :class="[
          'bg-white rounded-lg shadow-sm border border-gray-200 p-6 text-left transition-all',
          tool.available
            ? 'hover:shadow-md hover:border-primary-300 cursor-pointer'
            : 'opacity-50 cursor-not-allowed',
          activeTool === tool.id ? 'ring-2 ring-primary-500 border-primary-500' : ''
        ]"
      >
        <div class="flex items-start gap-4">
          <div class="p-3 bg-primary-100 rounded-lg">
            <!-- Document icon (log-viewer) -->
            <svg v-if="tool.icon === 'document'" class="w-6 h-6 text-primary-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            <!-- Database icon (redis-cli) -->
            <svg v-else-if="tool.icon === 'database'" class="w-6 h-6 text-primary-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" />
            </svg>
            <!-- Terminal icon (ansible-runner) -->
            <svg v-else-if="tool.icon === 'terminal'" class="w-6 h-6 text-primary-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
            </svg>
          </div>
          <div>
            <h3 class="font-medium text-gray-900">{{ tool.name }}</h3>
            <p class="text-sm text-gray-500 mt-1">{{ tool.description }}</p>
          </div>
        </div>
      </button>
    </div>

    <!-- Tool Interface Panel -->
    <div v-if="activeTool" class="bg-white rounded-lg shadow-sm border border-gray-200">
      <!-- Panel Header -->
      <div class="flex items-center justify-between px-6 py-4 border-b border-gray-200">
        <h2 class="text-lg font-semibold text-gray-900">
          {{ tools.find(t => t.id === activeTool)?.name }}
        </h2>
        <button
          @click="closeTool"
          class="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
        >
          <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      <!-- Panel Content -->
      <div class="p-6">
        <!-- Log Viewer Tool -->
        <div v-if="activeTool === 'log-viewer'" class="space-y-4">
          <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-2">Select Node</label>
              <select
                v-model="selectedNode"
                class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
              >
                <option value="">-- Select a node --</option>
                <option v-for="node in nodes" :key="node.node_id" :value="node.node_id">
                  {{ node.hostname }} ({{ node.ip_address }})
                </option>
              </select>
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-2">Service Name</label>
              <input
                type="text"
                v-model="selectedService"
                placeholder="e.g., autobot-agent"
                class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
              />
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-2">Lines</label>
              <select
                v-model="logLines"
                class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
              >
                <option :value="50">50 lines</option>
                <option :value="100">100 lines</option>
                <option :value="200">200 lines</option>
                <option :value="500">500 lines</option>
              </select>
            </div>
          </div>
          <button
            @click="getServiceLogs"
            :disabled="loading || !selectedNode || !selectedService"
            class="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors disabled:opacity-50 flex items-center gap-2"
          >
            <svg v-if="loading" class="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            {{ loading ? 'Fetching...' : 'Get Logs' }}
          </button>
        </div>

        <!-- Redis CLI Tool -->
        <div v-else-if="activeTool === 'redis-cli'" class="space-y-4">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-2">Redis Command</label>
            <input
              type="text"
              v-model="redisCommand"
              placeholder="e.g., PING, INFO, KEYS *"
              class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 font-mono"
            />
          </div>
          <p class="text-xs text-gray-500">
            Command will be executed on the Redis node. Common commands: PING, INFO, DBSIZE, CLIENT LIST
          </p>
          <button
            @click="runRedisCommand"
            :disabled="loading || !redisCommand"
            class="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors disabled:opacity-50 flex items-center gap-2"
          >
            <svg v-if="loading" class="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            {{ loading ? 'Executing...' : 'Execute' }}
          </button>
        </div>

        <!-- Command Runner Tool -->
        <div v-else-if="activeTool === 'ansible-runner'" class="space-y-4">
          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-2">Select Node</label>
              <select
                v-model="selectedNode"
                class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
              >
                <option value="">-- Select a node --</option>
                <option v-for="node in nodes" :key="node.node_id" :value="node.node_id">
                  {{ node.hostname }} ({{ node.ip_address }})
                </option>
              </select>
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-2">Command</label>
              <input
                type="text"
                v-model="shellCommand"
                placeholder="e.g., uptime, df -h, free -m"
                class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 font-mono"
              />
            </div>
          </div>
          <p class="text-xs text-gray-500">
            Run shell commands on the selected node via SSH. Be careful with destructive commands.
          </p>
          <button
            @click="runShellCommand"
            :disabled="loading || !selectedNode || !shellCommand"
            class="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors disabled:opacity-50 flex items-center gap-2"
          >
            <svg v-if="loading" class="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            {{ loading ? 'Running...' : 'Run Command' }}
          </button>
        </div>

        <!-- Error Message -->
        <div v-if="error" class="mt-4 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700">
          {{ error }}
        </div>

        <!-- Result Output -->
        <div v-if="result" class="mt-4">
          <label class="block text-sm font-medium text-gray-700 mb-2">Output</label>
          <pre class="p-4 bg-gray-900 text-gray-100 rounded-lg overflow-auto max-h-96 text-sm font-mono whitespace-pre-wrap">{{ result }}</pre>
        </div>
      </div>
    </div>
  </div>
</template>
