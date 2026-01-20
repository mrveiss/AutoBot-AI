<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * ServicesView - Services grouped by host with per-service control
 *
 * Displays all systemd services grouped by host, with the ability to
 * start/stop/restart individual services on specific nodes.
 * Supports filtering by category (AutoBot vs System services).
 *
 * Related to Issue #728
 */

import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useSlmApi } from '@/composables/useSlmApi'
import { useSlmWebSocket } from '@/composables/useSlmWebSocket'
import { useFleetStore } from '@/stores/fleet'
import { createLogger } from '@/utils/debugUtils'
import type { FleetServiceStatus, ServiceStatus, ServiceCategory, SLMNode } from '@/types/slm'

const logger = createLogger('ServicesView')
const api = useSlmApi()
const fleetStore = useFleetStore()
const { connect, subscribeAll, onServiceStatus, connected } = useSlmWebSocket()

// State
const services = ref<FleetServiceStatus[]>([])
const totalServices = ref(0)
const isLoading = ref(true)
const errorMessage = ref<string | null>(null)
const lastRefresh = ref<string | null>(null)

// Filters
const searchQuery = ref('')
const statusFilter = ref<string>('all')
const categoryFilter = ref<ServiceCategory | 'all'>('autobot')
const autoRefresh = ref(true)
const autoRefreshInterval = 15000

// Expanded nodes
const expandedNodes = ref<Set<string>>(new Set())

// Action state
const isActionInProgress = ref(false)
const actionNodeId = ref<string | null>(null)
const actionService = ref<string | null>(null)
const actionType = ref<string | null>(null)

// Category change state
const categoryMenuOpen = ref<string | null>(null)
const isCategoryChanging = ref(false)

// Refresh interval
let refreshInterval: ReturnType<typeof setInterval> | null = null

// Status filter options
const statusOptions = [
  { value: 'all', label: 'All Services' },
  { value: 'running', label: 'Running' },
  { value: 'stopped', label: 'Stopped' },
  { value: 'failed', label: 'Failed' },
]

// Category counts
const categoryCounts = computed(() => {
  const autobot = services.value.filter(s => s.category === 'autobot').length
  const system = services.value.filter(s => s.category === 'system').length
  return { autobot, system, all: services.value.length }
})

// Get unique nodes from fleet store
const nodes = computed(() => fleetStore.nodes)

// Group services by node
interface NodeServiceGroup {
  nodeId: string
  hostname: string
  ipAddress: string
  status: string
  services: Array<{
    service_name: string
    category: ServiceCategory
    status: ServiceStatus
  }>
  runningCount: number
  stoppedCount: number
  failedCount: number
}

const servicesByNode = computed<NodeServiceGroup[]>(() => {
  // Build a map of node services from the fleet services data
  const nodeMap = new Map<string, NodeServiceGroup>()

  // Initialize from nodes
  for (const node of nodes.value) {
    nodeMap.set(node.node_id, {
      nodeId: node.node_id,
      hostname: node.hostname,
      ipAddress: node.ip_address,
      status: node.status,
      services: [],
      runningCount: 0,
      stoppedCount: 0,
      failedCount: 0,
    })
  }

  // Populate services from fleet data
  for (const service of services.value) {
    // Apply category filter
    if (categoryFilter.value !== 'all' && service.category !== categoryFilter.value) {
      continue
    }

    // Apply search filter
    if (searchQuery.value) {
      const query = searchQuery.value.toLowerCase()
      if (!service.service_name.toLowerCase().includes(query)) {
        continue
      }
    }

    // Add service to each node it exists on
    for (const nodeInfo of service.nodes) {
      const nodeGroup = nodeMap.get(nodeInfo.node_id)
      if (nodeGroup) {
        // Apply status filter
        if (statusFilter.value !== 'all' && nodeInfo.status !== statusFilter.value) {
          continue
        }

        nodeGroup.services.push({
          service_name: service.service_name,
          category: service.category,
          status: nodeInfo.status,
        })

        if (nodeInfo.status === 'running') nodeGroup.runningCount++
        else if (nodeInfo.status === 'stopped') nodeGroup.stoppedCount++
        else if (nodeInfo.status === 'failed') nodeGroup.failedCount++
      }
    }
  }

  // Sort services within each node
  for (const nodeGroup of nodeMap.values()) {
    nodeGroup.services.sort((a, b) => a.service_name.localeCompare(b.service_name))
  }

  // Return nodes that have services, sorted by hostname
  return Array.from(nodeMap.values())
    .filter(n => n.services.length > 0)
    .sort((a, b) => a.hostname.localeCompare(b.hostname))
})

