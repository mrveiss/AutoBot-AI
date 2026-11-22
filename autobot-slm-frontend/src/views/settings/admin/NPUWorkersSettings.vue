// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

<script setup lang="ts">
/**
 * NPUWorkersSettings - NPU Worker Management (#729).
 * Provides management of distributed NPU workers for AI processing.
 */

import { ref, reactive, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAutobotApi, type NPUWorker } from '@/composables/useAutobotApi'
import { throwUnlessLoaded, useDashboardPoller } from '@/composables/useDashboardPoller'
import { BaseAlert, BaseModal, PollingPausedAlert, createLogger } from '@autobot/ui'
import NPUAssignedWorkersPanel from './NPUAssignedWorkersPanel.vue'

const logger = createLogger('NPUWorkersSettings')

const api = useAutobotApi()
const { t } = useI18n()

// Workers serve plain HTTP: the scheme autobot_shared/network_constants.py builds NPU_WORKER_SERVICE with.
// An edited worker keeps the scheme it was paired with.
const NEW_WORKER_SCHEME = 'http:'
const DEFAULT_PORTS: Record<string, number> = { 'http:': 80, 'https:': 443 }

// State
const loading = ref(false)
const saving = ref(false)
const error = ref<string | null>(null)
const success = ref<string | null>(null)
const testingWorker = ref<Record<string, boolean>>({})

// Workers data
const workers = ref<NPUWorker[]>([])

// Load balancing config
const loadBalancingConfig = reactive({
  strategy: 'round-robin',
  health_check_interval: 30,
  max_retries: 3,
  retry_delay: 5,
})

// Modal state
const showModal = ref(false)
const editingWorker = ref<NPUWorker | null>(null)
const deleteTarget = ref<NPUWorker | null>(null)

// Form data
const workerForm = reactive({
  name: '',
  platform: 'linux',
  ip_address: '',
  port: 8081,
  enabled: true,
  priority: 1,
  weight: 1,
})

// Metrics modal
const showMetrics = ref(false)
const selectedWorkerMetrics = ref<NPUWorker | null>(null)


// Computed
const healthyWorkers = computed(() =>
  workers.value.filter(w => w.status === 'online').length
)

const busyWorkers = computed(() =>
  workers.value.filter(w => w.status === 'busy').length
)

const offlineWorkers = computed(() =>
  workers.value.filter(w => w.status === 'offline' || w.status === 'error').length
)

// Methods
async function fetchWorkers(): Promise<boolean> {
  loading.value = true
  error.value = null

  try {
    workers.value = await api.getNPUWorkers()
    return true
  } catch (e) {
    error.value = e instanceof Error ? e.message : t('settings.admin.nPUWorkersSettings.failedToLoadWorkers')
    return false
  } finally {
    loading.value = false
  }
}

// Saving before the config loaded would overwrite the server's settings with
// the form's defaults (#17971 review), so Save waits for a successful fetch.
const loadBalancingConfigLoaded = ref(false)

async function fetchLoadBalancingConfig(): Promise<void> {
  try {
    const response = await api.getNPULoadBalancingConfig()
    if (response) {
      Object.assign(loadBalancingConfig, response)
    }
    loadBalancingConfigLoaded.value = true
  } catch (e) {
    // GET /api/npu/load-balancing is served (#15536): a failure is a real error, so say so.
    // Save stays disabled, because saving the form's defaults would overwrite the server's settings.
    loadBalancingConfigLoaded.value = false
    error.value = e instanceof Error ? e.message : t('settings.admin.nPUWorkersSettings.loadBalancingLoadFailed')
    logger.error('NPU load-balancing config failed to load:', e)
  }
}

async function saveLoadBalancingConfig(): Promise<void> {
  if (!loadBalancingConfigLoaded.value) return
  saving.value = true
  error.value = null

  try {
    await api.updateNPULoadBalancingConfig(loadBalancingConfig)
    success.value = t('settings.admin.nPUWorkersSettings.loadBalancingSaved')
    setTimeout(() => { success.value = null }, 3000)
  } catch (e) {
    error.value = e instanceof Error ? e.message : t('settings.admin.nPUWorkersSettings.failedToSaveConfiguration')
  } finally {
    saving.value = false
  }
}

