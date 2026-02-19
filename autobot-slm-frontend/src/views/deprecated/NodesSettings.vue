<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * @deprecated Issue #737: This component has been deprecated and archived.
 *
 * DEPRECATION NOTICE:
 * - Archived: 2026-02-02
 * - Reason: Consolidated duplicate UI into FleetOverview.vue
 * - Migration: All node management is now in FleetOverview (/)
 * - Route /settings/nodes redirects to Fleet Overview
 *
 * This file is preserved for reference during Phase 2 & 3 of issue #737
 * which involves creating shared composables and unifying data models.
 *
 * DO NOT USE THIS COMPONENT - Use FleetOverview.vue instead.
 *
 * Original description:
 * NodesSettings - Node management for SLM Admin
 * Provides infrastructure node management including enrollment,
 * testing, updates, and certificate management.
 */

import { ref, computed, onMounted } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { getBackendUrl } from '@/config/ssot-config'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('NodesSettings')

// Types
interface NodeMetrics {
  cpu: number
  ram: number
  uptime: number
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
}

const authStore = useAuthStore()

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
const showRemoveModal = ref(false)
const selectedNode = ref<InfrastructureNode | null>(null)
const forceRemove = ref(false)
const isRemoving = ref(false)

// Add node form
const newNode = ref({
  hostname: '',
  ip_address: '',
  ssh_user: 'autobot',
  ssh_port: 22,
  auth_method: 'pki' as 'password' | 'pki',
  password: '',
  role: 'custom',
  auto_enroll: true,
})

// Enrollment steps
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

// Methods
async function fetchNodes() {
  isLoading.value = true
  loadError.value = null

  try {
    const backendUrl = getBackendUrl()
    const response = await fetch(`${backendUrl}/api/infrastructure/nodes`, {
      headers: authStore.getAuthHeaders(),
    })

    if (!response.ok) {
      throw new Error(`Failed to fetch nodes: ${response.statusText}`)
    }

    const data = await response.json()
    nodes.value = data.nodes || []
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : 'Unknown error'
  } finally {
    isLoading.value = false
  }
}

async function fetchRoles() {
  try {
    const backendUrl = getBackendUrl()
    const response = await fetch(`${backendUrl}/api/infrastructure/nodes/roles`, {
      headers: authStore.getAuthHeaders(),
    })

    if (response.ok) {
      availableRoles.value = await response.json()
    }
  } catch (error) {
    // Use default roles if API fails
    availableRoles.value = [
      { id: 'frontend', name: 'Frontend Server', description: 'Vue.js frontend', services: ['vite-dev', 'nginx'] },
      { id: 'npu-worker', name: 'NPU Worker', description: 'Intel OpenVINO', services: ['npu-service'] },
      { id: 'redis', name: 'Redis Stack', description: 'Redis database', services: ['redis-stack'] },
      { id: 'ai-stack', name: 'AI Stack', description: 'LLM processing', services: ['llm-server'] },
      { id: 'browser', name: 'Browser Automation', description: 'Playwright/VNC', services: ['playwright', 'vnc'] },
      { id: 'custom', name: 'Custom', description: 'Custom configuration', services: [] },
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
      headers: authStore.getAuthHeaders(),
    })

    const result = await response.json()

    if (result.success) {
      const idx = nodes.value.findIndex(n => n.id === node.id)
      if (idx !== -1) {
        nodes.value[idx].status = 'online'
        nodes.value[idx].last_seen = new Date().toISOString()
        if (result.metrics) {
          nodes.value[idx].metrics = result.metrics
        }
      }
    }
  } catch (error) {
    logger.error('Connection test error:', error)
  } finally {
    testingNodeId.value = null
  }
}

