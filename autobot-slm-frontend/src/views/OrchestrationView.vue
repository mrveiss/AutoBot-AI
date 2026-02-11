<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * OrchestrationView - Fleet-wide service orchestration management (Issue #838)
 *
 * Service definitions, fleet status, start/stop/restart, migration, bulk actions.
 * Consumes all 11 /api/orchestration/* endpoints.
 */

import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useOrchestration } from '@/composables/useOrchestration'
import { useFleetStore } from '@/stores/fleet'
import { createLogger } from '@/utils/debugUtils'
import type {
  ServiceDefinition,
  FleetServiceEntry,
  ServiceActionResponse,
  BulkActionResponse,
} from '@/composables/useOrchestration'

const logger = createLogger('OrchestrationView')
const orch = useOrchestration()
const fleetStore = useFleetStore()

// UI state
const activeTab = ref<'definitions' | 'status'>('definitions')
const showMigrateDialog = ref(false)
const migrateService = ref<string | null>(null)
const migrateSourceNode = ref('')
const migrateTargetNode = ref('')
const isMigrating = ref(false)
const actionInProgress = ref<string | null>(null)
const bulkInProgress = ref(false)
const successMessage = ref<string | null>(null)
const autoRefresh = ref(true)
let refreshTimer: ReturnType<typeof setInterval> | null = null

// Computed
const nodes = computed(() => fleetStore.nodeList)

const fleetServices = computed(() => {
  if (!orch.fleetStatus.value?.services) return []
  return Object.entries(orch.fleetStatus.value.services).map(
    ([name, entry]: [string, FleetServiceEntry]) => ({ name, ...entry })
  )
})

const healthySummary = computed(() => ({
  healthy: orch.healthyCount.value,
  unhealthy: orch.unhealthyCount.value,
  total: orch.totalFleetServices.value,
}))

// Lifecycle
onMounted(async () => {
  await Promise.all([orch.fetchServices(), orch.fetchFleetStatus()])
  startAutoRefresh()
})

onUnmounted(() => stopAutoRefresh())

// Auto-refresh
function startAutoRefresh(): void {
  stopAutoRefresh()
  if (autoRefresh.value) {
    refreshTimer = setInterval(() => orch.fetchFleetStatus(), 30000)
  }
}

function stopAutoRefresh(): void {
  if (refreshTimer) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
}

function toggleAutoRefresh(): void {
  autoRefresh.value = !autoRefresh.value
  startAutoRefresh()
}

// Service actions
async function handleServiceAction(
  serviceName: string,
  action: 'start' | 'stop' | 'restart'
): Promise<void> {
  actionInProgress.value = `${action}-${serviceName}`
  const handlers: Record<string, () => Promise<ServiceActionResponse | null>> = {
    start: () => orch.startService(serviceName),
    stop: () => orch.stopService(serviceName),
    restart: () => orch.restartService(serviceName),
  }
  const result = await handlers[action]()
  actionInProgress.value = null
  if (result?.success) {
    successMessage.value = `${action} ${serviceName}: ${result.message}`
    await orch.fetchFleetStatus()
    setTimeout(() => { successMessage.value = null }, 3000)
  }
}

// Migration
function openMigrateDialog(serviceName: string): void {
  migrateService.value = serviceName
  migrateSourceNode.value = ''
  migrateTargetNode.value = ''
  showMigrateDialog.value = true
}

async function executeMigration(): Promise<void> {
  if (!migrateService.value || !migrateSourceNode.value || !migrateTargetNode.value) return
  isMigrating.value = true
  const result = await orch.migrateService(migrateService.value, {
    source_node_id: migrateSourceNode.value,
    target_node_id: migrateTargetNode.value,
  })
  isMigrating.value = false
  showMigrateDialog.value = false
  if (result?.success) {
    successMessage.value = `Migrated ${migrateService.value}: ${result.message}`
    await orch.fetchFleetStatus()
    setTimeout(() => { successMessage.value = null }, 3000)
  }
}

// Bulk actions
async function handleBulkAction(action: 'start' | 'stop' | 'restart'): Promise<void> {
  if (!confirm(`${action.charAt(0).toUpperCase() + action.slice(1)} ALL services?`)) return
  bulkInProgress.value = true
  const handlers: Record<string, () => Promise<BulkActionResponse | null>> = {
    start: () => orch.startAllServices(),
    stop: () => orch.stopAllServices(),
    restart: () => orch.restartAllServices(),
  }
  const result = await handlers[action]()
  bulkInProgress.value = false
  if (result) {
    successMessage.value = `Bulk ${action}: ${result.success_count} ok, ${result.failure_count} failed`
    setTimeout(() => { successMessage.value = null }, 5000)
  }
}