function openAddModal(): void {
  editingWorker.value = null
  resetForm()
  showModal.value = true
}

function openEditModal(worker: NPUWorker): void {
  editingWorker.value = worker
  const url = new URL(worker.definition.url)
  workerForm.name = worker.definition.name
  workerForm.ip_address = url.hostname
  // URL elides a scheme's default port, so an empty port means that default, not the form's 8081.
  workerForm.port = Number(url.port) || DEFAULT_PORTS[url.protocol] || workerForm.port
  workerForm.platform = worker.definition.platform
  workerForm.enabled = worker.definition.enabled
  workerForm.priority = worker.definition.priority
  workerForm.weight = worker.definition.weight
  showModal.value = true
}

function resetForm(): void {
  workerForm.name = ''
  workerForm.platform = 'linux'
  workerForm.ip_address = ''
  workerForm.port = 8081
  workerForm.enabled = true
  workerForm.priority = 1
  workerForm.weight = 1
}

function closeModal(): void {
  showModal.value = false
  editingWorker.value = null
  resetForm()
}

async function saveWorker(): Promise<void> {
  saving.value = true
  error.value = null

  try {
    const endpoint = new URL(editingWorker.value?.definition.url ?? `${NEW_WORKER_SCHEME}//placeholder`)
    endpoint.hostname = workerForm.ip_address
    endpoint.port = String(workerForm.port)
    // `host` elides a default port again, so an unchanged worker keeps the URL it was paired with.
    const url = `${endpoint.protocol}//${endpoint.host}`
    if (editingWorker.value) {
      await api.updateNPUWorker(editingWorker.value.id, {
        name: workerForm.name,
        url,
        platform: workerForm.platform,
        enabled: workerForm.enabled,
        priority: workerForm.priority,
        weight: workerForm.weight,
      })
    } else {
      await api.pairNPUWorker({ url, name: workerForm.name, enabled: workerForm.enabled })
    }

    success.value = t(editingWorker.value ? 'settings.admin.nPUWorkersSettings.workerUpdated' : 'settings.admin.nPUWorkersSettings.workerPaired')
    closeModal()
    await fetchWorkers()
    setTimeout(() => { success.value = null }, 3000)
  } catch (e) {
    error.value = e instanceof Error ? e.message : t('settings.admin.nPUWorkersSettings.failedToSaveWorker')
  } finally {
    saving.value = false
  }
}

async function testWorker(worker: NPUWorker): Promise<void> {
  testingWorker.value[worker.id] = true
  error.value = null

  try {
    const result = await api.testNPUWorker(worker.id)
    if (!result.success) {
      error.value = result.error_message || t('settings.admin.nPUWorkersSettings.connectionTestFailed')
      return
    }
    success.value = t('settings.admin.nPUWorkersSettings.connectionSuccessful', { hostname: worker.hostname })
    setTimeout(() => { success.value = null }, 3000)
  } catch (e) {
    error.value = e instanceof Error ? e.message : t('settings.admin.nPUWorkersSettings.connectionTestFailed')
  } finally {
    testingWorker.value[worker.id] = false
  }
}

// Restart returns with its route (#18725): no backend restarts an NPU worker yet.

function confirmDelete(worker: NPUWorker): void {
  deleteTarget.value = worker
}

async function deleteWorker(): Promise<void> {
  if (!deleteTarget.value) return

  saving.value = true
  error.value = null

  try {
    await api.removeNPUWorker(deleteTarget.value.id)
    success.value = t('settings.admin.nPUWorkersSettings.workerRemoved')
    deleteTarget.value = null
    await fetchWorkers()
    setTimeout(() => { success.value = null }, 3000)
  } catch (e) {
    error.value = e instanceof Error ? e.message : t('settings.admin.nPUWorkersSettings.failedToRemoveWorker')
  } finally {
    saving.value = false
  }
}

function viewMetrics(worker: NPUWorker): void {
  selectedWorkerMetrics.value = worker
  showMetrics.value = true
}

