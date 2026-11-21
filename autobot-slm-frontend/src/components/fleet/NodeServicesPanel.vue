<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * NodeServicesPanel - Displays and manages systemd services on a node
 *
 * Features:
 * - Service list with status indicators (running/stopped/failed)
 * - Start/Stop/Restart buttons for each service
 * - Service log viewer modal
 * - Search and status filtering
 * - Real-time status updates via polling
 *
 * Related to Issue #728
 */

import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { BaseAlert, PollingPausedAlert, formatBytes, createLogger } from '@autobot/ui'
import { throwUnlessLoaded, useDashboardPoller } from '@/composables/useDashboardPoller'
import { useSlmApi } from '@/composables/useSlmApi'
import { useSlmWebSocket } from '@/composables/useSlmWebSocket'
import { formatCompactRelativeTime } from '@/utils/dateUtils'
import type { NodeService, ServiceStatus } from '@/types/slm'
import i18n from '@/i18n'
import ServiceLogsModal from '@/components/fleet/ServiceLogsModal.vue'

const logger = createLogger('NodeServicesPanel')

// Props
interface Props {
  nodeId: string
  nodeName?: string
  autoRefreshInterval?: number
}

const props = withDefaults(defineProps<Props>(), {
  nodeName: 'Node',
  autoRefreshInterval: 10000,
})

// Emits
const emit = defineEmits<{
  close: []
}>()

// API composable
const api = useSlmApi()
const { connect, subscribe, onServiceStatus, connected } = useSlmWebSocket()

// State
const services = ref<NodeService[]>([])
const totalServices = ref(0)
const isLoading = ref(true)
const isActionInProgress = ref(false)
const actionService = ref<string | null>(null)
const lastRefresh = ref<string | null>(null)
const errorMessage = ref<string | null>(null)

// Filter state
const statusFilter = ref<string>('all')
const searchQuery = ref('')
const autoRefresh = ref(true)

// Logs modal: ServiceLogsModal is open while a service name is set (#16245)
const logsServiceName = ref<string | null>(null)

// Pagination
const currentPage = ref(1)
const pageSize = 50

// Issue #1019: Track expanded error contexts
const expandedErrors = ref<Set<string>>(new Set())

// Status filter options
const statusOptions = [
  { value: 'all', label: 'All Status' },
  { value: 'running', label: 'Running' },
  { value: 'stopped', label: 'Stopped' },
  { value: 'failed', label: 'Failed' },
]

// Computed
const filteredServices = computed(() => {
  let filtered = services.value

  // Apply status filter
  if (statusFilter.value !== 'all') {
    filtered = filtered.filter(s => s.status === statusFilter.value)
  }

  // Apply search filter (client-side for instant feedback)
  if (searchQuery.value) {
    const query = searchQuery.value.toLowerCase()
    filtered = filtered.filter(s =>
      s.service_name.toLowerCase().includes(query) ||
      (s.description && s.description.toLowerCase().includes(query))
    )
  }

  return filtered
})

const statusCounts = computed(() => {
  const counts = { running: 0, stopped: 0, failed: 0, unknown: 0 }
  services.value.forEach(s => {
    // Own keys only: `in` also admits `constructor`/`toString`/`__proto__` from a network payload (#17497).
    if (Object.prototype.hasOwnProperty.call(counts, s.status)) {
      counts[s.status as keyof typeof counts]++
    }
  })
  return counts
})

// Methods
function getStatusClasses(status: ServiceStatus): { bg: string; text: string; dot: string } {
  const classes: Record<ServiceStatus, { bg: string; text: string; dot: string }> = {
    running: {
      bg: 'bg-autobot-success-bg',
      text: 'text-autobot-pill-ok-fg',
      dot: 'bg-autobot-dot-ok',
    },
    stopped: {
      bg: 'bg-autobot-bg-secondary',
      text: 'text-autobot-text-secondary',
      dot: 'bg-autobot-dot-idle',
    },
    failed: {
      bg: 'bg-autobot-error-bg',
      text: 'text-autobot-pill-bad-fg',
      dot: 'bg-autobot-dot-bad',
    },
    unknown: {
      bg: 'bg-autobot-warning-bg',
      text: 'text-autobot-pill-warn-fg',
      dot: 'bg-autobot-dot-warn',
    },
    // #15401: the rest of the agent's run-state vocabulary. These fell through
    // to the `unknown` styling, so a crash-looping service looked the same as
    // one the probe could not read.
    'crash-loop': { bg: 'bg-autobot-error-bg', text: 'text-autobot-pill-bad-fg', dot: 'bg-autobot-dot-bad' },
    starting: { bg: 'bg-autobot-info-bg', text: 'text-autobot-pill-info-fg', dot: 'bg-autobot-primary' },
    stopping: { bg: 'bg-autobot-info-bg', text: 'text-autobot-pill-info-fg', dot: 'bg-autobot-primary' },
    completed: { bg: 'bg-autobot-bg-secondary', text: 'text-autobot-text-secondary', dot: 'bg-autobot-dot-idle' },
  }
  return Object.prototype.hasOwnProperty.call(classes, status) ? classes[status] : classes.unknown
}

