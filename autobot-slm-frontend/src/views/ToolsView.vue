<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * ToolsView - Infrastructure management tools
 *
 * Provides diagnostic and management tools for fleet operations.
 * Integrated into SLM as per Issue #729.
 *
 * Issue #754: Added aria-hidden on decorative icons, aria-label on
 * tool buttons, for/id on form labels, role="alert" on errors,
 * role="region" on output, aria-label on close button,
 * accessible labels on action buttons.
 */

import { ref, computed, onMounted } from 'vue'
import { useFleetStore } from '@/stores/fleet'
import { useAuthStore } from '@/stores/auth'

const fleetStore = useFleetStore()
const authStore = useAuthStore()

// Tool definitions - all tools integrated into SLM (Issue #729)
const tools = [
  {
    id: 'network-test',
    name: 'Network Connectivity Test',
    description: 'Test SSH and network connectivity to nodes',
    icon: 'network',
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
    id: 'service-restart',
    name: 'Service Manager',
    description: 'Start, stop, or restart services on nodes',
    icon: 'refresh',
    available: true,
  },
  {
    id: 'log-viewer',
    name: 'Service Logs',
    description: 'View service logs from nodes via journalctl',
    icon: 'document',
    available: true,
  },
  {
    id: 'health-check',
    name: 'Deep Health Check',
    description: 'Run comprehensive health diagnostics',
    icon: 'heart',
    available: true,
  },
  {
    id: 'ansible-runner',
    name: 'Ansible Ad-Hoc',
    description: 'Run ad-hoc Ansible commands on nodes',
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
const ansibleCommand = ref<string>('uptime')
const logLines = ref<number>(100)

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

async function runNetworkTest(): Promise<void> {
  if (!selectedNode.value) {
    error.value = 'Please select a node'
    return
  }

  loading.value = true
  error.value = null
  result.value = null

  try {
    const response = await fetch(`/api/nodes/test-connection`, {
      method: 'POST',
      headers: {
        ...authStore.getAuthHeaders(),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        ip_address: selectedNodeDetails.value?.ip_address,
        ssh_user: selectedNodeDetails.value?.ssh_user || 'autobot',
        ssh_port: selectedNodeDetails.value?.ssh_port || 22,
        auth_method: selectedNodeDetails.value?.auth_method || 'key',
      }),
    })

    if (!response.ok) {
      const err = await response.json()
      throw new Error(err.detail || 'Connection test failed')
    }

    const data = await response.json()
    result.value = data.success
      ? `Connection successful!\n\nHost: ${data.hostname || 'unknown'}\nOS: ${data.os_info || 'unknown'}\nLatency: ${data.latency_ms || 'N/A'}ms`
      : `Connection failed: ${data.error || 'Unknown error'}`
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Test failed'
  } finally {
    loading.value = false
  }
}

async function runHealthCheck(): Promise<void> {
  if (!selectedNode.value) {
    error.value = 'Please select a node'
    return
  }

  loading.value = true
  error.value = null
  result.value = null

  try {
    const response = await fetch(`/api/nodes/${selectedNode.value}/health`, {
      headers: authStore.getAuthHeaders(),
    })

    if (!response.ok) {
      throw new Error('Health check failed')
    }

    const data = await response.json()
    result.value = `Health Check Results:\n\n` +
      `Status: ${data.status || 'unknown'}\n` +
      `CPU: ${data.cpu_percent?.toFixed(1) || 'N/A'}%\n` +
      `Memory: ${data.memory_percent?.toFixed(1) || 'N/A'}%\n` +
      `Disk: ${data.disk_percent?.toFixed(1) || 'N/A'}%\n` +
      `Last Heartbeat: ${data.last_heartbeat || 'N/A'}\n\n` +
      `Services:\n${(data.services || []).map((s: any) => `  - ${s.name}: ${s.status}`).join('\n') || '  No services found'}`
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Health check failed'
  } finally {
    loading.value = false
  }
}

async function getServiceLogs(): Promise<void> {
  if (!selectedNode.value || !selectedService.value) {
    error.value = 'Please select a node and service'
    return
  }

  loading.value = true
  error.value = null
  result.value = null

  try {
    const response = await fetch(
      `/api/nodes/${selectedNode.value}/services/${selectedService.value}/logs?lines=${logLines.value}`,
      { headers: authStore.getAuthHeaders() }
    )

    if (!response.ok) {
      const err = await response.json()
      throw new Error(err.detail || 'Failed to fetch logs')
    }

    const data = await response.json()
    result.value = data.logs || 'No logs available'
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to fetch logs'
  } finally {
    loading.value = false
  }
}

async function serviceAction(action: 'start' | 'stop' | 'restart'): Promise<void> {
  if (!selectedNode.value || !selectedService.value) {
    error.value = 'Please select a node and service'
    return
  }

  loading.value = true
  error.value = null
  result.value = null

  try {
    const response = await fetch(
      `/api/nodes/${selectedNode.value}/services/${selectedService.value}/${action}`,
      {
        method: 'POST',
        headers: authStore.getAuthHeaders(),
      }
    )

    if (!response.ok) {
      const err = await response.json()
      throw new Error(err.detail || `Failed to ${action} service`)
    }

    const data = await response.json()
    result.value = data.success
      ? `Service ${action} successful!\n\n${data.message || ''}`
      : `Service ${action} failed: ${data.message || 'Unknown error'}`
  } catch (e) {
    error.value = e instanceof Error ? e.message : `Failed to ${action} service`
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

    // Execute via ansible ad-hoc
    const response = await fetch(`/api/nodes/${targetNode.node_id}/exec`, {
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

async function runAnsibleCommand(): Promise<void> {
  if (!selectedNode.value || !ansibleCommand.value.trim()) {
    error.value = 'Please select a node and enter a command'
    return
  }

  loading.value = true
  error.value = null
  result.value = null

  try {
    const response = await fetch(`/api/nodes/${selectedNode.value}/exec`, {
      method: 'POST',
      headers: {
        ...authStore.getAuthHeaders(),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        command: ansibleCommand.value,
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

// Load nodes on mount
onMounted(async () => {
  await fleetStore.fetchNodes()
})
</script>

<template>
  <div class="h-full flex flex-col overflow-hidden">
    <!-- Content (no header - parent ToolsLayout provides it) -->
    <div class="flex-1 overflow-auto p-6">
      <!-- Info Banner -->
      <div class="mb-6 flex items-center gap-2 text-sm text-gray-600 bg-white rounded-lg p-3 border border-gray-200" role="status">
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2" />
        </svg>
        <span>{{ nodes.length }} nodes available for fleet operations</span>
      </div>
      <!-- Tools Grid -->
      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-6" role="group" aria-label="Available tools">
        <button
          v-for="tool in tools"
          :key="tool.id"
          @click="selectTool(tool.id)"
          :disabled="!tool.available"
          :aria-label="`${tool.name}: ${tool.description}`"
          :aria-pressed="activeTool === tool.id"
          :class="[
            'bg-white rounded-lg shadow-sm border border-gray-200 p-6 text-left transition-all',
            tool.available
              ? 'hover:shadow-md hover:border-primary-300 cursor-pointer'
              : 'opacity-50 cursor-not-allowed',
            activeTool === tool.id ? 'ring-2 ring-primary-500 border-primary-500' : ''
          ]"
        >
          <div class="flex items-start gap-4">
            <div class="p-3 bg-primary-100 rounded-lg" aria-hidden="true">
              <!-- Network icon -->
              <svg v-if="tool.icon === 'network'" class="w-6 h-6 text-primary-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" />
              </svg>
              <!-- Database icon -->
              <svg v-else-if="tool.icon === 'database'" class="w-6 h-6 text-primary-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" />
              </svg>
              <!-- Refresh icon -->
              <svg v-else-if="tool.icon === 'refresh'" class="w-6 h-6 text-primary-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
              <!-- Document icon -->
              <svg v-else-if="tool.icon === 'document'" class="w-6 h-6 text-primary-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              <!-- Heart icon -->
              <svg v-else-if="tool.icon === 'heart'" class="w-6 h-6 text-primary-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" />
              </svg>
              <!-- Terminal icon -->
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
      <div v-if="activeTool" class="bg-white rounded-lg shadow-sm border border-gray-200" role="region" :aria-label="tools.find(t => t.id === activeTool)?.name || 'Tool panel'">
        <!-- Panel Header -->
        <div class="flex items-center justify-between px-6 py-4 border-b border-gray-200">
          <h2 class="text-lg font-semibold text-gray-900">
            {{ tools.find(t => t.id === activeTool)?.name }}
          </h2>
          <button
            @click="closeTool"
            class="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
            aria-label="Close tool panel"
          >
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <!-- Panel Content -->
        <div class="p-6">
          <!-- Network Test Tool -->
          <div v-if="activeTool === 'network-test'" class="space-y-4">
            <div>
              <label for="net-test-node" class="block text-sm font-medium text-gray-700 mb-2">Select Node</label>
              <select
                id="net-test-node"
                v-model="selectedNode"
                class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
              >
                <option value="">-- Select a node --</option>
                <option v-for="node in nodes" :key="node.node_id" :value="node.node_id">
                  {{ node.hostname }} ({{ node.ip_address }})
                </option>
              </select>
            </div>
            <button
              @click="runNetworkTest"
              :disabled="loading || !selectedNode"
              class="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed disabled:bg-gray-400 flex items-center gap-2"
            >
              <svg v-if="loading" class="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24" aria-hidden="true">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              {{ loading ? 'Testing...' : 'Run Test' }}
            </button>
          </div>

          <!-- Health Check Tool -->
          <div v-else-if="activeTool === 'health-check'" class="space-y-4">
            <div>
              <label for="health-check-node" class="block text-sm font-medium text-gray-700 mb-2">Select Node</label>
              <select
                id="health-check-node"
                v-model="selectedNode"
                class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
              >
                <option value="">-- Select a node --</option>
                <option v-for="node in nodes" :key="node.node_id" :value="node.node_id">
                  {{ node.hostname }} ({{ node.ip_address }})
                </option>
              </select>
            </div>
            <button
              @click="runHealthCheck"
              :disabled="loading || !selectedNode"
              class="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed disabled:bg-gray-400 flex items-center gap-2"
            >
              <svg v-if="loading" class="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24" aria-hidden="true">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              {{ loading ? 'Checking...' : 'Run Health Check' }}
            </button>
          </div>

          <!-- Service Manager Tool -->
          <div v-else-if="activeTool === 'service-restart'" class="space-y-4">
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label for="svc-mgr-node" class="block text-sm font-medium text-gray-700 mb-2">Select Node</label>
                <select
                  id="svc-mgr-node"
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
                <label for="svc-mgr-service" class="block text-sm font-medium text-gray-700 mb-2">Service Name</label>
                <input
                  type="text"
                  id="svc-mgr-service"
                  v-model="selectedService"
                  placeholder="e.g., autobot-agent, redis, nginx"
                  class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                />
              </div>
            </div>
            <div class="flex gap-2" role="group" aria-label="Service actions">
              <button
                @click="serviceAction('start')"
                :disabled="loading || !selectedNode || !selectedService"
                class="px-4 py-2 bg-success-600 text-white rounded-lg hover:bg-success-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed disabled:bg-gray-400"
                :aria-label="`Start ${selectedService || 'service'}`"
              >
                Start
              </button>
              <button
                @click="serviceAction('stop')"
                :disabled="loading || !selectedNode || !selectedService"
                class="px-4 py-2 bg-danger-600 text-white rounded-lg hover:bg-danger-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed disabled:bg-gray-400"
                :aria-label="`Stop ${selectedService || 'service'}`"
              >
                Stop
              </button>
              <button
                @click="serviceAction('restart')"
                :disabled="loading || !selectedNode || !selectedService"
                class="px-4 py-2 bg-warning-600 text-white rounded-lg hover:bg-warning-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed disabled:bg-gray-400"
                :aria-label="`Restart ${selectedService || 'service'}`"
              >
                Restart
              </button>
            </div>
          </div>

          <!-- Log Viewer Tool -->
          <div v-else-if="activeTool === 'log-viewer'" class="space-y-4">
            <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <label for="log-viewer-node" class="block text-sm font-medium text-gray-700 mb-2">Select Node</label>
                <select
                  id="log-viewer-node"
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
                <label for="log-viewer-service" class="block text-sm font-medium text-gray-700 mb-2">Service Name</label>
                <input
                  type="text"
                  id="log-viewer-service"
                  v-model="selectedService"
                  placeholder="e.g., autobot-agent"
                  class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                />
              </div>
              <div>
                <label for="log-viewer-lines" class="block text-sm font-medium text-gray-700 mb-2">Lines</label>
                <select
                  id="log-viewer-lines"
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
              class="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed disabled:bg-gray-400 flex items-center gap-2"
            >
              <svg v-if="loading" class="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24" aria-hidden="true">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              {{ loading ? 'Fetching...' : 'Get Logs' }}
            </button>
          </div>

          <!-- Redis CLI Tool -->
          <div v-else-if="activeTool === 'redis-cli'" class="space-y-4">
            <div>
              <label for="redis-command" class="block text-sm font-medium text-gray-700 mb-2">Redis Command</label>
              <input
                type="text"
                id="redis-command"
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
              class="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed disabled:bg-gray-400 flex items-center gap-2"
            >
              <svg v-if="loading" class="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24" aria-hidden="true">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              {{ loading ? 'Executing...' : 'Execute' }}
            </button>
          </div>

          <!-- Ansible Ad-Hoc Tool -->
          <div v-else-if="activeTool === 'ansible-runner'" class="space-y-4">
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label for="ansible-node" class="block text-sm font-medium text-gray-700 mb-2">Select Node</label>
                <select
                  id="ansible-node"
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
                <label for="ansible-command" class="block text-sm font-medium text-gray-700 mb-2">Command</label>
                <input
                  type="text"
                  id="ansible-command"
                  v-model="ansibleCommand"
                  placeholder="e.g., uptime, df -h, free -m"
                  class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 font-mono"
                />
              </div>
            </div>
            <p class="text-xs text-gray-500">
              Run shell commands on the selected node via Ansible. Be careful with destructive commands.
            </p>
            <button
              @click="runAnsibleCommand"
              :disabled="loading || !selectedNode || !ansibleCommand"
              class="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed disabled:bg-gray-400 flex items-center gap-2"
            >
              <svg v-if="loading" class="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24" aria-hidden="true">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              {{ loading ? 'Running...' : 'Run Command' }}
            </button>
          </div>

          <!-- Error Message -->
          <div v-if="error" class="mt-4 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700" role="alert">
            {{ error }}
          </div>

          <!-- Result Output -->
          <div v-if="result" class="mt-4" role="region" aria-label="Command output">
            <label for="tool-output" class="block text-sm font-medium text-gray-700 mb-2">Output</label>
            <pre id="tool-output" class="p-4 bg-gray-900 text-gray-100 rounded-lg overflow-auto max-h-96 text-sm font-mono whitespace-pre-wrap" role="log">{{ result }}</pre>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