async function handleAddNode() {
  showAddNodeModal.value = false

  try {
    const backendUrl = getBackendUrl()
    const response = await fetch(`${backendUrl}/api/infrastructure/nodes`, {
      method: 'POST',
      headers: {
        ...authStore.getAuthHeaders(),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        name: newNode.value.hostname,
        ip_address: newNode.value.ip_address,
        ssh_user: newNode.value.ssh_user,
        ssh_port: newNode.value.ssh_port,
        auth_method: newNode.value.auth_method,
        password: newNode.value.password,
        role: newNode.value.role,
        auto_enroll: newNode.value.auto_enroll,
      }),
    })

    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || 'Failed to add node')
    }

    const addedNode = await response.json()
    nodes.value.push(addedNode)

    // Reset form
    newNode.value = {
      hostname: '',
      ip_address: '',
      ssh_user: 'autobot',
      ssh_port: 22,
      auth_method: 'pki',
      password: '',
      role: 'custom',
      auto_enroll: true,
    }

    // Auto-enroll if requested
    if (newNode.value.auto_enroll) {
      enrollNode(addedNode)
    }
  } catch (error) {
    logger.error('Failed to add node:', error)
  }
}

async function enrollNode(node: InfrastructureNode) {
  enrollingNodeId.value = node.id

  const idx = nodes.value.findIndex(n => n.id === node.id)
  if (idx !== -1) {
    nodes.value[idx].status = 'enrolling'
    nodes.value[idx].enrollment_step = 0
  }

  try {
    const backendUrl = getBackendUrl()
    const response = await fetch(`${backendUrl}/api/infrastructure/nodes/${node.id}/enroll`, {
      method: 'POST',
      headers: authStore.getAuthHeaders(),
    })

    if (!response.ok) {
      throw new Error('Enrollment failed')
    }
  } catch (error) {
    logger.error('Failed to start enrollment:', error)
    if (idx !== -1) {
      nodes.value[idx].status = 'error'
    }
  } finally {
    enrollingNodeId.value = null
  }
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
      {
        method: 'DELETE',
        headers: authStore.getAuthHeaders(),
      }
    )

    if (!response.ok) {
      throw new Error('Failed to remove node')
    }

    nodes.value = nodes.value.filter(n => n.id !== selectedNode.value?.id)
    showRemoveModal.value = false
  } catch (error) {
    logger.error('Failed to remove node:', error)
  } finally {
    isRemoving.value = false
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
  if (stepIndex < currentStep) return 'text-success-600'
  if (stepIndex === currentStep) return 'text-primary-600'
  return 'text-gray-400'
}

function getStepIcon(currentStep: number | undefined, stepIndex: number): string {
  if (currentStep === undefined) return 'M8 12h.01'
  if (stepIndex < currentStep) return 'M5 13l4 4L19 7'
  if (stepIndex === currentStep) return 'M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15'
  return 'M8 12h.01'
}

// Lifecycle
onMounted(() => {
  fetchNodes()
  fetchRoles()
})
</script>