// #13138: `memory_bytes` is optional AND nullable in the contract; the body
// already handled `undefined`, only the signature disagreed.
const BYTES_OPTIONS = { decimals: [0, 1, 1, 2], units: ['B', 'KB', 'MB', 'GB'], nullText: '-', integerBase: true, keepTrailingZeros: true } as const

function toggleErrorDetail(serviceName: string): void {
  const next = new Set(expandedErrors.value)
  if (next.has(serviceName)) {
    next.delete(serviceName)
  } else {
    next.add(serviceName)
  }
  expandedErrors.value = next
}



async function fetchServices(): Promise<boolean> {
  try {
    const response = await api.getNodeServices(props.nodeId, {
      status: statusFilter.value !== 'all' ? statusFilter.value : undefined,
      search: searchQuery.value || undefined,
      page: currentPage.value,
      per_page: pageSize,
    })

    services.value = response.services
    totalServices.value = response.total
    lastRefresh.value = new Date().toISOString()
    errorMessage.value = null
    return true
  } catch (error) {
    logger.error('Failed to fetch services:', error)
    errorMessage.value = 'Failed to load services'
    return false
  } finally {
    isLoading.value = false
  }
}

async function handleAction(serviceName: string, action: 'start' | 'stop' | 'restart'): Promise<void> {
  if (isActionInProgress.value) return

  isActionInProgress.value = true
  actionService.value = serviceName

  try {
    let result
    switch (action) {
      case 'start':
        result = await api.startService(props.nodeId, serviceName)
        break
      case 'stop':
        result = await api.stopService(props.nodeId, serviceName)
        break
      case 'restart':
        result = await api.restartService(props.nodeId, serviceName)
        break
    }

    if (result.success) {
      // Refresh services list
      await fetchServices()
    } else {
      errorMessage.value = result.message
    }
  } catch (error) {
    logger.error(`Failed to ${action} service:`, error)
    errorMessage.value = i18n.global.t('fleet.nodeServicesPanel.actionFailed', { action, service: serviceName })
  } finally {
    isActionInProgress.value = false
    actionService.value = null
  }
}

function viewLogs(serviceName: string): void {
  logsServiceName.value = serviceName
}

function closeLogsModal(): void {
  logsServiceName.value = null
}

// #19482: shared dashboard policy; fetchServices() is false on a failed read, which the poller counts
const servicesPoller = useDashboardPoller(async () => {
  throwUnlessLoaded(await fetchServices())
}, props.autoRefreshInterval)

// Refresh/Retry: clear the shown error, restart (also a paused) poller; auto-refresh off is a one-off read
const restartServices = () => {
  errorMessage.value = null
  return autoRefresh.value ? servicesPoller.start('') : fetchServices()
}

// Debounced search
let searchTimeout: ReturnType<typeof setTimeout> | null = null
watch(searchQuery, () => {
  if (searchTimeout) clearTimeout(searchTimeout)
  searchTimeout = setTimeout(() => {
    currentPage.value = 1
    fetchServices()
  }, 300)
})

// Watch filter changes
watch(statusFilter, () => {
  currentPage.value = 1
  fetchServices()
})

// Watch auto-refresh changes
watch(autoRefresh, (enabled) => (enabled ? servicesPoller.start('') : servicesPoller.stop()))

// Handle real-time service status updates via WebSocket
function handleServiceStatusUpdate(
  nodeId: string,
  data: { service_name: string; status: string; action?: string; success: boolean; message?: string }
): void {
  // Only handle updates for this node
  if (nodeId !== props.nodeId) return

  // Find the service in our list and update its status
  const serviceIndex = services.value.findIndex(s => s.service_name === data.service_name)
  if (serviceIndex === -1) return

  // Update the service status
  services.value[serviceIndex] = {
    ...services.value[serviceIndex],
    status: data.status as ServiceStatus,
    last_checked: new Date().toISOString(),
  }

  logger.debug('Service status updated via WebSocket:', data.service_name, data.status)
}