// Summary stats
const summaryStats = computed(() => {
  let totalServices = 0
  let running = 0
  let stopped = 0
  let failed = 0

  for (const node of servicesByNode.value) {
    totalServices += node.services.length
    running += node.runningCount
    stopped += node.stoppedCount
    failed += node.failedCount
  }

  return { totalServices, running, stopped, failed, nodes: servicesByNode.value.length }
})

// Methods
function getStatusDotClass(status: ServiceStatus): string {
  switch (status) {
    case 'running': return 'bg-green-500'
    case 'stopped': return 'bg-gray-400'
    case 'failed': return 'bg-red-500'
    default: return 'bg-yellow-500'
  }
}

function getStatusTextClass(status: ServiceStatus): string {
  switch (status) {
    case 'running': return 'text-green-600'
    case 'stopped': return 'text-gray-500'
    case 'failed': return 'text-red-600'
    default: return 'text-yellow-600'
  }
}

function getCategoryBadgeClass(category: ServiceCategory): string {
  return category === 'autobot'
    ? 'bg-primary-100 text-primary-700'
    : 'bg-slate-100 text-slate-600'
}

function toggleNode(nodeId: string): void {
  if (expandedNodes.value.has(nodeId)) {
    expandedNodes.value.delete(nodeId)
  } else {
    expandedNodes.value.add(nodeId)
  }
  // Trigger reactivity
  expandedNodes.value = new Set(expandedNodes.value)
}

function expandAll(): void {
  expandedNodes.value = new Set(servicesByNode.value.map(n => n.nodeId))
}

function collapseAll(): void {
  expandedNodes.value = new Set()
}

async function fetchServices(): Promise<void> {
  try {
    const response = await api.getFleetServices()
    services.value = response.services
    totalServices.value = response.total_services
    lastRefresh.value = new Date().toISOString()
    errorMessage.value = null

    // Auto-expand first few nodes on initial load
    if (expandedNodes.value.size === 0 && servicesByNode.value.length > 0) {
      const nodesToExpand = servicesByNode.value.slice(0, 3)
      expandedNodes.value = new Set(nodesToExpand.map(n => n.nodeId))
    }
  } catch (error) {
    logger.error('Failed to fetch fleet services:', error)
    errorMessage.value = 'Failed to load services'
  } finally {
    isLoading.value = false
  }
}

async function handleServiceAction(
  nodeId: string,
  serviceName: string,
  action: 'start' | 'stop' | 'restart'
): Promise<void> {
  if (isActionInProgress.value) return

  isActionInProgress.value = true
  actionNodeId.value = nodeId
  actionService.value = serviceName
  actionType.value = action

  try {
    const result = await api.serviceAction(nodeId, serviceName, action)

    if (result.success) {
      // Update local state optimistically
      const service = services.value.find(s => s.service_name === serviceName)
      if (service) {
        const nodeInfo = service.nodes.find(n => n.node_id === nodeId)
        if (nodeInfo) {
          if (action === 'start' || action === 'restart') {
            nodeInfo.status = 'running'
          } else if (action === 'stop') {
            nodeInfo.status = 'stopped'
          }
          // Recalculate counts
          service.running_count = service.nodes.filter(n => n.status === 'running').length
          service.stopped_count = service.nodes.filter(n => n.status === 'stopped').length
          service.failed_count = service.nodes.filter(n => n.status === 'failed').length
        }
      }
    } else {
      errorMessage.value = result.message
    }
  } catch (error) {
    logger.error(`Failed to ${action} service:`, error)
    errorMessage.value = `Failed to ${action} ${serviceName}`
  } finally {
    isActionInProgress.value = false
    actionNodeId.value = null
    actionService.value = null
    actionType.value = null
  }
}

