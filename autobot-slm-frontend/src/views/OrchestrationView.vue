<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Unified OrchestrationView - Complete orchestration management (Issue #850 Phase 4)
 *
 * Consolidates 4 pages into single 5-tab view:
 * 1. Per-Node Control (from ServicesView)
 * 2. Fleet Operations (from OrchestrationView)
 * 3. Roles & Deployment (from RolesView)
 * 4. Migration & Advanced (from OrchestrationView)
 * 5. Infrastructure Overview (from InfrastructureSettings)
 */

import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useOrchestrationManagement } from '@/composables/useOrchestrationManagement'
import { useRoles, type Role } from '@/composables/useRoles'
import { createLogger } from '@/utils/debugUtils'
import ServiceStatusBadge from '@/components/orchestration/ServiceStatusBadge.vue'
import ServiceActionButtons from '@/components/orchestration/ServiceActionButtons.vue'
import NodeHealthCard from '@/components/orchestration/NodeHealthCard.vue'
import RestartConfirmDialog from '@/components/orchestration/RestartConfirmDialog.vue'

const logger = createLogger('OrchestrationView')

// Initialize composables
const route = useRoute()
const router = useRouter()
const orchestration = useOrchestrationManagement()
const roles = useRoles()

// =============================================================================
// Tab Management (Issue #924: subroutes via :tab? param)
// =============================================================================

const VALID_TABS = ['per-node', 'fleet', 'roles', 'migration', 'infrastructure'] as const
type Tab = (typeof VALID_TABS)[number]

function resolveTab(param: unknown): Tab {
  const t = param as string
  return VALID_TABS.includes(t as Tab) ? (t as Tab) : 'per-node'
}

const activeTab = ref<Tab>(resolveTab(route.params.tab))

// Keep activeTab in sync when the user navigates via browser back/forward
watch(() => route.params.tab, (tab) => {
  activeTab.value = resolveTab(tab)
})

function navigateToTab(tab: Tab): void {
  activeTab.value = tab
  router.push({ name: 'orchestration', params: { tab } })
}

const tabs: { id: Tab; label: string; icon: string }[] = [
  { id: 'per-node', label: 'Per-Node Control', icon: 'server' },
  { id: 'fleet', label: 'Fleet Operations', icon: 'globe' },
  { id: 'roles', label: 'Roles & Deployment', icon: 'cog' },
  { id: 'migration', label: 'Migration', icon: 'arrows' },
  { id: 'infrastructure', label: 'Overview', icon: 'chart' },
]

// =============================================================================
// Tab 1: Per-Node Control State
// =============================================================================

const searchQuery = ref('')
const categoryFilter = ref<'autobot' | 'system' | 'all'>('all')
const statusFilter = ref<string>('all')
const expandedNodes = ref<Set<string>>(new Set())
const autoRefresh = ref(true)
let refreshInterval: ReturnType<typeof setInterval> | null = null

// Group services by node
interface NodeServiceGroup {
  nodeId: string
  hostname: string
  ipAddress: string
  status: string
  services: Array<{
    service_name: string
    category: string
    status: string
  }>
  runningCount: number
  stoppedCount: number
  failedCount: number
}