// Lifecycle
onMounted(() => {
  restartServices()

  // Setup WebSocket for real-time updates
  connect()
  subscribe(props.nodeId)
  onServiceStatus(handleServiceStatusUpdate)
})

onUnmounted(() => {
  if (searchTimeout) {
    clearTimeout(searchTimeout)
  }
})
</script>

<template>
  <div class="bg-white rounded-lg shadow-xs border border-autobot-border flex flex-col max-h-[700px]">
    <!-- Header -->
    <div class="flex items-center justify-between px-4 py-3 border-b border-autobot-border">
      <div class="flex items-center gap-3">
        <h3 class="text-lg font-semibold text-autobot-text-primary">{{ $t('fleet.nodeServicesPanel.value0Services', { value0: nodeName }) }}</h3>
        <!-- WebSocket Status -->
        <span
          :class="[
            'inline-flex items-center gap-1 px-1.5 py-0.5 rounded-sm text-xs',
            connected ? 'text-autobot-success' : 'text-autobot-text-tertiary'
          ]"
          :title="connected ? 'Live updates active' : 'Live updates offline'"
        >
          <span :class="['w-1.5 h-1.5 rounded-full', connected ? 'bg-autobot-dot-ok' : 'bg-autobot-dot-idle']"></span>
          {{ connected ? $t('fleet.nodeServicesPanel.live') : $t('fleet.nodeServicesPanel.offline') }}
        </span>
        <div class="flex items-center gap-2 text-sm">
          <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-sm bg-autobot-pill-ok-bg text-autobot-pill-ok-fg">
            <span class="w-2 h-2 rounded-full bg-autobot-dot-ok"></span>
            {{ statusCounts.running }}
          </span>
          <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-sm bg-autobot-bg-tertiary text-autobot-text-secondary">
            <span class="w-2 h-2 rounded-full bg-autobot-dot-idle"></span>
            {{ statusCounts.stopped }}
          </span>
          <span v-if="statusCounts.failed > 0" class="inline-flex items-center gap-1 px-2 py-0.5 rounded-sm bg-autobot-pill-bad-bg text-autobot-pill-bad-fg">
            <span class="w-2 h-2 rounded-full bg-autobot-dot-bad"></span>
            {{ statusCounts.failed }}
          </span>
        </div>
      </div>
      <button
        @click="emit('close')"
        class="text-autobot-text-tertiary hover:text-autobot-text-secondary transition-colors"
        :aria-label="$t('fleet.nodeServicesPanel.close')"
      >
        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>

    <PollingPausedAlert :poller="servicesPoller" :message="$t('common.polling.paused')" :retry-label="$t('common.polling.retry')" @retry="restartServices" />

    <!-- Error Banner -->
    <BaseAlert
      v-if="errorMessage"
      variant="error"
      size="compact"
      :message="errorMessage"
      dismissible
      :dismiss-label="$t('fleet.nodeServicesPanel.dismissError')"
      @dismiss="errorMessage = null"
    />

    <!-- Filter Bar -->
    <div class="flex items-center gap-4 px-4 py-2 bg-autobot-bg-secondary border-b border-autobot-border">
      <!-- Search -->
      <div class="flex-1 relative">
        <svg class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-autobot-text-tertiary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
        </svg>
        <input
          v-model="searchQuery"
          type="text"
          :placeholder="$t('fleet.nodeServicesPanel.searchServices')"
          class="w-full pl-9 pr-4 py-1.5 text-sm border border-autobot-border-strong rounded-md focus:ring-primary-500 focus:border-primary-500"
        />
      </div>

      <!-- Status Filter -->
      <div class="flex items-center gap-2">
        <label class="text-sm text-autobot-text-secondary">{{ $t('fleet.nodeServicesPanel.status') }}</label>
        <select
          v-model="statusFilter"
          class="text-sm border-autobot-border-strong rounded-md focus:ring-primary-500 focus:border-primary-500"
        >
          <option v-for="option in statusOptions" :key="option.value" :value="option.value">
            {{ option.label }}
          </option>
        </select>
      </div>

      <!-- Refresh button -->
      <button
        @click="restartServices"
        :disabled="isLoading"
        class="p-1.5 text-autobot-text-tertiary hover:text-autobot-text-secondary disabled:opacity-50"
        :title="$t('fleet.nodeServicesPanel.refresh')"
      >
        <svg :class="['w-5 h-5', isLoading ? 'animate-spin' : '']" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
        </svg>
      </button>
    </div>

    <!-- Loading State -->
    <div v-if="isLoading && services.length === 0" class="flex-1 flex flex-col items-center justify-center py-12 text-autobot-text-tertiary">
      <svg class="w-8 h-8 animate-spin mb-3" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
      </svg>
      <span>{{ $t('fleet.nodeServicesPanel.loadingServices') }}</span>
    </div>

    <!-- Empty State -->
    <div
      v-else-if="filteredServices.length === 0"
      class="flex-1 flex flex-col items-center justify-center py-12 text-autobot-text-tertiary"
    >
      <svg class="w-12 h-12 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01" />
      </svg>
      <p v-if="services.length === 0">{{ $t('fleet.nodeServicesPanel.noServicesDiscoveredYet') }}</p>
      <p v-else>{{ $t('fleet.nodeServicesPanel.noServicesMatchThe') }}</p>
    </div>

    <!-- Services Table -->
    <div v-else class="flex-1 overflow-y-auto">
      <table class="w-full">
        <thead class="bg-autobot-bg-secondary sticky top-0">
          <tr>
            <th class="w-12 px-4 py-2 text-left text-xs font-semibold text-autobot-text-tertiary uppercase tracking-wider">{{ $t('fleet.nodeServicesPanel.status1') }}</th>
            <th class="px-4 py-2 text-left text-xs font-semibold text-autobot-text-tertiary uppercase tracking-wider">{{ $t('fleet.nodeServicesPanel.service') }}</th>
            <th class="w-20 px-4 py-2 text-left text-xs font-semibold text-autobot-text-tertiary uppercase tracking-wider">{{ $t('fleet.nodeServicesPanel.enabled') }}</th>
            <th class="w-24 px-4 py-2 text-left text-xs font-semibold text-autobot-text-tertiary uppercase tracking-wider">{{ $t('fleet.nodeServicesPanel.memory') }}</th>
            <th class="w-28 px-4 py-2 text-left text-xs font-semibold text-autobot-text-tertiary uppercase tracking-wider">{{ $t('fleet.nodeServicesPanel.lastCheck') }}</th>
            <th class="w-36 px-4 py-2 text-center text-xs font-semibold text-autobot-text-tertiary uppercase tracking-wider">{{ $t('fleet.nodeServicesPanel.actions') }}</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-autobot-border-subtle">
          <tr
            v-for="service in filteredServices"
            :key="service.id"
            :class="[
              'hover:bg-autobot-bg-hover transition-colors',
              service.status === 'failed' ? 'bg-autobot-error-bg' : '',
            ]"
          >
            <!-- Status -->
            <td class="px-4 py-3">
              <div
                :class="[
                  'inline-flex items-center gap-1.5 px-2 py-0.5 rounded-sm text-xs font-medium',
                  getStatusClasses(service.status).bg,
                  getStatusClasses(service.status).text,
                ]"
              >
                <span :class="['w-2 h-2 rounded-full', getStatusClasses(service.status).dot]"></span>
                {{ service.status }}
              </div>
            </td>

            <!-- Service Name, Description & Error Context (#1019) -->
            <td class="px-4 py-3">
              <div class="font-medium text-autobot-text-primary flex items-center gap-1.5">
                {{ service.service_name }}
                <span
                  v-if="service.extra_data?.engine_degraded"
                  class="inline-flex items-center px-1.5 py-0.5 rounded-sm text-xs font-medium bg-autobot-pill-warn-bg text-autobot-pill-warn-fg"
                  :title="String(service.extra_data.degraded_reason || '')"
                >
                  {{ $t('fleet.nodeServicesPanel.engineDegraded') }}
                </span>
              </div>
              <div v-if="service.description" class="text-xs text-autobot-text-tertiary truncate max-w-xs" :title="service.description">
                {{ service.description }}
              </div>
              <div
                v-if="service.extra_data?.engine_degraded && service.extra_data?.degraded_reason"
                class="mt-1 text-xs text-autobot-pill-warn-fg"
              >
                {{ service.extra_data.degraded_reason }}
              </div>
              <div
                v-if="service.status === 'failed' && service.extra_data?.error_message"
                class="mt-1.5 text-xs"
              >
                <button
                  @click="toggleErrorDetail(service.service_name)"
                  class="text-autobot-error hover:text-autobot-pill-bad-fg underline"
                >{{ $t('fleet.nodeServicesPanel.value0ErrorContext', { value0: expandedErrors.has(service.service_name) ? $t('fleet.nodeServicesPanel.hide') : $t('fleet.nodeServicesPanel.show') }) }}</button>
                <BaseAlert v-if="expandedErrors.has(service.service_name)" variant="error" size="compact" class="mt-1">
                  <p class="font-mono whitespace-pre-wrap max-h-32 overflow-y-auto">{{ service.extra_data.error_message }}</p></BaseAlert>
              </div>
            </td>

            <!-- Enabled -->
            <td class="px-4 py-3">
              <span
                :class="[
                  'text-xs font-medium',
                  service.enabled ? 'text-autobot-success' : 'text-autobot-text-tertiary',
                ]"
              >
                {{ service.enabled ? $t('fleet.nodeServicesPanel.yes') : $t('fleet.nodeServicesPanel.no') }}
              </span>
            </td>

            <!-- Memory -->
            <td class="px-4 py-3 text-sm text-autobot-text-secondary font-mono">
              {{ formatBytes(service.memory_bytes, BYTES_OPTIONS) }}
            </td>

            <!-- Last Check -->
            <td class="px-4 py-3 text-xs text-autobot-text-tertiary">
              {{ formatCompactRelativeTime(service.last_checked) }}
            </td>

            <!-- Actions -->
            <td class="px-4 py-3">
              <div class="flex items-center justify-center gap-1">
                <!-- Start -->
                <button
                  v-if="service.status !== 'running'"
                  @click="handleAction(service.service_name, 'start')"
                  :disabled="isActionInProgress"
                  class="p-1.5 text-autobot-success hover:bg-autobot-success-bg rounded-sm disabled:opacity-50"
                  :title="$t('fleet.nodeServicesPanel.start')"
                >
                  <svg v-if="actionService === service.service_name" class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
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
                  @click="handleAction(service.service_name, 'stop')"
                  :disabled="isActionInProgress"
                  class="p-1.5 text-autobot-error hover:bg-autobot-error-bg rounded-sm disabled:opacity-50"
                  :title="$t('fleet.nodeServicesPanel.stop')"
                >
                  <svg v-if="actionService === service.service_name" class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
                  </svg>
                  <svg v-else class="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                    <rect x="6" y="6" width="12" height="12" />
                  </svg>
                </button>

                <!-- Restart -->
                <button
                  @click="handleAction(service.service_name, 'restart')"
                  :disabled="isActionInProgress"
                  class="p-1.5 text-autobot-text-link hover:bg-autobot-info-bg rounded-sm disabled:opacity-50"
                  :title="$t('fleet.nodeServicesPanel.restart')"
                >
                  <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                  </svg>
                </button>

                <!-- Logs -->
                <button
                  @click="viewLogs(service.service_name)"
                  class="p-1.5 text-autobot-text-tertiary hover:bg-autobot-bg-hover rounded-sm"
                  :title="$t('fleet.nodeServicesPanel.viewLogs')"
                >
                  <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Footer -->
    <div class="flex items-center justify-between px-4 py-2 bg-autobot-bg-secondary border-t border-autobot-border">
      <label class="flex items-center gap-2 text-sm text-autobot-text-secondary cursor-pointer">
        <input
          type="checkbox"
          v-model="autoRefresh"
          class="w-4 h-4 text-primary-600 border-autobot-border-strong rounded-sm focus:ring-primary-500"
        />{{ $t('fleet.nodeServicesPanel.autoRefreshEveryValue0S', { value0: Math.round(autoRefreshInterval / 1000) }) }}</label>
      <div class="text-xs text-autobot-text-tertiary">
        <span class="font-medium text-autobot-text-secondary">{{ filteredServices.length }}</span>{{ $t('fleet.nodeServicesPanel.ofValue0Services', { value0: totalServices }) }}<span v-if="lastRefresh">{{ $t('fleet.nodeServicesPanel.updatedValue0', { value0: formatCompactRelativeTime(lastRefresh) }) }}</span>
      </div>
    </div>

    <!-- Logs Modal -->
    <ServiceLogsModal :node-id="nodeId" :service-name="logsServiceName" @close="closeLogsModal" />
  </div>
</template>