function getStatusColor(status: string): string {
  switch (status) {
    case 'online': return 'bg-autobot-pill-ok-bg text-autobot-pill-ok-fg'
    case 'busy': return 'bg-autobot-pill-warn-bg text-autobot-pill-warn-fg'
    case 'offline': return 'bg-autobot-bg-tertiary text-autobot-text-secondary'
    case 'error': return 'bg-autobot-pill-bad-bg text-autobot-pill-bad-fg'
    default: return 'bg-autobot-bg-tertiary text-autobot-text-secondary'
  }
}

function getStatusDot(status: string): string {
  switch (status) {
    case 'online': return 'bg-autobot-dot-ok'
    case 'busy': return 'bg-autobot-dot-warn'
    case 'offline': return 'bg-autobot-dot-idle'
    case 'error': return 'bg-autobot-dot-bad'
    default: return 'bg-autobot-dot-idle'
  }
}

function getLoadColor(load: number): string {
  if (load < 50) return 'bg-autobot-dot-ok'
  if (load < 80) return 'bg-autobot-dot-warn'
  return 'bg-autobot-dot-bad'
}

// #19482: shared dashboard policy; fetchWorkers() is false on a failed read, which the poller counts
const workersPoller = useDashboardPoller(async () => {
  throwUnlessLoaded(await fetchWorkers())
}, 30000)
onMounted(() => {
  void fetchLoadBalancingConfig()
  workersPoller.start('')
})
</script>