function getStatusColor(s: string): string {
  if (s === 'running' || s === 'healthy') return 'text-green-600'
  if (s === 'stopped' || s === 'unhealthy') return 'text-red-600'
  return 'text-yellow-600'
}

function getStatusBg(s: string): string {
  if (s === 'running' || s === 'healthy') return 'bg-green-100 text-green-800'
  if (s === 'stopped' || s === 'unhealthy') return 'bg-red-100 text-red-800'
  return 'bg-yellow-100 text-yellow-800'
}
</script>

<template>
  <div class="p-6 max-w-7xl mx-auto">
    <!-- Header -->
    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-2xl font-bold text-gray-900">Service Orchestration</h1>
        <p class="text-sm text-gray-500 mt-1">
          Manage service definitions, fleet-wide actions, and cross-node migration
        </p>
      </div>
      <div class="flex items-center gap-3">
        <button
          @click="toggleAutoRefresh"
          :class="['px-3 py-1.5 text-sm rounded-lg border', autoRefresh ? 'bg-blue-50 border-blue-200 text-blue-700' : 'bg-gray-50 border-gray-200 text-gray-600']"
        >
          Auto-refresh: {{ autoRefresh ? 'ON' : 'OFF' }}
        </button>
        <button
          @click="Promise.all([orch.fetchServices(), orch.fetchFleetStatus()])"
          class="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
          :disabled="orch.loading.value"
        >
          Refresh
        </button>
      </div>
    </div>

    <!-- Alerts -->
    <div v-if="orch.error.value" class="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
      {{ orch.error.value }}
      <button @click="orch.clearError()" class="ml-2 underline">Dismiss</button>
    </div>
    <div v-if="successMessage" class="mb-4 p-3 bg-green-50 border border-green-200 rounded-lg text-green-700 text-sm">
      {{ successMessage }}
    </div>

    <!-- Fleet Summary -->
    <div class="grid grid-cols-3 gap-4 mb-6">
      <div class="bg-white rounded-lg border p-4">
        <p class="text-sm text-gray-500">Service Definitions</p>
        <p class="text-2xl font-bold">{{ orch.serviceCount.value }}</p>
      </div>
      <div class="bg-white rounded-lg border p-4">
        <p class="text-sm text-gray-500">Fleet Healthy</p>
        <p class="text-2xl font-bold text-green-600">{{ healthySummary.healthy }}</p>
      </div>
      <div class="bg-white rounded-lg border p-4">
        <p class="text-sm text-gray-500">Fleet Unhealthy</p>
        <p class="text-2xl font-bold text-red-600">{{ healthySummary.unhealthy }}</p>
      </div>
    </div>

    <!-- Bulk Actions -->
    <div class="mb-6 flex gap-3">
      <button
        @click="handleBulkAction('start')" :disabled="bulkInProgress"
        class="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50"
      >Start All</button>
      <button
        @click="handleBulkAction('stop')" :disabled="bulkInProgress"
        class="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50"
      >Stop All</button>
      <button
        @click="handleBulkAction('restart')" :disabled="bulkInProgress"
        class="px-4 py-2 bg-yellow-600 text-white rounded-lg hover:bg-yellow-700 disabled:opacity-50"
      >Restart All</button>
      <span v-if="bulkInProgress" class="text-sm text-gray-500 self-center">Processing...</span>
    </div>

    <!-- Tabs -->
    <div class="border-b mb-6">
      <nav class="flex gap-6">
        <button
          v-for="tab in [{ key: 'definitions', label: 'Service Definitions' }, { key: 'status', label: 'Fleet Status' }]"
          :key="tab.key"
          @click="activeTab = tab.key as 'definitions' | 'status'"
          :class="['pb-3 text-sm font-medium border-b-2 -mb-px', activeTab === tab.key ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700']"
        >{{ tab.label }}</button>
      </nav>
    </div>

    <!-- Loading -->
    <div v-if="orch.loading.value && !orch.services.value.length" class="text-center py-12 text-gray-500">
      Loading...
    </div>

    <!-- Service Definitions Tab -->
    <div v-else-if="activeTab === 'definitions'">
      <div class="bg-white rounded-lg border overflow-hidden">
        <table class="w-full">
          <thead class="bg-gray-50">
            <tr>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Name</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Type</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Default Host</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Port</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Health Check</th>
              <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Actions</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-200">
            <tr v-for="svc in orch.services.value" :key="svc.name" class="hover:bg-gray-50">
              <td class="px-4 py-3">
                <p class="font-medium text-gray-900">{{ svc.name }}</p>
                <p class="text-xs text-gray-500">{{ svc.description }}</p>
              </td>
              <td class="px-4 py-3 text-sm text-gray-600">{{ svc.service_type }}</td>
              <td class="px-4 py-3 text-sm font-mono text-gray-600">{{ svc.default_host }}</td>
              <td class="px-4 py-3 text-sm font-mono text-gray-600">{{ svc.default_port }}</td>
              <td class="px-4 py-3 text-sm text-gray-600">{{ svc.health_check_type }}</td>
              <td class="px-4 py-3 text-right">
                <div class="flex gap-1 justify-end">
                  <button
                    @click="handleServiceAction(svc.name, 'start')"
                    :disabled="actionInProgress !== null"
                    class="px-2 py-1 text-xs bg-green-100 text-green-700 rounded hover:bg-green-200 disabled:opacity-50"
                  >Start</button>
                  <button
                    @click="handleServiceAction(svc.name, 'stop')"
                    :disabled="actionInProgress !== null"
                    class="px-2 py-1 text-xs bg-red-100 text-red-700 rounded hover:bg-red-200 disabled:opacity-50"
                  >Stop</button>
                  <button
                    @click="handleServiceAction(svc.name, 'restart')"
                    :disabled="actionInProgress !== null"
                    class="px-2 py-1 text-xs bg-yellow-100 text-yellow-700 rounded hover:bg-yellow-200 disabled:opacity-50"
                  >Restart</button>
                  <button
                    @click="openMigrateDialog(svc.name)"
                    class="px-2 py-1 text-xs bg-purple-100 text-purple-700 rounded hover:bg-purple-200"
                  >Migrate</button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-if="!orch.services.value.length" class="p-8 text-center text-gray-500">
          No service definitions found
        </div>
      </div>
    </div>

    <!-- Fleet Status Tab -->
    <div v-else-if="activeTab === 'status'">
      <div class="bg-white rounded-lg border overflow-hidden">
        <table class="w-full">
          <thead class="bg-gray-50">
            <tr>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Service</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Host</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Port</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Message</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-200">
            <tr v-for="svc in fleetServices" :key="svc.name" class="hover:bg-gray-50">
              <td class="px-4 py-3 font-medium text-gray-900">{{ svc.name }}</td>
              <td class="px-4 py-3">
                <span :class="['px-2 py-1 text-xs font-medium rounded-full', getStatusBg(svc.status)]">
                  {{ svc.status }}
                </span>
              </td>
              <td class="px-4 py-3 text-sm font-mono text-gray-600">{{ svc.host }}</td>
              <td class="px-4 py-3 text-sm font-mono text-gray-600">{{ svc.port }}</td>
              <td class="px-4 py-3 text-sm text-gray-500">{{ svc.message }}</td>
            </tr>
          </tbody>
        </table>
        <div v-if="!fleetServices.length" class="p-8 text-center text-gray-500">
          No fleet status data available
        </div>
        <div v-if="orch.fleetStatus.value?.timestamp" class="px-4 py-2 bg-gray-50 text-xs text-gray-500 border-t">
          Last updated: {{ new Date(orch.fleetStatus.value.timestamp).toLocaleString() }}
        </div>
      </div>
    </div>

    <!-- Migrate Dialog -->
    <div v-if="showMigrateDialog" class="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div class="bg-white rounded-xl shadow-xl w-full max-w-md p-6">
        <h3 class="text-lg font-bold mb-4">Migrate Service: {{ migrateService }}</h3>
        <div class="space-y-4">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Source Node</label>
            <select v-model="migrateSourceNode" class="w-full border rounded-lg px-3 py-2 text-sm">
              <option value="">Select source node...</option>
              <option v-for="node in nodes" :key="node.id" :value="node.id">
                {{ node.hostname || node.id }} ({{ node.ip_address }})
              </option>
            </select>
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Target Node</label>
            <select v-model="migrateTargetNode" class="w-full border rounded-lg px-3 py-2 text-sm">
              <option value="">Select target node...</option>
              <option
                v-for="node in nodes"
                :key="node.id"
                :value="node.id"
                :disabled="node.id === migrateSourceNode"
              >
                {{ node.hostname || node.id }} ({{ node.ip_address }})
              </option>
            </select>
          </div>
        </div>
        <div class="flex justify-end gap-3 mt-6">
          <button @click="showMigrateDialog = false" class="px-4 py-2 text-sm text-gray-700 border rounded-lg hover:bg-gray-50">
            Cancel
          </button>
          <button
            @click="executeMigration"
            :disabled="!migrateSourceNode || !migrateTargetNode || isMigrating"
            class="px-4 py-2 text-sm bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50"
          >
            {{ isMigrating ? 'Migrating...' : 'Migrate' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