const servicesByNode = computed<NodeServiceGroup[]>(() => {
  const nodeMap = new Map<string, NodeServiceGroup>()

  // Initialize from nodes
  for (const node of orchestration.fleetStore.nodeList) {
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

  // Populate with services
  if (Array.isArray(orchestration.fleetServices)) {
    for (const fleetService of orchestration.fleetServices) {
      // Apply category filter
      if (categoryFilter.value !== 'all' && fleetService.category !== categoryFilter.value) {
        continue
      }

      // Apply search filter
      if (
        searchQuery.value &&
        !fleetService.service_name.toLowerCase().includes(searchQuery.value.toLowerCase())
      ) {
        continue
      }

      for (const nodeStatus of fleetService.nodes) {
      const nodeGroup = nodeMap.get(nodeStatus.node_id)
      if (!nodeGroup) continue

      // Apply status filter
      if (statusFilter.value !== 'all' && nodeStatus.status !== statusFilter.value) {
        continue
      }

      nodeGroup.services.push({
        service_name: fleetService.service_name,
        category: fleetService.category,
        status: nodeStatus.status,
      })

      // Update counts
      if (nodeStatus.status === 'running') nodeGroup.runningCount++
      else if (nodeStatus.status === 'stopped') nodeGroup.stoppedCount++
      else if (nodeStatus.status === 'failed') nodeGroup.failedCount++
    }
  }
  }

  // Filter out nodes with no services (after filtering)
  return Array.from(nodeMap.values()).filter((node) => node.services.length > 0)
})

const categoryCounts = computed(() => {
  const counts = { autobot: 0, system: 0, all: 0 }
  if (Array.isArray(orchestration.fleetServices)) {
    for (const svc of orchestration.fleetServices) {
      counts[svc.category as 'autobot' | 'system']++
      counts.all++
    }
  }
  return counts
})

// =============================================================================
// Tab 2: Fleet Operations State
// =============================================================================

const fleetSearchQuery = ref('')
const fleetCategoryFilter = ref<'autobot' | 'system' | 'all'>('all')

const filteredFleetServices = computed(() => {
  if (!Array.isArray(orchestration.fleetServices)) {
    return []
  }
  return orchestration.fleetServices.filter((svc) => {
    // Category filter
    if (fleetCategoryFilter.value !== 'all' && svc.category !== fleetCategoryFilter.value) {
      return false
    }
    // Search filter
    if (
      fleetSearchQuery.value &&
      !svc.service_name.toLowerCase().includes(fleetSearchQuery.value.toLowerCase())
    ) {
      return false
    }
    return true
  })
})

// =============================================================================
// Tab 3: Roles & Deployment State
// =============================================================================

const showRoleForm = ref(false)
const editingRole = ref<string | null>(null)
const roleFormData = ref({
  name: '',
  display_name: '',
  sync_type: 'component',
  source_paths: '',
  target_path: '/opt/autobot',
  systemd_service: '',
  auto_restart: false,
  health_check_port: '',
  health_check_path: '',
  pre_sync_cmd: '',
  post_sync_cmd: '',
})

// =============================================================================
// Tab 4: Migration State (role-based)
// =============================================================================

const migrationRole = ref<Role | null>(null)
const migrationSourceNode = ref('')
const migrationTargetNode = ref('')
const migrationRemoveFromSource = ref(false)
const migrationRestart = ref(true)
const migrationInProgress = ref(false)
const migrationResult = ref<{
  success: boolean
  message: string
  details: Array<{ node_id: string; success: boolean; message: string }>
} | null>(null)

// =============================================================================
// Tab 5: Infrastructure Overview State
// =============================================================================

const infrastructureStats = computed(() => {
  const nodes = orchestration.fleetStore.nodeList
  return {
    totalNodes: nodes.length,
    onlineNodes: nodes.filter((n) => n.status === 'online').length,
    offlineNodes: nodes.filter((n) => n.status === 'offline').length,
    totalServices: orchestration.totalFleetServices,
    runningServices: orchestration.totalRunning,
    stoppedServices: orchestration.totalStopped,
    failedServices: orchestration.totalFailed,
  }
})

// =============================================================================
// Actions: Per-Node Control
// =============================================================================

async function handleServiceAction(
  nodeId: string,
  serviceName: string,
  action: 'start' | 'stop' | 'restart'
): Promise<void> {
  orchestration.setActiveAction(nodeId, serviceName, action)

  try {
    let result
    if (action === 'start') {
      result = await orchestration.startService(serviceName, { node_id: nodeId })
    } else if (action === 'stop') {
      result = await orchestration.stopService(serviceName, { node_id: nodeId })
    } else {
      result = await orchestration.restartService(serviceName, { node_id: nodeId })
    }

    if (result?.success) {
      logger.info(`${action} ${serviceName} on ${nodeId}: ${result.message}`)
      await orchestration.fetchFleetServices()
    }
  } catch (error) {
    logger.error(`Failed to ${action} ${serviceName}:`, error)
  } finally {
    orchestration.clearActiveAction()
  }
}

// Restart All Services on Node
const restartAllNodeId = ref<string | null>(null)
const restartAllHostname = ref<string | null>(null)
const showRestartAllConfirm = ref(false)

async function handleRestartAllServices(nodeId: string, hostname: string): Promise<void> {
  restartAllNodeId.value = nodeId
  restartAllHostname.value = hostname
  showRestartAllConfirm.value = true
}

async function confirmRestartAll(): Promise<void> {
  if (!restartAllNodeId.value) return
  showRestartAllConfirm.value = false

  // Note: This would call a per-node restart-all endpoint
  // For now, we'll restart each service individually
  const nodeGroup = servicesByNode.value.find((n) => n.nodeId === restartAllNodeId.value)
  if (nodeGroup) {
    for (const service of nodeGroup.services) {
      await handleServiceAction(restartAllNodeId.value, service.service_name, 'restart')
    }
  }

  restartAllNodeId.value = null
  restartAllHostname.value = null
}

function toggleNode(nodeId: string): void {
  if (expandedNodes.value.has(nodeId)) {
    expandedNodes.value.delete(nodeId)
  } else {
    expandedNodes.value.add(nodeId)
  }
}

function expandAll(): void {
  for (const node of servicesByNode.value) {
    expandedNodes.value.add(node.nodeId)
  }
}

function collapseAll(): void {
  expandedNodes.value.clear()
}

// =============================================================================
// Actions: Fleet Operations
// =============================================================================

async function handleFleetAction(
  serviceName: string,
  action: 'start' | 'stop' | 'restart'
): Promise<void> {
  try {
    let result
    if (action === 'start') {
      result = await orchestration.startFleetService(serviceName)
    } else if (action === 'stop') {
      result = await orchestration.stopFleetService(serviceName)
    } else {
      result = await orchestration.restartFleetService(serviceName)
    }

    if (result?.success) {
      logger.info(`Fleet ${action} ${serviceName}: ${result.message}`)
      await orchestration.fetchFleetServices()
    }
  } catch (error) {
    logger.error(`Failed to ${action} ${serviceName} fleet-wide:`, error)
  }
}

async function handleBulkAction(action: 'start' | 'stop' | 'restart'): Promise<void> {
  const confirmMsg = `Are you sure you want to ${action} ALL services across the entire fleet?`
  if (!confirm(confirmMsg)) return

  try {
    let result
    if (action === 'start') {
      result = await orchestration.startAllServices()
    } else if (action === 'stop') {
      result = await orchestration.stopAllServices()
    } else {
      result = await orchestration.restartAllServices()
    }

    if (result) {
      logger.info(`Bulk ${action}: ${result.success_count} succeeded, ${result.failure_count} failed`)
      await orchestration.fetchFleetServices()
      await orchestration.fetchFleetStatus()
    }
  } catch (error) {
    logger.error(`Failed bulk ${action}:`, error)
  }
}

// =============================================================================
// Actions: Roles & Deployment
// =============================================================================

function openCreateRoleForm(): void {
  editingRole.value = null
  roleFormData.value = {
    name: '',
    display_name: '',
    sync_type: 'component',
    source_paths: '',
    target_path: '/opt/autobot',
    systemd_service: '',
    auto_restart: false,
    health_check_port: '',
    health_check_path: '',
    pre_sync_cmd: '',
    post_sync_cmd: '',
  }
  showRoleForm.value = true
}

function openEditRoleForm(role: any): void {
  editingRole.value = role.name
  roleFormData.value = {
    name: role.name,
    display_name: role.display_name || '',
    sync_type: role.sync_type || 'component',
    source_paths: (role.source_paths || []).join(', '),
    target_path: role.target_path,
    systemd_service: role.systemd_service || '',
    auto_restart: role.auto_restart,
    health_check_port: role.health_check_port?.toString() || '',
    health_check_path: role.health_check_path || '',
    pre_sync_cmd: role.pre_sync_cmd || '',
    post_sync_cmd: role.post_sync_cmd || '',
  }
  showRoleForm.value = true
}

async function saveRole(): Promise<void> {
  const payload = {
    name: roleFormData.value.name,
    display_name: roleFormData.value.display_name || null,
    sync_type: roleFormData.value.sync_type,
    source_paths: roleFormData.value.source_paths
      ? roleFormData.value.source_paths.split(',').map((s) => s.trim()).filter(Boolean)
      : [],
    target_path: roleFormData.value.target_path,
    systemd_service: roleFormData.value.systemd_service || null,
    auto_restart: roleFormData.value.auto_restart,
    health_check_port: roleFormData.value.health_check_port
      ? parseInt(roleFormData.value.health_check_port)
      : null,
    health_check_path: roleFormData.value.health_check_path || null,
    pre_sync_cmd: roleFormData.value.pre_sync_cmd || null,
    post_sync_cmd: roleFormData.value.post_sync_cmd || null,
  }

  if (editingRole.value) {
    await roles.updateRole(editingRole.value, payload)
  } else {
    await roles.createRole(payload)
  }

  showRoleForm.value = false
  await roles.fetchRoles()
}

async function deleteRole(roleName: string): Promise<void> {
  if (!confirm(`Delete role "${roleName}"? This cannot be undone.`)) return
  await roles.deleteRole(roleName)
  await roles.fetchRoles()
}

// =============================================================================
// Actions: Migration (role-based)
// =============================================================================

function selectMigrationRole(role: Role): void {
  migrationRole.value = role
  migrationSourceNode.value = ''
  migrationTargetNode.value = ''
  migrationResult.value = null
}

function resetMigration(): void {
  migrationRole.value = null
  migrationSourceNode.value = ''
  migrationTargetNode.value = ''
  migrationRemoveFromSource.value = false
  migrationRestart.value = true
  migrationInProgress.value = false
  migrationResult.value = null
}

async function executeMigration(): Promise<void> {
  if (!migrationRole.value || !migrationTargetNode.value) return

  migrationInProgress.value = true
  migrationResult.value = null
  const roleName = migrationRole.value.name

  // Assign role to target node so sync picks it up
  const assigned = await roles.assignRole(migrationTargetNode.value, roleName)
  if (!assigned) {
    migrationResult.value = {
      success: false,
      message: roles.error || 'Failed to assign role to target node',
      details: [],
    }
    migrationInProgress.value = false
    return
  }

  // Sync role code to target node
  const syncResult = await roles.syncRole(roleName, [migrationTargetNode.value], migrationRestart.value)

  // Optionally remove role from source node
  if (syncResult.success && migrationRemoveFromSource.value && migrationSourceNode.value) {
    await roles.removeRole(migrationSourceNode.value, roleName)
  }

  migrationResult.value = {
    success: syncResult.success,
    message: syncResult.message,
    details: syncResult.results || [],
  }

  if (syncResult.success) {
    logger.info(`Role migration ${roleName} → ${migrationTargetNode.value}: success`)
    await Promise.allSettled([roles.fetchRoles(), orchestration.fetchFleetServices()])
  }

  migrationInProgress.value = false
}

// =============================================================================
// Lifecycle
// =============================================================================

async function refresh(): Promise<void> {
  try {
    // Use Promise.allSettled to continue even if some calls fail
    const results = await Promise.allSettled([
      orchestration.fetchFleetServices(),
      orchestration.fetchFleetStatus(),
      orchestration.fetchServiceDefinitions(),
      orchestration.fleetStore.fetchNodes(),
      roles.fetchRoles(),
    ])

    // Log any failures for debugging
    results.forEach((result, index) => {
      if (result.status === 'rejected') {
        const names = ['fleetServices', 'fleetStatus', 'serviceDefinitions', 'nodes', 'roles']
        logger.warn(`Failed to fetch ${names[index]}:`, result.reason)
      }
    })
  } catch (err) {
    logger.error('Unexpected error during refresh:', err)
  }
}

function toggleAutoRefresh(): void {
  autoRefresh.value = !autoRefresh.value
  if (autoRefresh.value) {
    refreshInterval = setInterval(refresh, 15000)
  } else if (refreshInterval) {
    clearInterval(refreshInterval)
    refreshInterval = null
  }
}

onMounted(async () => {
  logger.info('OrchestrationView mounted - checking auth')
  const token = localStorage.getItem('slm_access_token')
  logger.info('Auth token present:', !!token)
  if (!token) {
    logger.error('NO AUTH TOKEN - Please log in first')
    logger.error('Please navigate to /login to authenticate')
  }

  logger.info('Calling refresh()')
  await refresh()
  logger.info('After refresh:', {
    nodes: orchestration.fleetStore.nodeList.length,
    fleetServices: orchestration.fleetServices?.length || 0,
    serviceDefinitions: orchestration.serviceDefinitions?.length || 0,
    roles: roles.roles.length,
    fleetStoreError: orchestration.fleetStore.error,
    orchestrationError: orchestration.error,
    rolesError: roles.error,
    categoryFilter: categoryFilter.value,
  })

  // Log computed data for debugging
  logger.info('Computed data:', {
    servicesByNode: servicesByNode.value.length,
    categoryCounts: categoryCounts.value,
  })

  orchestration.initializeWebSocket((nodeId, data) => {
    logger.debug('Service status update:', nodeId, data.service_name, data.status)
    // Status updates are reflected via reactive state
  })

  if (autoRefresh.value) {
    refreshInterval = setInterval(refresh, 15000)
  }
})

onUnmounted(() => {
  if (refreshInterval) {
    clearInterval(refreshInterval)
  }
})
</script>

<template>
  <div class="p-6">
    <!-- Header -->
    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-2xl font-bold text-gray-900">Orchestration</h1>
        <p class="text-sm text-gray-500 mt-1">
          Unified service lifecycle management across the fleet
        </p>
      </div>
      <div class="flex items-center gap-3">
        <div class="flex items-center gap-1.5 text-sm">
          <span
            :class="[
              'w-2 h-2 rounded-full',
              orchestration.connected ? 'bg-green-500' : 'bg-gray-400'
            ]"
          ></span>
          <span :class="orchestration.connected ? 'text-green-600' : 'text-gray-500'">
            {{ orchestration.connected ? 'Live' : 'Offline' }}
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
          @click="refresh"
          :disabled="orchestration.loading"
          class="btn btn-secondary flex items-center gap-2"
        >
          <svg
            :class="['w-4 h-4', orchestration.loading ? 'animate-spin' : '']"
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

    <!-- ERROR DISPLAY -->
    <div v-if="orchestration.error" class="mb-4 p-4 bg-red-50 border border-red-200 rounded-lg">
      <div class="flex items-start gap-3">
        <svg class="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
          <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"/>
        </svg>
        <div class="flex-1">
          <h3 class="text-sm font-medium text-red-800">Error Loading Data</h3>
          <p class="mt-1 text-sm text-red-700">{{ orchestration.error }}</p>
          <button
            @click="refresh"
            class="mt-2 text-sm text-red-600 hover:text-red-800 underline"
          >
            Retry
          </button>
        </div>
      </div>
    </div>

    <!-- LOADING STATE -->
    <div v-if="orchestration.loading && !orchestration.fleetServices?.length" class="mb-4 p-8 bg-blue-50 border border-blue-200 rounded-lg text-center">
      <div class="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mb-3"></div>
      <p class="text-sm text-blue-700">Loading orchestration data...</p>
      <p class="text-xs text-blue-600 mt-1">Fetching services from {{ orchestration.fleetStore.nodeList.length }} nodes</p>
    </div>

    <!-- Tabs -->
    <div class="border-b border-gray-200 mb-6">
      <nav class="-mb-px flex gap-6">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          @click="navigateToTab(tab.id)"
          :class="[
            'py-3 px-1 border-b-2 font-medium text-sm whitespace-nowrap',
            activeTab === tab.id
              ? 'border-primary-500 text-primary-600'
              : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
          ]"
        >
          {{ tab.label }}
        </button>
      </nav>
    </div>

    <!-- Tab Content -->
    <div>
      <!-- Tab 1: Per-Node Control -->
      <div v-if="activeTab === 'per-node'">
        <!-- Filters -->
        <div class="card p-4 mb-4">
          <div class="flex flex-wrap items-center gap-4">
            <!-- Search -->
            <div class="flex-1 min-w-64">
              <input
                v-model="searchQuery"
                type="text"
                placeholder="Search services..."
                class="w-full px-3 py-2 border rounded-lg text-sm"
              />
            </div>

            <!-- Category Tabs -->
            <div class="flex items-center gap-2">
              <button
                @click="categoryFilter = 'autobot'"
                :class="[
                  'px-3 py-1.5 text-sm font-medium rounded-lg',
                  categoryFilter === 'autobot'
                    ? 'bg-primary-100 text-primary-700'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                ]"
              >
                AutoBot ({{ categoryCounts.autobot }})
              </button>
              <button
                @click="categoryFilter = 'system'"
                :class="[
                  'px-3 py-1.5 text-sm font-medium rounded-lg',
                  categoryFilter === 'system'
                    ? 'bg-primary-100 text-primary-700'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                ]"
              >
                System ({{ categoryCounts.system }})
              </button>
              <button
                @click="categoryFilter = 'all'"
                :class="[
                  'px-3 py-1.5 text-sm font-medium rounded-lg',
                  categoryFilter === 'all'
                    ? 'bg-primary-100 text-primary-700'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                ]"
              >
                All ({{ categoryCounts.all }})
              </button>
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

        <!-- Services by Node -->
        <div v-if="servicesByNode.length > 0" class="space-y-4">
          <div v-for="node in servicesByNode" :key="node.nodeId" class="card overflow-hidden">
            <NodeHealthCard
              :nodeId="node.nodeId"
              :hostname="node.hostname"
              :ipAddress="node.ipAddress"
              :status="node.status as any"
              :runningCount="node.runningCount"
              :stoppedCount="node.stoppedCount"
              :failedCount="node.failedCount"
              :totalServices="node.services.length"
              :isExpanded="expandedNodes.has(node.nodeId)"
              :showExpandIcon="true"
              :showRestartButton="true"
              @toggle="toggleNode"
              @restartAll="handleRestartAllServices"
            />

            <!-- Services List -->
            <div v-if="expandedNodes.has(node.nodeId)" class="border-t border-gray-100">
              <table class="w-full">
                <thead class="bg-gray-50">
                  <tr class="text-xs text-gray-500 uppercase">
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
                      <span
                        :class="[
                          'px-1.5 py-0.5 text-xs font-medium rounded',
                          service.category === 'autobot'
                            ? 'bg-blue-100 text-blue-700'
                            : 'bg-gray-100 text-gray-700'
                        ]"
                      >
                        {{ service.category === 'autobot' ? 'AutoBot' : 'System' }}
                      </span>
                    </td>
                    <td class="px-4 py-2">
                      <ServiceStatusBadge :status="service.status as any" />
                    </td>
                    <td class="px-4 py-2">
                      <ServiceActionButtons
                        :serviceName="service.service_name"
                        :nodeId="node.nodeId"
                        :status="service.status as any"
                        :isActionInProgress="orchestration.actionInProgress"
                        :activeAction="orchestration.activeAction"
                        @start="(nId, svc) => handleServiceAction(nId, svc, 'start')"
                        @stop="(nId, svc) => handleServiceAction(nId, svc, 'stop')"
                        @restart="(nId, svc) => handleServiceAction(nId, svc, 'restart')"
                      />
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
        <div v-else class="card p-12 text-center">
          <svg class="mx-auto h-12 w-12 text-gray-400 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
          </svg>
          <p class="text-gray-500 mb-2 font-medium">No services found</p>
          <p class="text-sm text-gray-400 mb-4">
            {{ orchestration.fleetStore.nodeList.length === 0
              ? 'No nodes are registered in the fleet. Add nodes to see services.'
              : orchestration.fleetServices?.length === 0
              ? 'No services are running on any nodes. Services will appear here when deployed.'
              : 'Try changing the filter or search criteria above.' }}
          </p>
          <button
            @click="refresh"
            class="px-4 py-2 text-sm bg-primary-100 text-primary-700 rounded-lg hover:bg-primary-200"
          >
            Refresh
          </button>
        </div>
      </div>

      <!-- Tab 2: Fleet Operations -->
      <div v-if="activeTab === 'fleet'" class="space-y-4">
        <!-- Fleet Actions -->
        <div class="card p-4">
          <h3 class="font-medium text-gray-900 mb-3">Fleet-Wide Actions</h3>
          <div class="flex items-center gap-3">
            <button
              @click="handleBulkAction('start')"
              :disabled="orchestration.loading"
              class="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50"
            >
              Start All Services
            </button>
            <button
              @click="handleBulkAction('stop')"
              :disabled="orchestration.loading"
              class="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50"
            >
              Stop All Services
            </button>
            <button
              @click="handleBulkAction('restart')"
              :disabled="orchestration.loading"
              class="px-4 py-2 bg-orange-600 text-white rounded-lg hover:bg-orange-700 disabled:opacity-50"
            >
              Restart All Services
            </button>
          </div>
        </div>

        <!-- Fleet Services Table -->
        <div class="card">
          <div class="px-4 py-3 bg-gray-50 border-b">
            <h3 class="font-medium text-gray-900">Fleet Services</h3>
          </div>
          <table class="w-full">
            <thead class="bg-gray-50">
              <tr class="text-xs text-gray-500 uppercase">
                <th class="px-4 py-2 text-left">Service</th>
                <th class="px-4 py-2 text-left">Category</th>
                <th class="px-4 py-2 text-center">Running</th>
                <th class="px-4 py-2 text-center">Stopped</th>
                <th class="px-4 py-2 text-center">Failed</th>
                <th class="px-4 py-2 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="service in filteredFleetServices"
                :key="service.service_name"
                class="border-t border-gray-50 hover:bg-gray-50"
              >
                <td class="px-4 py-2">
                  <span class="font-medium text-gray-900">{{ service.service_name }}</span>
                  <span class="text-xs text-gray-500 ml-2">({{ service.total_nodes }} nodes)</span>
                </td>
                <td class="px-4 py-2">
                  <span
                    :class="[
                      'px-1.5 py-0.5 text-xs font-medium rounded',
                      service.category === 'autobot'
                        ? 'bg-blue-100 text-blue-700'
                        : 'bg-gray-100 text-gray-700'
                    ]"
                  >
                    {{ service.category === 'autobot' ? 'AutoBot' : 'System' }}
                  </span>
                </td>
                <td class="px-4 py-2 text-center text-green-600 font-medium">
                  {{ service.running_count }}
                </td>
                <td class="px-4 py-2 text-center text-gray-500 font-medium">
                  {{ service.stopped_count }}
                </td>
                <td class="px-4 py-2 text-center text-red-600 font-medium">
                  {{ service.failed_count }}
                </td>
                <td class="px-4 py-2">
                  <div class="flex items-center justify-end gap-1">
                    <button
                      @click="handleFleetAction(service.service_name, 'start')"
                      class="px-2 py-1 text-xs bg-green-100 text-green-700 rounded hover:bg-green-200"
                      title="Start on all nodes"
                    >
                      Start
                    </button>
                    <button
                      @click="handleFleetAction(service.service_name, 'stop')"
                      class="px-2 py-1 text-xs bg-red-100 text-red-700 rounded hover:bg-red-200"
                      title="Stop on all nodes"
                    >
                      Stop
                    </button>
                    <button
                      @click="handleFleetAction(service.service_name, 'restart')"
                      class="px-2 py-1 text-xs bg-blue-100 text-blue-700 rounded hover:bg-blue-200"
                      title="Restart on all nodes"
                    >
                      Restart
                    </button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Tab 3: Roles & Deployment -->
      <div v-if="activeTab === 'roles'">
        <div class="mb-4">
          <button
            @click="openCreateRoleForm"
            class="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
          >
            Create Role
          </button>
        </div>

        <!-- Role Form -->
        <div v-if="showRoleForm" class="card mb-6">
          <div class="px-4 py-3 bg-gray-50 border-b flex items-center justify-between">
            <h3 class="font-medium text-gray-900">
              {{ editingRole ? `Edit Role: ${editingRole}` : 'Create Role' }}
            </h3>
            <button @click="showRoleForm = false" class="text-gray-400 hover:text-gray-600">
              &times;
            </button>
          </div>
          <form @submit.prevent="saveRole" class="p-4 space-y-4">
            <div class="grid grid-cols-2 gap-4">
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">Name *</label>
                <input
                  v-model="roleFormData.name"
                  :disabled="!!editingRole"
                  required
                  class="w-full px-3 py-2 border rounded-lg text-sm disabled:bg-gray-100"
                  placeholder="e.g. redis-server"
                />
              </div>
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">Display Name</label>
                <input
                  v-model="roleFormData.display_name"
                  class="w-full px-3 py-2 border rounded-lg text-sm"
                  placeholder="e.g. Redis Server"
                />
              </div>
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">Sync Type</label>
                <select v-model="roleFormData.sync_type" class="w-full px-3 py-2 border rounded-lg text-sm">
                  <option value="component">Component</option>
                  <option value="full">Full</option>
                  <option value="config">Config Only</option>
                </select>
              </div>
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">Target Path *</label>
                <input
                  v-model="roleFormData.target_path"
                  required
                  class="w-full px-3 py-2 border rounded-lg text-sm"
                  placeholder="/opt/autobot"
                />
              </div>
              <div class="col-span-2">
                <label class="block text-sm font-medium text-gray-700 mb-1"
                  >Source Paths (comma-separated)</label
                >
                <input
                  v-model="roleFormData.source_paths"
                  class="w-full px-3 py-2 border rounded-lg text-sm"
                  placeholder="autobot-slm-backend/, autobot-shared/"
                />
              </div>
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">Systemd Service</label>
                <input
                  v-model="roleFormData.systemd_service"
                  class="w-full px-3 py-2 border rounded-lg text-sm"
                  placeholder="autobot-slm.service"
                />
              </div>
              <div class="flex items-center gap-2 pt-6">
                <input
                  id="auto-restart"
                  type="checkbox"
                  v-model="roleFormData.auto_restart"
                  class="rounded"
                />
                <label for="auto-restart" class="text-sm text-gray-700"
                  >Auto Restart on Deploy</label
                >
              </div>
            </div>
            <div class="flex gap-2">
              <button type="submit" class="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm">
                {{ editingRole ? 'Update' : 'Create' }}
              </button>
              <button
                type="button"
                @click="showRoleForm = false"
                class="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 text-sm"
              >
                Cancel
              </button>
            </div>
          </form>
        </div>

        <!-- Roles Table -->
        <div class="card">
          <div class="px-4 py-3 bg-gray-50 border-b">
            <h3 class="font-medium text-gray-900">Registered Roles ({{ roles.roles.length }})</h3>
          </div>
          <table class="w-full">
            <thead class="bg-gray-50">
              <tr class="text-xs text-gray-500 uppercase">
                <th class="px-4 py-2 text-left">Name</th>
                <th class="px-4 py-2 text-left">Sync Type</th>
                <th class="px-4 py-2 text-left">Target</th>
                <th class="px-4 py-2 text-left">Service</th>
                <th class="px-4 py-2 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="role in roles.roles"
                :key="role.name"
                class="border-t border-gray-50 hover:bg-gray-50"
              >
                <td class="px-4 py-2">
                  <p class="text-sm font-medium text-gray-900">{{ role.display_name || role.name }}</p>
                  <p v-if="role.display_name" class="text-xs text-gray-500">{{ role.name }}</p>
                </td>
                <td class="px-4 py-2">
                  <span class="px-2 py-1 text-xs rounded-full bg-blue-100 text-blue-700">
                    {{ role.sync_type || 'component' }}
                  </span>
                </td>
                <td class="px-4 py-2 text-sm text-gray-600 font-mono">{{ role.target_path }}</td>
                <td class="px-4 py-2 text-sm text-gray-600">{{ role.systemd_service || '-' }}</td>
                <td class="px-4 py-2 text-right">
                  <button
                    @click="openEditRoleForm(role)"
                    class="px-2 py-1 text-xs bg-gray-100 text-gray-700 rounded hover:bg-gray-200 mr-1"
                  >
                    Edit
                  </button>
                  <button
                    @click="deleteRole(role.name)"
                    class="px-2 py-1 text-xs bg-red-100 text-red-700 rounded hover:bg-red-200"
                  >
                    Delete
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Tab 4: Migration (role-based) -->
      <div v-if="activeTab === 'migration'" class="space-y-4">
        <!-- Step 1: Select a role -->
        <div v-if="!migrationRole" class="card p-4">
          <h3 class="font-medium text-gray-900 mb-1">Role Migration</h3>
          <p class="text-sm text-gray-600 mb-4">
            Select an AutoBot role to migrate. A role consists of all code and services needed to
            provide a capability. The role will be synced to the target node and optionally removed
            from the source.
          </p>
          <div v-if="roles.roles.length === 0" class="text-sm text-gray-500 py-4 text-center">
            No roles defined. Create roles in the Roles &amp; Deployment tab first.
          </div>
          <div v-else class="grid grid-cols-2 gap-3">
            <button
              v-for="role in roles.roles"
              :key="role.name"
              @click="selectMigrationRole(role)"
              class="text-left border rounded-lg p-3 hover:border-blue-400 hover:bg-blue-50 transition-colors"
            >
              <div class="font-medium text-gray-900 text-sm">
                {{ role.display_name || role.name }}
              </div>
              <div class="text-xs text-gray-500 mt-1 truncate">
                {{ role.systemd_service || 'No systemd service' }}
              </div>
              <div class="flex items-center gap-2 mt-1">
                <span class="text-xs bg-gray-100 text-gray-600 rounded px-1.5 py-0.5">
                  {{ role.sync_type || 'full' }}
                </span>
                <span class="text-xs text-gray-400">
                  {{ role.source_paths.length }} source path(s)
                </span>
              </div>
            </button>
          </div>
        </div>

        <!-- Step 2: Configure migration -->
        <div v-if="migrationRole" class="card p-4">
          <div class="flex items-center justify-between mb-4">
            <h3 class="font-medium text-gray-900">
              Migrate: {{ migrationRole.display_name || migrationRole.name }}
            </h3>
            <button
              @click="resetMigration()"
              class="text-sm text-gray-500 hover:text-gray-700 underline"
            >
              Change role
            </button>
          </div>

          <!-- Role summary -->
          <div class="bg-gray-50 rounded-lg p-3 mb-4 text-sm grid grid-cols-2 gap-y-1">
            <div>
              <span class="text-gray-500">Service:</span>
              {{ migrationRole.systemd_service || 'None' }}
            </div>
            <div>
              <span class="text-gray-500">Sync type:</span>
              {{ migrationRole.sync_type || 'full' }}
            </div>
            <div>
              <span class="text-gray-500">Target path:</span>
              {{ migrationRole.target_path }}
            </div>
            <div>
              <span class="text-gray-500">Sources:</span>
              {{ migrationRole.source_paths.length }} path(s)
            </div>
          </div>

          <!-- Node selection -->
          <div class="space-y-3">
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">
                Source Node
                <span class="text-gray-400 font-normal">(optional — where role currently runs)</span>
              </label>
              <select
                v-model="migrationSourceNode"
                class="w-full px-3 py-2 border rounded-lg text-sm"
              >
                <option value="">Not currently assigned / skip</option>
                <option
                  v-for="node in orchestration.fleetStore.nodeList"
                  :key="node.node_id"
                  :value="node.node_id"
                >
                  {{ node.hostname }} ({{ node.ip_address }})
                </option>
              </select>
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">
                Target Node <span class="text-red-500">*</span>
              </label>
              <select
                v-model="migrationTargetNode"
                class="w-full px-3 py-2 border rounded-lg text-sm"
              >
                <option value="">Select target node...</option>
                <option
                  v-for="node in orchestration.fleetStore.nodeList"
                  :key="node.node_id"
                  :value="node.node_id"
                  :disabled="node.node_id === migrationSourceNode"
                >
                  {{ node.hostname }} ({{ node.ip_address }})
                </option>
              </select>
            </div>

            <!-- Options -->
            <div class="flex flex-col gap-2 pt-1">
              <label class="flex items-center gap-2 text-sm cursor-pointer">
                <input type="checkbox" v-model="migrationRestart" class="rounded" />
                <span>Restart services on target node after sync</span>
              </label>
              <label
                class="flex items-center gap-2 text-sm cursor-pointer"
                :class="!migrationSourceNode ? 'opacity-40' : ''"
              >
                <input
                  type="checkbox"
                  v-model="migrationRemoveFromSource"
                  :disabled="!migrationSourceNode"
                  class="rounded"
                />
                <span>Remove role assignment from source node after migration</span>
              </label>
            </div>

            <!-- Actions -->
            <div class="flex gap-2 pt-2">
              <button
                @click="executeMigration"
                :disabled="!migrationTargetNode || migrationInProgress"
                class="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {{ migrationInProgress ? 'Migrating...' : 'Execute Migration' }}
              </button>
              <button
                @click="resetMigration()"
                :disabled="migrationInProgress"
                class="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>

        <!-- Result -->
        <div
          v-if="migrationResult"
          class="card p-4"
          :class="migrationResult.success ? 'border-green-300 bg-green-50' : 'border-red-300 bg-red-50'"
        >
          <div
            class="flex items-center gap-2 font-medium mb-2"
            :class="migrationResult.success ? 'text-green-700' : 'text-red-700'"
          >
            <span>{{ migrationResult.success ? '✓' : '✗' }}</span>
            <span>{{ migrationResult.message }}</span>
          </div>
          <div v-if="migrationResult.details.length > 0" class="text-sm space-y-1 mt-2">
            <div
              v-for="detail in migrationResult.details"
              :key="detail.node_id"
              :class="detail.success ? 'text-green-600' : 'text-red-600'"
            >
              {{ detail.node_id }}: {{ detail.message }}
            </div>
          </div>
          <button
            v-if="migrationResult.success"
            @click="resetMigration()"
            class="mt-3 text-sm text-blue-600 hover:underline"
          >
            Migrate another role
          </button>
        </div>
      </div>

      <!-- Tab 5: Infrastructure Overview -->
      <div v-if="activeTab === 'infrastructure'" class="space-y-4">
        <!-- Stats Grid -->
        <div class="grid grid-cols-4 gap-4">
          <div class="card p-4">
            <p class="text-sm text-gray-500">Total Nodes</p>
            <p class="text-2xl font-bold text-gray-900 mt-1">{{ infrastructureStats.totalNodes }}</p>
            <p class="text-xs text-gray-500 mt-1">
              {{ infrastructureStats.onlineNodes }} online, {{ infrastructureStats.offlineNodes }} offline
            </p>
          </div>
          <div class="card p-4">
            <p class="text-sm text-gray-500">Total Services</p>
            <p class="text-2xl font-bold text-gray-900 mt-1">{{ infrastructureStats.totalServices }}</p>
          </div>
          <div class="card p-4">
            <p class="text-sm text-gray-500">Running</p>
            <p class="text-2xl font-bold text-green-600 mt-1">{{ infrastructureStats.runningServices }}</p>
          </div>
          <div class="card p-4">
            <p class="text-sm text-gray-500">Stopped/Failed</p>
            <p class="text-2xl font-bold text-red-600 mt-1">
              {{ infrastructureStats.stoppedServices + infrastructureStats.failedServices }}
            </p>
          </div>
        </div>

        <!-- Nodes List -->
        <div class="card">
          <div class="px-4 py-3 bg-gray-50 border-b">
            <h3 class="font-medium text-gray-900">Fleet Nodes</h3>
          </div>
          <table class="w-full">
            <thead class="bg-gray-50">
              <tr class="text-xs text-gray-500 uppercase">
                <th class="px-4 py-2 text-left">Node</th>
                <th class="px-4 py-2 text-left">IP Address</th>
                <th class="px-4 py-2 text-left">Status</th>
                <th class="px-4 py-2 text-left">Services</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="node in orchestration.fleetStore.nodeList"
                :key="node.node_id"
                class="border-t border-gray-50 hover:bg-gray-50"
              >
                <td class="px-4 py-2">
                  <span class="font-medium text-gray-900">{{ node.hostname }}</span>
                </td>
                <td class="px-4 py-2 text-sm text-gray-600 font-mono">{{ node.ip_address }}</td>
                <td class="px-4 py-2">
                  <ServiceStatusBadge :status="node.status as any" />
                </td>
                <td class="px-4 py-2 text-sm text-gray-600">
                  {{
                    orchestration.fleetServices.length > 0
                      ? orchestration.fleetServices.reduce(
                          (sum, svc) => sum + svc.nodes.filter((n) => n.node_id === node.node_id).length,
                          0
                        )
                      : 0
                  }}
                  services
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- Restart All Confirmation Dialog -->
    <RestartConfirmDialog
      :show="showRestartAllConfirm"
      title="Restart All Services"
      :message="`Are you sure you want to restart all services on <strong>${restartAllHostname}</strong>?<br><br>Services will be restarted sequentially.`"
      confirmButtonText="Restart All Services"
      @confirm="confirmRestartAll"
      @cancel="showRestartAllConfirm = false"
    />
  </div>
</template>