<template>
  <div class="p-6 space-y-6">
    <!-- Messages -->
    <PollingPausedAlert :poller="workersPoller" :message="t('common.polling.paused')" :retry-label="t('common.polling.retry')" @retry="workersPoller.start('')" />
    <BaseAlert v-if="error" variant="error" :message="error" dismissible :dismiss-label="$t('settings.admin.nPUWorkersSettings.dismissError')" @dismiss="error = null" />

    <BaseAlert v-if="success" variant="success" :message="success" />

    <!-- Header -->
    <div class="bg-white rounded-lg shadow-xs border border-autobot-border p-6">
      <div class="flex items-center justify-between mb-6">
        <div>
          <h2 class="text-lg font-semibold text-autobot-text-primary">{{ $t('settings.admin.nPUWorkersSettings.nPUWorkerManagement') }}</h2>
          <p class="text-sm text-autobot-text-tertiary mt-1">{{ $t('settings.admin.nPUWorkersSettings.manageDistributedNPUWorkers') }}</p>
        </div>
        <button
          @click="openAddModal"
          class="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 flex items-center gap-2"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
          </svg>
          {{ $t('settings.admin.nPUWorkersSettings.pairWorker') }}
        </button>
      </div>

      <NPUAssignedWorkersPanel @paired="fetchWorkers" />
      <!-- Stats Grid -->
      <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div class="p-4 bg-autobot-bg-secondary rounded-lg text-center">
          <p class="text-2xl font-bold text-autobot-text-primary">{{ workers.length }}</p>
          <p class="text-sm text-autobot-text-tertiary">{{ $t('settings.admin.nPUWorkersSettings.totalWorkers') }}</p>
        </div>
        <div class="p-4 bg-autobot-success-bg rounded-lg text-center">
          <p class="text-2xl font-bold text-autobot-success">{{ healthyWorkers }}</p>
          <p class="text-sm text-autobot-text-tertiary">{{ $t('settings.admin.nPUWorkersSettings.online') }}</p>
        </div>
        <div class="p-4 bg-autobot-warning-bg rounded-lg text-center">
          <p class="text-2xl font-bold text-autobot-warning">{{ busyWorkers }}</p>
          <p class="text-sm text-autobot-text-tertiary">{{ $t('settings.admin.nPUWorkersSettings.busy') }}</p>
        </div>
        <div class="p-4 bg-autobot-error-bg rounded-lg text-center">
          <p class="text-2xl font-bold text-autobot-error">{{ offlineWorkers }}</p>
          <p class="text-sm text-autobot-text-tertiary">{{ $t('settings.admin.nPUWorkersSettings.offline') }}</p>
        </div>
      </div>
    </div>

    <!-- Load Balancing Configuration -->
    <div class="bg-white rounded-lg shadow-xs border border-autobot-border p-6">
      <h3 class="font-semibold text-autobot-text-primary mb-4 flex items-center gap-2">
        <svg class="w-5 h-5 text-autobot-text-tertiary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 6l3 1m0 0l-3 9a5.002 5.002 0 006.001 0M6 7l3 9M6 7l6-2m6 2l3-1m-3 1l-3 9a5.002 5.002 0 006.001 0M18 7l3 9m-3-9l-6-2m0-2v2m0 16V5m0 16H9m3 0h3" />
        </svg>
        {{ $t('settings.admin.nPUWorkersSettings.loadBalancingConfiguration') }}
      </h3>

      <div class="grid md:grid-cols-2 gap-6">
        <div>
          <label class="block text-sm font-medium text-autobot-text-secondary mb-1">{{ $t('settings.admin.nPUWorkersSettings.strategy') }}</label>
          <select
            v-model="loadBalancingConfig.strategy"
            class="w-full px-3 py-2 border border-autobot-border-strong rounded-lg focus:ring-2 focus:ring-primary-500"
          >
            <option value="round-robin">{{ $t('settings.admin.nPUWorkersSettings.roundRobin') }}</option>
            <option value="least-loaded">{{ $t('settings.admin.nPUWorkersSettings.leastLoaded') }}</option>
            <option value="weighted">{{ $t('settings.admin.nPUWorkersSettings.weighted') }}</option>
            <option value="priority">{{ $t('settings.admin.nPUWorkersSettings.priorityBased') }}</option>
          </select>
          <p class="text-xs text-autobot-text-tertiary mt-1">{{ $t('settings.admin.nPUWorkersSettings.distributionStrategyForTask') }}</p>
        </div>

        <div>
          <label class="block text-sm font-medium text-autobot-text-secondary mb-1">{{ $t('settings.admin.nPUWorkersSettings.healthCheckIntervalSeconds') }}</label>
          <input
            v-model.number="loadBalancingConfig.health_check_interval"
            type="number"
            min="5"
            max="300"
            class="w-full px-3 py-2 border border-autobot-border-strong rounded-lg focus:ring-2 focus:ring-primary-500"
          />
          <p class="text-xs text-autobot-text-tertiary mt-1">{{ $t('settings.admin.nPUWorkersSettings.secondsBetweenHealthChecks') }}</p>
        </div>
      </div>

      <div class="mt-4 flex justify-end">
        <button
          @click="saveLoadBalancingConfig"
          :disabled="saving || !loadBalancingConfigLoaded"
          class="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50 flex items-center gap-2"
        >
          <svg v-if="saving" class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          <svg v-else class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
          </svg>
          {{ $t('settings.admin.nPUWorkersSettings.saveConfiguration') }}
        </button>
      </div>
    </div>

    <!-- Workers List -->
    <div class="bg-white rounded-lg shadow-xs border border-autobot-border overflow-hidden">
      <div class="p-4 bg-autobot-bg-secondary border-b border-autobot-border flex items-center justify-between">
        <h3 class="font-semibold text-autobot-text-primary">{{ $t('settings.admin.nPUWorkersSettings.registeredWorkersCount', { count: workers.length }) }}</h3>
        <button
          @click="workersPoller.start('')"
          :disabled="loading"
          class="p-2 text-autobot-text-tertiary hover:text-autobot-text-secondary hover:bg-autobot-bg-hover rounded-sm"
          :aria-label="$t('settings.admin.nPUWorkersSettings.refreshWorkers')"
        >
          <svg :class="['w-5 h-5', loading && 'animate-spin']" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
        </button>
      </div>

      <!-- Loading -->
      <div v-if="loading && workers.length === 0" class="flex items-center justify-center py-12">
        <svg class="animate-spin w-8 h-8 text-primary-600" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
      </div>

      <!-- Empty State -->
      <div v-else-if="workers.length === 0" class="p-8 text-center">
        <svg class="w-12 h-12 text-autobot-text-tertiary mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01" />
        </svg>
        <p class="text-autobot-text-tertiary mb-4">{{ $t('settings.admin.nPUWorkersSettings.noNPUWorkersRegistered') }}</p>
        <button
          @click="openAddModal"
          class="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700"
        >
          {{ $t('settings.admin.nPUWorkersSettings.pairYourFirstWorker') }}
        </button>
      </div>

      <!-- Workers Table -->
      <div v-else class="overflow-x-auto">
        <table class="w-full">
          <thead>
            <tr class="border-b border-autobot-border bg-autobot-bg-secondary">
              <th class="text-left py-3 px-4 text-sm font-medium text-autobot-text-tertiary">{{ $t('settings.admin.nPUWorkersSettings.worker') }}</th>
              <th class="text-left py-3 px-4 text-sm font-medium text-autobot-text-tertiary">{{ $t('settings.admin.nPUWorkersSettings.status') }}</th>
              <th class="text-left py-3 px-4 text-sm font-medium text-autobot-text-tertiary">{{ $t('settings.admin.nPUWorkersSettings.load') }}</th>
              <th class="text-left py-3 px-4 text-sm font-medium text-autobot-text-tertiary">{{ $t('settings.admin.nPUWorkersSettings.capabilities') }}</th>
              <th class="text-left py-3 px-4 text-sm font-medium text-autobot-text-tertiary">{{ $t('settings.admin.nPUWorkersSettings.lastHeartbeat') }}</th>
              <th class="text-right py-3 px-4 text-sm font-medium text-autobot-text-tertiary">{{ $t('settings.admin.nPUWorkersSettings.actions') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="worker in workers" :key="worker.id" class="border-b border-autobot-border-subtle hover:bg-autobot-bg-hover">
              <!-- Worker Info -->
              <td class="py-3 px-4">
                <div>
                  <p class="font-medium text-autobot-text-primary">{{ worker.hostname }}</p>
                  <p class="text-sm text-autobot-text-tertiary">{{ worker.ip_address }}</p>
                </div>
              </td>

              <!-- Status -->
              <td class="py-3 px-4">
                <span
                  :class="[
                    'inline-flex items-center gap-1.5 px-2 py-1 rounded-full text-xs font-medium',
                    getStatusColor(worker.status),
                  ]"
                >
                  <span :class="['w-2 h-2 rounded-full', getStatusDot(worker.status)]"></span>
                  {{ worker.status }}
                </span>
              </td>

              <!-- Load -->
              <td class="py-3 px-4">
                <div class="w-24">
                  <div class="flex items-center gap-2">
                    <div class="flex-1 bg-autobot-bg-active rounded-full h-2">
                      <div
                        :class="['h-2 rounded-full', getLoadColor(worker.current_load)]"
                        :style="{ width: worker.current_load + '%' }"
                      ></div>
                    </div>
                    <span class="text-sm text-autobot-text-secondary">{{ worker.current_load }}%</span>
                  </div>
                </div>
              </td>

              <!-- Capabilities -->
              <td class="py-3 px-4">
                <div class="flex flex-wrap gap-1">
                  <span
                    v-for="cap in worker.capabilities?.slice(0, 3)"
                    :key="cap"
                    class="px-2 py-0.5 bg-autobot-bg-tertiary text-autobot-text-secondary rounded-sm text-xs"
                  >
                    {{ cap }}
                  </span>
                  <span
                    v-if="(worker.capabilities?.length || 0) > 3"
                    class="px-2 py-0.5 bg-autobot-bg-tertiary text-autobot-text-secondary rounded-sm text-xs"
                  >
                    +{{ (worker.capabilities?.length || 0) - 3 }}
                  </span>
                </div>
              </td>

              <!-- Last Heartbeat -->
              <td class="py-3 px-4 text-sm text-autobot-text-secondary">
                {{ worker.last_heartbeat || $t('settings.admin.nPUWorkersSettings.never') }}
              </td>

              <!-- Actions -->
              <td class="py-3 px-4">
                <div class="flex items-center justify-end gap-1">
                  <button
                    @click="testWorker(worker)"
                    :disabled="testingWorker[worker.id]"
                    class="p-2 text-autobot-text-tertiary hover:text-autobot-text-link hover:bg-autobot-info-bg rounded-sm disabled:opacity-50"
                    :title="$t('settings.admin.nPUWorkersSettings.testConnection')"
                  >
                    <svg v-if="testingWorker[worker.id]" class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                      <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                      <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                    <svg v-else class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
                    </svg>
                  </button>
                  <button
                    @click="viewMetrics(worker)"
                    class="p-2 text-autobot-text-tertiary hover:text-primary-500 hover:bg-primary-50 rounded-sm"
                    :title="$t('settings.admin.nPUWorkersSettings.viewMetrics')"
                  >
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                    </svg>
                  </button>
                  <!-- Restart returns with its route (#18725). -->
                  <button
                    @click="openEditModal(worker)"
                    class="p-2 text-autobot-text-tertiary hover:text-primary-500 hover:bg-primary-50 rounded-sm"
                    :title="$t('settings.admin.nPUWorkersSettings.edit')"
                  >
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                    </svg>
                  </button>
                  <button
                    @click="confirmDelete(worker)"
                    class="p-2 text-autobot-text-tertiary hover:text-autobot-error hover:bg-autobot-error-bg rounded-sm"
                    :title="$t('settings.admin.nPUWorkersSettings.remove')"
                  >
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Add/Edit Worker Modal -->
    <BaseModal
      :close-on-esc="!saving"
      v-model="showModal"
      :title="editingWorker ? $t('settings.admin.nPUWorkersSettings.editWorker') : $t('settings.admin.nPUWorkersSettings.pairNewWorker')"
      size="sm"
      :close-label="$t('settings.admin.nPUWorkersSettings.close')"
      @close="closeModal"
    >
      <div class="space-y-4">
        <div>
          <label class="block text-sm font-medium text-autobot-text-secondary mb-1">{{ $t('settings.admin.nPUWorkersSettings.workerName') }}</label>
          <input
            v-model="workerForm.name"
            type="text"
            class="w-full px-3 py-2 border border-autobot-border-strong rounded-lg focus:ring-2 focus:ring-primary-500"
            :placeholder="$t('settings.admin.nPUWorkersSettings.eGNPUWorkerVM2')"
          />
        </div>

        <div class="grid grid-cols-2 gap-4">
          <div>
            <label class="block text-sm font-medium text-autobot-text-secondary mb-1">{{ $t('settings.admin.nPUWorkersSettings.platform') }}</label>
            <select
              v-model="workerForm.platform"
              class="w-full px-3 py-2 border border-autobot-border-strong rounded-lg focus:ring-2 focus:ring-primary-500"
            >
              <option value="linux">{{ $t('settings.admin.nPUWorkersSettings.linux') }}</option>
              <option value="windows">{{ $t('settings.admin.nPUWorkersSettings.windows') }}</option>
              <option value="macos">{{ $t('settings.admin.nPUWorkersSettings.macOS') }}</option>
            </select>
          </div>
          <div>
            <label class="block text-sm font-medium text-autobot-text-secondary mb-1">{{ $t('settings.admin.nPUWorkersSettings.port') }}</label>
            <input
              v-model.number="workerForm.port"
              type="number"
              class="w-full px-3 py-2 border border-autobot-border-strong rounded-lg focus:ring-2 focus:ring-primary-500"
              placeholder="8081"
            />
          </div>
        </div>

        <div>
          <label class="block text-sm font-medium text-autobot-text-secondary mb-1">{{ $t('settings.admin.nPUWorkersSettings.iPAddress') }}</label>
          <input
            v-model="workerForm.ip_address"
            type="text"
            class="w-full px-3 py-2 border border-autobot-border-strong rounded-lg focus:ring-2 focus:ring-primary-500"
            placeholder="10.0.0.22"
          />
        </div>
      </div>
      <template #actions>
        <button
          @click="closeModal"
          class="px-4 py-2 bg-autobot-bg-tertiary text-autobot-text-secondary rounded-lg hover:bg-autobot-bg-active"
        >
          {{ $t('settings.admin.nPUWorkersSettings.cancel') }}
        </button>
        <button
          @click="saveWorker"
          :disabled="saving"
          class="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50 flex items-center gap-2"
        >
          <svg v-if="saving" class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          {{ editingWorker ? $t('settings.admin.nPUWorkersSettings.update') : $t('settings.admin.nPUWorkersSettings.pairWorker') }}
        </button>
      </template>
    </BaseModal>

    <!-- Delete Confirmation -->
    <BaseModal
      :close-on-esc="!saving"
      v-if="deleteTarget"
      :model-value="true"
      :title="$t('settings.admin.nPUWorkersSettings.removeWorker')"
      size="sm"
      :close-label="$t('settings.admin.nPUWorkersSettings.close')"
      @close="deleteTarget = null"
    >
      <p class="text-autobot-text-secondary mb-6">
        {{ $t('settings.admin.nPUWorkersSettings.areYouSureYou') }} <strong>{{ deleteTarget.hostname }}</strong>{{ $t('settings.admin.nPUWorkersSettings.thisActionCannotBe') }}
      </p>
      <template #actions>
        <button
          @click="deleteTarget = null"
          class="px-4 py-2 bg-autobot-bg-tertiary text-autobot-text-secondary rounded-lg hover:bg-autobot-bg-active"
        >
          {{ $t('settings.admin.nPUWorkersSettings.cancel') }}
        </button>
        <button
          @click="deleteWorker"
          :disabled="saving"
          class="px-4 py-2 bg-autobot-error-solid text-(--text-on-error) rounded-lg hover:bg-(--color-error-solid-hover) disabled:opacity-50 flex items-center gap-2"
        >
          <svg v-if="saving" class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          {{ $t('settings.admin.nPUWorkersSettings.remove') }}
        </button>
      </template>
    </BaseModal>

    <!-- Metrics Modal -->
    <BaseModal
      v-if="selectedWorkerMetrics"
      :model-value="showMetrics"
      :title="$t('settings.admin.nPUWorkersSettings.hostnameMetrics', { hostname: selectedWorkerMetrics?.hostname })"
      size="md"
      :close-label="$t('settings.admin.nPUWorkersSettings.close')"
      @close="showMetrics = false"
    >
      <div class="space-y-4">
        <div class="grid grid-cols-2 gap-4">
          <div class="p-4 bg-autobot-bg-secondary rounded-lg">
            <p class="text-sm text-autobot-text-tertiary">{{ $t('settings.admin.nPUWorkersSettings.currentLoad') }}</p>
            <p class="text-xl font-semibold text-autobot-text-primary">{{ selectedWorkerMetrics.current_load }}%</p>
          </div>
          <div class="p-4 bg-autobot-bg-secondary rounded-lg">
            <p class="text-sm text-autobot-text-tertiary">{{ $t('settings.admin.nPUWorkersSettings.status') }}</p>
            <p class="text-xl font-semibold" :class="selectedWorkerMetrics.status === 'online' ? 'text-autobot-success' : 'text-autobot-text-secondary'">
              {{ selectedWorkerMetrics.status }}
            </p>
          </div>
        </div>

        <div class="p-4 bg-autobot-bg-secondary rounded-lg">
          <p class="text-sm text-autobot-text-tertiary mb-2">{{ $t('settings.admin.nPUWorkersSettings.capabilities') }}</p>
          <div class="flex flex-wrap gap-2">
            <span
              v-for="cap in selectedWorkerMetrics.capabilities"
              :key="cap"
              class="px-2 py-1 bg-white border border-autobot-border rounded-sm text-sm"
            >
              {{ cap }}
            </span>
          </div>
        </div>

        <div class="p-4 bg-autobot-bg-secondary rounded-lg">
          <p class="text-sm text-autobot-text-tertiary">{{ $t('settings.admin.nPUWorkersSettings.lastHeartbeat') }}</p>
          <p class="font-medium text-autobot-text-primary">{{ selectedWorkerMetrics.last_heartbeat || $t('settings.admin.nPUWorkersSettings.never') }}</p>
        </div>
      </div>
      <template #actions>
        <button
          @click="showMetrics = false"
          class="px-4 py-2 bg-autobot-bg-tertiary text-autobot-text-secondary rounded-lg hover:bg-autobot-bg-active"
        >
          {{ $t('settings.admin.nPUWorkersSettings.close') }}
        </button>
      </template>
    </BaseModal>
  </div>
</template>