<template>
  <div class="p-6">
    <!-- Header -->
    <div class="flex items-center justify-between mb-6">
      <div>
        <h2 class="text-xl font-bold text-gray-900">Infrastructure Nodes</h2>
        <p class="text-sm text-gray-500">Manage AutoBot distributed infrastructure nodes</p>
      </div>
      <button
        @click="showAddNodeModal = true"
        class="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors flex items-center gap-2"
      >
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
        </svg>
        Add Node
      </button>
    </div>

    <!-- Stats Bar -->
    <div class="grid grid-cols-4 gap-4 mb-6">
      <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4 text-center">
        <p class="text-2xl font-bold text-gray-900">{{ stats.total }}</p>
        <p class="text-sm text-gray-500">Total</p>
      </div>
      <div class="bg-white rounded-lg shadow-sm border border-green-200 p-4 text-center">
        <p class="text-2xl font-bold text-green-700">{{ stats.online }}</p>
        <p class="text-sm text-green-600">Online</p>
      </div>
      <div class="bg-white rounded-lg shadow-sm border border-yellow-200 p-4 text-center">
        <p class="text-2xl font-bold text-yellow-700">{{ stats.pending }}</p>
        <p class="text-sm text-yellow-600">Pending</p>
      </div>
      <div class="bg-white rounded-lg shadow-sm border border-red-200 p-4 text-center">
        <p class="text-2xl font-bold text-red-700">{{ stats.error }}</p>
        <p class="text-sm text-red-600">Error</p>
      </div>
    </div>

    <!-- Loading State -->
    <div v-if="isLoading" class="flex items-center justify-center py-12">
      <svg class="animate-spin w-8 h-8 text-primary-600" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
      </svg>
    </div>

    <!-- Error State -->
    <div v-else-if="loadError" class="text-center py-12">
      <svg class="w-12 h-12 mx-auto text-red-400 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
      </svg>
      <p class="text-gray-900 font-medium">Failed to load nodes</p>
      <p class="text-gray-500 text-sm mt-1">{{ loadError }}</p>
      <button @click="fetchNodes" class="mt-4 px-4 py-2 bg-primary-600 text-white rounded-lg">
        Retry
      </button>
    </div>

    <!-- Empty State -->
    <div v-else-if="nodes.length === 0" class="text-center py-12 bg-white rounded-lg border border-gray-200">
      <svg class="w-12 h-12 mx-auto text-gray-400 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2" />
      </svg>
      <p class="text-gray-900 font-medium">No nodes configured</p>
      <p class="text-gray-500 text-sm mt-1">Add your first infrastructure node to get started</p>
      <button @click="showAddNodeModal = true" class="mt-4 px-4 py-2 bg-primary-600 text-white rounded-lg">
        Add First Node
      </button>
    </div>

    <!-- Nodes List -->
    <div v-else class="space-y-3">
      <div
        v-for="node in nodes"
        :key="node.id"
        class="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden"
        :class="{ 'border-primary-300': expandedNodeId === node.id }"
      >
        <!-- Node Header -->
        <div
          @click="toggleNodeExpand(node.id)"
          class="flex items-center p-4 cursor-pointer hover:bg-gray-50 transition-colors"
        >
          <!-- Status Indicator -->
          <div
            :class="[
              'w-3 h-3 rounded-full mr-4',
              node.status === 'online' ? 'bg-green-500' : '',
              node.status === 'pending' || node.status === 'enrolling' ? 'bg-yellow-500 animate-pulse' : '',
              node.status === 'offline' || node.status === 'error' ? 'bg-red-500' : '',
            ]"
          ></div>

          <!-- Node Info -->
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2">
              <p class="font-medium text-gray-900 truncate">{{ node.name }}</p>
              <span class="px-2 py-0.5 text-xs bg-gray-100 text-gray-600 rounded">
                {{ getRoleLabel(node.role) }}
              </span>
            </div>
            <p class="text-sm text-gray-500 font-mono">{{ node.ip_address }}</p>
          </div>

          <!-- Metrics (if online) -->
          <div v-if="node.status === 'online' && node.metrics" class="flex gap-6 text-sm mr-4">
            <div class="text-center">
              <p class="text-gray-400 text-xs">CPU</p>
              <p class="font-medium">{{ node.metrics.cpu }}%</p>
            </div>
            <div class="text-center">
              <p class="text-gray-400 text-xs">RAM</p>
              <p class="font-medium">{{ node.metrics.ram }}%</p>
            </div>
            <div class="text-center">
              <p class="text-gray-400 text-xs">Uptime</p>
              <p class="font-medium">{{ formatUptime(node.metrics.uptime) }}</p>
            </div>
          </div>

          <!-- Actions -->
          <div class="flex gap-2">
            <button
              v-if="node.status !== 'enrolling'"
              @click.stop="testNodeConnection(node)"
              :disabled="testingNodeId === node.id"
              class="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded disabled:opacity-50"
              title="Test Connection"
            >
              <svg v-if="testingNodeId === node.id" class="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              <svg v-else class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
            </button>
            <button
              @click.stop="toggleNodeExpand(node.id)"
              class="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded"
            >
              <svg
                class="w-5 h-5 transition-transform"
                :class="{ 'rotate-180': expandedNodeId === node.id }"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
              </svg>
            </button>
          </div>
        </div>

        <!-- Expanded Details -->
        <Transition name="expand">
          <div v-if="expandedNodeId === node.id" class="border-t border-gray-100 p-4 bg-gray-50">
            <!-- Details Grid -->
            <div class="grid grid-cols-3 gap-4 mb-4">
              <div>
                <p class="text-xs text-gray-400 uppercase">SSH User</p>
                <p class="text-sm font-medium">{{ node.ssh_user }}</p>
              </div>
              <div>
                <p class="text-xs text-gray-400 uppercase">SSH Port</p>
                <p class="text-sm font-medium">{{ node.ssh_port }}</p>
              </div>
              <div>
                <p class="text-xs text-gray-400 uppercase">Auth Method</p>
                <p class="text-sm font-medium">{{ node.auth_method === 'pki' ? 'PKI (SSH Key)' : 'Password' }}</p>
              </div>
              <div>
                <p class="text-xs text-gray-400 uppercase">Added</p>
                <p class="text-sm font-medium">{{ formatDate(node.created_at) }}</p>
              </div>
              <div>
                <p class="text-xs text-gray-400 uppercase">Last Seen</p>
                <p class="text-sm font-medium">{{ formatDate(node.last_seen) || 'Never' }}</p>
              </div>
              <div v-if="node.os">
                <p class="text-xs text-gray-400 uppercase">OS</p>
                <p class="text-sm font-medium">{{ node.os }}</p>
              </div>
            </div>

            <!-- Enrollment Progress -->
            <div v-if="node.status === 'enrolling'" class="mb-4 p-4 bg-blue-50 rounded-lg border border-blue-100">
              <div class="flex items-center gap-2 mb-3">
                <svg class="w-5 h-5 text-blue-500 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                  <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                <span class="font-medium text-blue-700">Enrolling node...</span>
              </div>
              <div class="space-y-2">
                <div
                  v-for="(step, index) in enrollmentSteps"
                  :key="index"
                  class="flex items-center gap-2 text-sm"
                  :class="getStepClass(node.enrollment_step, index)"
                >
                  <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" :d="getStepIcon(node.enrollment_step, index)" />
                  </svg>
                  <span>{{ step }}</span>
                </div>
              </div>
            </div>

            <!-- Actions -->
            <div class="flex gap-3">
              <button
                v-if="node.status === 'pending'"
                @click="enrollNode(node)"
                :disabled="enrollingNodeId === node.id"
                class="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50 flex items-center gap-2"
              >
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                Start Enrollment
              </button>
              <button
                @click="confirmRemoveNode(node)"
                class="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 flex items-center gap-2"
              >
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
                Remove
              </button>
            </div>
          </div>
        </Transition>
      </div>
    </div>

    <!-- Add Node Modal -->
    <Teleport to="body">
      <Transition name="modal">
        <div v-if="showAddNodeModal" class="fixed inset-0 z-50 flex items-center justify-center">
          <div class="absolute inset-0 bg-black/50" @click="showAddNodeModal = false"></div>
          <div class="relative bg-white rounded-lg shadow-xl w-full max-w-lg mx-4 p-6">
            <h3 class="text-lg font-semibold mb-4">Add Infrastructure Node</h3>

            <div class="space-y-4">
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">Hostname</label>
                <input
                  v-model="newNode.hostname"
                  type="text"
                  placeholder="e.g., frontend-vm"
                  class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
                />
              </div>

              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">IP Address</label>
                <input
                  v-model="newNode.ip_address"
                  type="text"
                  placeholder="e.g., 172.16.168.21"
                  class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
                />
              </div>

              <div class="grid grid-cols-2 gap-4">
                <div>
                  <label class="block text-sm font-medium text-gray-700 mb-1">SSH User</label>
                  <input
                    v-model="newNode.ssh_user"
                    type="text"
                    class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
                  />
                </div>
                <div>
                  <label class="block text-sm font-medium text-gray-700 mb-1">SSH Port</label>
                  <input
                    v-model.number="newNode.ssh_port"
                    type="number"
                    class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
                  />
                </div>
              </div>

              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">Role</label>
                <select
                  v-model="newNode.role"
                  class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
                >
                  <option v-for="role in availableRoles" :key="role.id" :value="role.id">
                    {{ role.name }} - {{ role.description }}
                  </option>
                </select>
              </div>

              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">Authentication</label>
                <select
                  v-model="newNode.auth_method"
                  class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
                >
                  <option value="pki">PKI (SSH Key)</option>
                  <option value="password">Password</option>
                </select>
              </div>

              <div v-if="newNode.auth_method === 'password'">
                <label class="block text-sm font-medium text-gray-700 mb-1">Password</label>
                <input
                  v-model="newNode.password"
                  type="password"
                  class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
                />
              </div>

              <div class="flex items-center gap-2">
                <input
                  v-model="newNode.auto_enroll"
                  type="checkbox"
                  id="auto_enroll"
                  class="rounded border-gray-300"
                />
                <label for="auto_enroll" class="text-sm text-gray-700">
                  Automatically start enrollment after adding
                </label>
              </div>
            </div>

            <div class="flex justify-end gap-3 mt-6">
              <button
                @click="showAddNodeModal = false"
                class="px-4 py-2 text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200"
              >
                Cancel
              </button>
              <button
                @click="handleAddNode"
                :disabled="!newNode.hostname || !newNode.ip_address"
                class="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50"
              >
                Add Node
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- Remove Confirmation Modal -->
    <Teleport to="body">
      <Transition name="modal">
        <div v-if="showRemoveModal" class="fixed inset-0 z-50 flex items-center justify-center">
          <div class="absolute inset-0 bg-black/50" @click="showRemoveModal = false"></div>
          <div class="relative bg-white rounded-lg shadow-xl w-full max-w-md mx-4 p-6">
            <h3 class="text-lg font-semibold mb-4">Remove Node</h3>

            <div v-if="selectedNode" class="mb-4">
              <div class="p-4 bg-red-50 border border-red-200 rounded-lg mb-4">
                <p class="text-sm text-red-700">
                  You are about to remove <strong>{{ selectedNode.name }}</strong> ({{ selectedNode.ip_address }}).
                </p>
              </div>

              <p class="text-sm text-gray-600 mb-3">This will:</p>
              <ul class="text-sm text-gray-600 list-disc list-inside space-y-1">
                <li>Stop all services on this node</li>
                <li>Remove certificates and credentials</li>
                <li>Update configuration to exclude this node</li>
              </ul>

              <div class="mt-4 flex items-center gap-2">
                <input
                  v-model="forceRemove"
                  type="checkbox"
                  id="force_remove"
                  class="rounded border-gray-300"
                />
                <label for="force_remove" class="text-sm text-gray-700">
                  Force remove (skip safety checks)
                </label>
              </div>
            </div>

            <div class="flex justify-end gap-3">
              <button
                @click="showRemoveModal = false"
                class="px-4 py-2 text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200"
              >
                Cancel
              </button>
              <button
                @click="removeNode"
                :disabled="isRemoving"
                class="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50 flex items-center gap-2"
              >
                <svg v-if="isRemoving" class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                  <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                {{ isRemoving ? 'Removing...' : 'Remove Node' }}
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped>
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

.modal-enter-active,
.modal-leave-active {
  transition: all 0.2s ease;
}

.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}
</style>