async function handleCategoryChange(
  serviceName: string,
  newCategory: ServiceCategory
): Promise<void> {
  if (isCategoryChanging.value) return

  isCategoryChanging.value = true
  categoryMenuOpen.value = null

  try {
    await api.updateServiceCategory(serviceName, newCategory)
    const service = services.value.find(s => s.service_name === serviceName)
    if (service) {
      service.category = newCategory
    }
    logger.info(`Service ${serviceName} category changed to ${newCategory}`)
  } catch (error) {
    logger.error(`Failed to update category for ${serviceName}:`, error)
    errorMessage.value = `Failed to update category for ${serviceName}`
  } finally {
    isCategoryChanging.value = false
  }
}

function toggleCategoryMenu(serviceName: string): void {
  if (categoryMenuOpen.value === serviceName) {
    categoryMenuOpen.value = null
  } else {
    categoryMenuOpen.value = serviceName
  }
}

function handleClickOutside(event: MouseEvent): void {
  const target = event.target as HTMLElement
  if (!target.closest('.category-menu-container')) {
    categoryMenuOpen.value = null
  }
}

function toggleAutoRefresh(): void {
  autoRefresh.value = !autoRefresh.value
  if (autoRefresh.value) {
    refreshInterval = setInterval(fetchServices, autoRefreshInterval)
  } else if (refreshInterval) {
    clearInterval(refreshInterval)
    refreshInterval = null
  }
}

function isActionOnService(nodeId: string, serviceName: string): boolean {
  return actionNodeId.value === nodeId && actionService.value === serviceName
}

// Handle real-time service status updates via WebSocket
function handleServiceStatusUpdate(
  nodeId: string,
  data: { service_name: string; status: string }
): void {
  const service = services.value.find(s => s.service_name === data.service_name)
  if (!service) return

  const nodeInfo = service.nodes.find(n => n.node_id === nodeId)
  if (!nodeInfo) return

  nodeInfo.status = data.status as ServiceStatus
  service.running_count = service.nodes.filter(n => n.status === 'running').length
  service.stopped_count = service.nodes.filter(n => n.status === 'stopped').length
  service.failed_count = service.nodes.filter(n => n.status === 'failed').length

  logger.debug('Service status updated via WebSocket:', data.service_name, nodeId, data.status)
}

// Lifecycle
onMounted(() => {
  fetchServices()
  fleetStore.fetchNodes()
  connect()
  subscribeAll()
  onServiceStatus(handleServiceStatusUpdate)

  if (autoRefresh.value) {
    refreshInterval = setInterval(fetchServices, autoRefreshInterval)
  }

  document.addEventListener('click', handleClickOutside)
})

onUnmounted(() => {
  if (refreshInterval) {
    clearInterval(refreshInterval)
  }
  document.removeEventListener('click', handleClickOutside)
})
</script>

<template>
  <div class="p-6">
    <!-- Header -->
    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-2xl font-bold text-gray-900">Fleet Services</h1>
        <p class="text-sm text-gray-500 mt-1">
          Manage systemd services across all fleet nodes - grouped by host
        </p>
      </div>
      <div class="flex items-center gap-3">
        <div class="flex items-center gap-1.5 text-sm">
          <span
            :class="[
              'w-2 h-2 rounded-full',
              connected ? 'bg-green-500' : 'bg-gray-400'
            ]"
          ></span>
          <span :class="connected ? 'text-green-600' : 'text-gray-500'">
            {{ connected ? 'Live' : 'Offline' }}
          </span>
        </div>
        <label class="flex items-center gap-2 text-sm text-gray-600 cursor-pointer">
          <input
            type="checkbox"
            :checked="autoRefresh"
            @change="toggleAutoRefresh"
            class="w-4 h-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500"
          />
          Auto-refresh
        </label>
        <button
          @click="fetchServices"
          :disabled="isLoading"
          class="btn btn-secondary flex items-center gap-2"
        >
          <svg
            :class="['w-4 h-4', isLoading ? 'animate-spin' : '']"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
            />
          </svg>
          Refresh
        </button>
      </div>
    </div>

    <!-- Summary Cards -->
    <div class="grid grid-cols-1 md:grid-cols-5 gap-4 mb-6">
      <div class="card p-4">
        <div class="text-sm text-gray-500">Nodes</div>
        <div class="text-2xl font-bold text-gray-900">{{ summaryStats.nodes }}</div>
      </div>
      <div class="card p-4">
        <div class="text-sm text-gray-500">Total Services</div>
        <div class="text-2xl font-bold text-gray-900">{{ summaryStats.totalServices }}</div>
      </div>
      <div class="card p-4 border-l-4 border-green-500">
        <div class="text-sm text-gray-500">Running</div>
        <div class="text-2xl font-bold text-green-600">{{ summaryStats.running }}</div>
      </div>
      <div class="card p-4 border-l-4 border-gray-400">
        <div class="text-sm text-gray-500">Stopped</div>
        <div class="text-2xl font-bold text-gray-600">{{ summaryStats.stopped }}</div>
      </div>
      <div class="card p-4 border-l-4 border-red-500">
        <div class="text-sm text-gray-500">Failed</div>
        <div class="text-2xl font-bold text-red-600">{{ summaryStats.failed }}</div>
      </div>
    </div>

    <!-- Error Banner -->
    <div
      v-if="errorMessage"
      class="mb-4 px-4 py-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700 flex items-center justify-between"
    >
      <span>{{ errorMessage }}</span>
      <button @click="errorMessage = null" class="text-red-500 hover:text-red-700">
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>

    <!-- Filter Bar -->
    <div class="card mb-6">
      <div class="flex items-center gap-4 p-4">
        <!-- Category Toggle Buttons -->
        <div class="flex rounded-lg border border-gray-300 overflow-hidden">
          <button
            @click="categoryFilter = 'autobot'"
            :class="[
              'px-3 py-1.5 text-sm font-medium transition-colors',
              categoryFilter === 'autobot'
                ? 'bg-primary-600 text-white'
                : 'bg-white text-gray-700 hover:bg-gray-50'
            ]"
          >
            AutoBot ({{ categoryCounts.autobot }})
          </button>
          <button
            @click="categoryFilter = 'system'"
            :class="[
              'px-3 py-1.5 text-sm font-medium transition-colors border-l border-gray-300',
              categoryFilter === 'system'
                ? 'bg-primary-600 text-white'
                : 'bg-white text-gray-700 hover:bg-gray-50'
            ]"
          >
            System ({{ categoryCounts.system }})
          </button>
          <button
            @click="categoryFilter = 'all'"
            :class="[
              'px-3 py-1.5 text-sm font-medium transition-colors border-l border-gray-300',
              categoryFilter === 'all'
                ? 'bg-primary-600 text-white'
                : 'bg-white text-gray-700 hover:bg-gray-50'
            ]"
          >
            All ({{ categoryCounts.all }})
          </button>
        </div>

        <!-- Search -->
        <div class="flex-1 relative">
          <svg class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <input
            v-model="searchQuery"
            type="text"
            placeholder="Search services..."
            class="w-full pl-9 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-primary-500 focus:border-primary-500"
          />
        </div>

        <!-- Status Filter -->
        <div class="flex items-center gap-2">
          <label class="text-sm text-gray-600">Status:</label>
          <select
            v-model="statusFilter"
            class="border-gray-300 rounded-lg focus:ring-primary-500 focus:border-primary-500"
          >
            <option v-for="option in statusOptions" :key="option.value" :value="option.value">
              {{ option.label }}
            </option>
          </select>
        </div>

        <!-- Expand/Collapse -->
        <div class="flex items-center gap-2">
          <button @click="expandAll" class="text-sm text-primary-600 hover:text-primary-800">
            Expand All
          </button>
          <span class="text-gray-300">|</span>
          <button @click="collapseAll" class="text-sm text-primary-600 hover:text-primary-800">
            Collapse All
          </button>
        </div>
      </div>
    </div>

    <!-- Loading State -->
    <div v-if="isLoading && services.length === 0" class="card p-12 text-center">
      <svg class="w-8 h-8 animate-spin mx-auto mb-3 text-gray-400" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
      </svg>
      <p class="text-gray-500">Loading fleet services...</p>
    </div>

    <!-- Empty State -->
    <div v-else-if="servicesByNode.length === 0" class="card p-12 text-center">
      <svg class="w-16 h-16 mx-auto text-gray-400 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01" />
      </svg>
      <h3 class="text-lg font-medium text-gray-900 mb-2">No services found</h3>
      <p class="text-gray-500">
        No services match your current filters. Try adjusting the category or search criteria.
      </p>
    </div>

    <!-- Services Grouped by Node -->
    <div v-else class="space-y-4">
      <div
        v-for="node in servicesByNode"
        :key="node.nodeId"
        class="card overflow-hidden"
      >
        <!-- Node Header (Clickable) -->
        <button
          @click="toggleNode(node.nodeId)"
          class="w-full flex items-center justify-between p-4 hover:bg-gray-50 transition-colors"
        >
          <div class="flex items-center gap-4">
            <!-- Expand/Collapse Icon -->
            <svg
              :class="[
                'w-5 h-5 text-gray-400 transition-transform',
                expandedNodes.has(node.nodeId) ? 'rotate-90' : ''
              ]"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
            </svg>

            <!-- Node Info -->
            <div class="text-left">
              <div class="flex items-center gap-2">
                <span class="font-semibold text-gray-900">{{ node.hostname }}</span>
                <span class="text-sm text-gray-500">({{ node.ipAddress }})</span>
              </div>
              <div class="text-sm text-gray-500">
                {{ node.services.length }} services
              </div>
            </div>
          </div>

          <!-- Status Summary -->
          <div class="flex items-center gap-4">
            <div class="flex items-center gap-1.5 text-sm">
              <span class="w-2 h-2 rounded-full bg-green-500"></span>
              <span class="text-green-600">{{ node.runningCount }}</span>
            </div>
            <div class="flex items-center gap-1.5 text-sm">
              <span class="w-2 h-2 rounded-full bg-gray-400"></span>
              <span class="text-gray-500">{{ node.stoppedCount }}</span>
            </div>
            <div v-if="node.failedCount > 0" class="flex items-center gap-1.5 text-sm">
              <span class="w-2 h-2 rounded-full bg-red-500"></span>
              <span class="text-red-600">{{ node.failedCount }}</span>
            </div>
          </div>
        </button>

        <!-- Services List (Expandable) -->
        <div v-if="expandedNodes.has(node.nodeId)" class="border-t border-gray-100">
          <table class="w-full">
            <thead>
              <tr class="bg-gray-50 text-xs text-gray-500 uppercase">
                <th class="px-4 py-2 text-left">Service</th>
                <th class="px-4 py-2 text-left w-24">Category</th>
                <th class="px-4 py-2 text-left w-24">Status</th>
                <th class="px-4 py-2 text-right w-32">Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="service in node.services"
                :key="service.service_name"
                class="border-t border-gray-50 hover:bg-gray-50"
              >
                <td class="px-4 py-2">
                  <span class="font-medium text-gray-900">{{ service.service_name }}</span>
                </td>
                <td class="px-4 py-2">
                  <div class="relative category-menu-container">
                    <button
                      @click.stop="toggleCategoryMenu(`${node.nodeId}-${service.service_name}`)"
                      :class="[
                        'inline-flex items-center px-1.5 py-0.5 text-xs font-medium rounded cursor-pointer hover:opacity-80',
                        getCategoryBadgeClass(service.category)
                      ]"
                    >
                      {{ service.category === 'autobot' ? 'AutoBot' : 'System' }}
                      <svg class="w-3 h-3 ml-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
                      </svg>
                    </button>
                    <div
                      v-if="categoryMenuOpen === `${node.nodeId}-${service.service_name}`"
                      class="absolute left-0 mt-1 w-28 bg-white rounded-lg shadow-lg border border-gray-200 z-10"
                    >
                      <button
                        @click="handleCategoryChange(service.service_name, 'autobot')"
                        :disabled="isCategoryChanging"
                        class="w-full px-3 py-1.5 text-left text-xs hover:bg-gray-50 rounded-t-lg"
                      >
                        AutoBot
                      </button>
                      <button
                        @click="handleCategoryChange(service.service_name, 'system')"
                        :disabled="isCategoryChanging"
                        class="w-full px-3 py-1.5 text-left text-xs hover:bg-gray-50 rounded-b-lg border-t border-gray-100"
                      >
                        System
                      </button>
                    </div>
                  </div>
                </td>
                <td class="px-4 py-2">
                  <div class="flex items-center gap-1.5">
                    <span :class="['w-2 h-2 rounded-full', getStatusDotClass(service.status)]"></span>
                    <span :class="['text-sm capitalize', getStatusTextClass(service.status)]">
                      {{ service.status }}
                    </span>
                  </div>
                </td>
                <td class="px-4 py-2">
                  <div class="flex items-center justify-end gap-1">
                    <!-- Start -->
                    <button
                      v-if="service.status !== 'running'"
                      @click.stop="handleServiceAction(node.nodeId, service.service_name, 'start')"
                      :disabled="isActionInProgress"
                      class="p-1 text-green-600 hover:bg-green-50 rounded disabled:opacity-50"
                      title="Start"
                    >
                      <svg
                        v-if="isActionOnService(node.nodeId, service.service_name) && actionType === 'start'"
                        class="w-4 h-4 animate-spin"
                        fill="none"
                        viewBox="0 0 24 24"
                      >
                        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
                      </svg>
                      <svg v-else class="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                        <path d="M8 5v14l11-7z" />
                      </svg>
                    </button>

                    <!-- Stop -->
                    <button
                      v-if="service.status === 'running'"
                      @click.stop="handleServiceAction(node.nodeId, service.service_name, 'stop')"
                      :disabled="isActionInProgress"
                      class="p-1 text-red-600 hover:bg-red-50 rounded disabled:opacity-50"
                      title="Stop"
                    >
                      <svg
                        v-if="isActionOnService(node.nodeId, service.service_name) && actionType === 'stop'"
                        class="w-4 h-4 animate-spin"
                        fill="none"
                        viewBox="0 0 24 24"
                      >
                        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
                      </svg>
                      <svg v-else class="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                        <rect x="6" y="6" width="12" height="12" />
                      </svg>
                    </button>

                    <!-- Restart -->
                    <button
                      @click.stop="handleServiceAction(node.nodeId, service.service_name, 'restart')"
                      :disabled="isActionInProgress"
                      class="p-1 text-blue-600 hover:bg-blue-50 rounded disabled:opacity-50"
                      title="Restart"
                    >
                      <svg
                        v-if="isActionOnService(node.nodeId, service.service_name) && actionType === 'restart'"
                        class="w-4 h-4 animate-spin"
                        fill="none"
                        viewBox="0 0 24 24"
                      >
                        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
                      </svg>
                      <svg v-else class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                      </svg>
                    </button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>
