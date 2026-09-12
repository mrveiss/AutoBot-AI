<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * RedisServicePanel - Start/Stop/Restart and logs for the Redis service
 *
 * Acts on the node that holds the `redis` role, through that role's systemd
 * unit, with the SLM's own node-service API (#16245): state, PID and memory
 * from GET /nodes/{nodeId}/services, actions from
 * POST /nodes/{nodeId}/services/{service}/{action}, and the journal through
 * ServiceLogsModal. Polls every 10 seconds. A value the SLM does not report
 * shows as unknown.
 *
 * Related to Issue #3381
 */

import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { formatBytes } from '@/utils/formatHelpers'
import i18n from '@/i18n'
import { createLogger } from '@/utils/debugUtils'
import { useSlmApi } from '@/composables/useSlmApi'
import type { NodeService, ServiceActionResponse } from '@/types/slm'
import ServiceLogsModal from '@/components/fleet/ServiceLogsModal.vue'

type RedisServiceAction = 'start' | 'stop' | 'restart'

const props = defineProps<{
  /** Node holding the `redis` role; unset while role owners load, or when no node holds it. */
  nodeId?: string
  /** The `redis` role's systemd unit. */
  serviceName?: string
}>()

const t = i18n.global.t.bind(i18n.global)

const logger = createLogger('RedisServicePanel')
const api = useSlmApi()

const POLL_INTERVAL_MS = 10_000
const SUCCESS_BANNER_MS = 4_000

const ACTIONS: Record<RedisServiceAction, (nodeId: string, serviceName: string) => Promise<ServiceActionResponse>> = {
  start: api.startService,
  stop: api.stopService,
  restart: api.restartService,
}

// -----------------------------------------------------------------------
// State
// -----------------------------------------------------------------------

const service = ref<NodeService | null>(null)
const hasFetched = ref(false)
const isLoading = ref(false)
const isActionInProgress = ref(false)
const currentAction = ref<RedisServiceAction | null>(null)
const errorMessage = ref<string | null>(null)
const successMessage = ref<string | null>(null)
const showStopConfirm = ref(false)
const logsServiceName = ref<string | null>(null)

let pollInterval: ReturnType<typeof setInterval> | null = null

const hasTarget = computed(() => Boolean(props.nodeId && props.serviceName))
const isRunning = computed(() => service.value?.status === 'running')
const isNotReported = computed(() => hasTarget.value && hasFetched.value && !service.value && !errorMessage.value)

const stateText = computed(() => {
  const unit = service.value
  if (!unit?.active_state) return t('redisServicePanel.unknown')
  return unit.sub_state ? `${unit.active_state} (${unit.sub_state})` : unit.active_state
})

const memoryText = computed(() =>
  formatBytes(service.value?.memory_bytes ?? null, {
    units: ['B', 'KB', 'MB', 'GB'],
    decimals: 1,
    keepTrailingZeros: true,
    integerBase: true,
    nullText: t('redisServicePanel.unknown'),
  }),
)

// -----------------------------------------------------------------------
// Helpers
// -----------------------------------------------------------------------

function statusDotClass(status: string | undefined): string {
  switch (status) {
    case 'running': return 'bg-green-500'
    case 'stopped': return 'bg-gray-400'
    case 'failed':
    case 'crash-loop': return 'bg-red-500'
    default: return 'bg-yellow-400'
  }
}

function statusTextClass(status: string | undefined): string {
  switch (status) {
    case 'running': return 'text-green-700'
    case 'stopped': return 'text-gray-600'
    case 'failed':
    case 'crash-loop': return 'text-red-700'
    default: return 'text-yellow-700'
  }
}

// -----------------------------------------------------------------------
// API calls
// -----------------------------------------------------------------------

async function fetchStatus(): Promise<void> {
  if (!props.nodeId || !props.serviceName) {
    service.value = null
    return
  }
  isLoading.value = true
  try {
    const response = await api.getNodeServices(props.nodeId, { search: props.serviceName })
    // `search` is a substring match, so take the exact unit only
    service.value = response.services.find((unit) => unit.service_name === props.serviceName) ?? null
    errorMessage.value = null
  } catch (err) {
    logger.error('Failed to fetch Redis status:', err)
    // A failed read says nothing about the unit now, so drop the last value
    service.value = null
    errorMessage.value = t('redisServicePanel.fetchStatusFailed')
  } finally {
    isLoading.value = false
    hasFetched.value = true
  }
}

async function performAction(action: RedisServiceAction): Promise<void> {
  if (isActionInProgress.value || !props.nodeId || !props.serviceName) return
  isActionInProgress.value = true
  currentAction.value = action
  errorMessage.value = null
  successMessage.value = null

  try {
    const result = await ACTIONS[action](props.nodeId, props.serviceName)
    await fetchStatus()
    if (result.success) {
      successMessage.value = t('redisServicePanel.actionSucceeded', { action })
      setTimeout(() => { successMessage.value = null }, SUCCESS_BANNER_MS)
    } else {
      errorMessage.value = result.message || t('redisServicePanel.actionFailed', { action })
    }
  } catch (err) {
    logger.error(`Failed to ${action} Redis service:`, err)
    errorMessage.value = t('redisServicePanel.actionFailed', { action })
  } finally {
    isActionInProgress.value = false
    currentAction.value = null
  }
}

function requestStop(): void {
  showStopConfirm.value = true
}

function confirmStop(): void {
  showStopConfirm.value = false
  performAction('stop')
}

function cancelStop(): void {
  showStopConfirm.value = false
}

function openLogs(): void {
  logsServiceName.value = props.serviceName ?? null
}

// -----------------------------------------------------------------------
// Lifecycle
// -----------------------------------------------------------------------

// Role owners load after mount, so the target can arrive late or change
watch(
  () => [props.nodeId, props.serviceName],
  () => {
    hasFetched.value = false
    fetchStatus()
  },
  { immediate: true },
)

onMounted(() => {
  pollInterval = setInterval(fetchStatus, POLL_INTERVAL_MS)
})

onUnmounted(() => {
  if (pollInterval) clearInterval(pollInterval)
})
</script>

<template>
  <div class="bg-white rounded-lg shadow-xs border border-gray-200">
    <!-- Header -->
    <div class="flex items-center justify-between px-4 py-3 border-b border-gray-200">
      <div class="flex items-center gap-3">
        <!-- Redis icon -->
        <div class="w-8 h-8 rounded-md bg-red-100 flex items-center justify-center">
          <svg class="w-5 h-5 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4" />
          </svg>
        </div>
        <div>
          <h3 class="text-base font-semibold text-gray-900">{{ $t('redisServicePanel.redisService') }}</h3>
          <p class="text-xs text-gray-500">{{ $t('redisServicePanel.inMemoryDataStore') }}</p>
        </div>
        <!-- Status badge -->
        <div v-if="hasTarget && hasFetched && !isLoading" class="flex items-center gap-1.5">
          <span :class="['w-2.5 h-2.5 rounded-full', statusDotClass(service?.status)]"></span>
          <span :class="['text-sm font-medium capitalize', statusTextClass(service?.status)]">
            {{ service ? service.status : $t('redisServicePanel.unknown') }}
          </span>
        </div>
        <div v-else-if="isLoading" class="flex items-center gap-1.5 text-gray-400 text-sm">
          <svg class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
          </svg>
          {{ $t('redisServicePanel.checking') }}
        </div>
      </div>

      <!-- Refresh button -->
      <button
        @click="fetchStatus"
        :disabled="!hasTarget || isLoading || isActionInProgress"
        class="p-1.5 text-gray-400 hover:text-gray-600 disabled:opacity-40 transition-colors"
        :title="$t('redisServicePanel.refreshStatus')"
        :aria-label="$t('redisServicePanel.refreshStatus')"
      >
        <svg :class="['w-4 h-4', isLoading ? 'animate-spin' : '']" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
            d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
        </svg>
      </button>
    </div>

    <!-- No node holds the redis role -->
    <div v-if="!hasTarget" class="px-4 py-3 border-b border-gray-200 text-sm text-gray-600">
      {{ $t('redisServicePanel.noRedisNode') }}
    </div>
    <!-- The node does not report the unit -->
    <div v-else-if="isNotReported" class="px-4 py-3 border-b border-gray-200 text-sm text-gray-600">
      {{ $t('redisServicePanel.notReported', { service: serviceName, node: nodeId }) }}
    </div>

    <!-- Success / Error banners -->
    <div v-if="successMessage" class="px-4 py-2 bg-green-50 border-b border-green-100 text-sm text-green-700 flex items-center justify-between">
      <span>{{ successMessage }}</span>
      <button @click="successMessage = null" class="text-green-500 hover:text-green-700" :aria-label="$t('redisServicePanel.dismiss')">
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>
    <div v-if="errorMessage" class="px-4 py-2 bg-red-50 border-b border-red-100 text-sm text-red-700 flex items-center justify-between">
      <span>{{ errorMessage }}</span>
      <button @click="errorMessage = null" class="text-red-500 hover:text-red-700" :aria-label="$t('redisServicePanel.dismiss')">
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>

    <!-- Metrics grid -->
    <div class="grid grid-cols-1 sm:grid-cols-3 gap-px bg-gray-100 border-b border-gray-200">
      <div class="bg-white px-4 py-3">
        <div class="text-xs text-gray-500 mb-0.5">{{ $t('redisServicePanel.state') }}</div>
        <div class="text-sm font-semibold text-gray-900">{{ stateText }}</div>
      </div>
      <div class="bg-white px-4 py-3">
        <div class="text-xs text-gray-500 mb-0.5">{{ $t('redisServicePanel.mainPid') }}</div>
        <div class="text-sm font-semibold text-gray-900">
          {{ service?.main_pid ?? $t('redisServicePanel.unknown') }}
        </div>
      </div>
      <div class="bg-white px-4 py-3">
        <div class="text-xs text-gray-500 mb-0.5">{{ $t('redisServicePanel.memoryUsed') }}</div>
        <div class="text-sm font-semibold text-gray-900">{{ memoryText }}</div>
      </div>
    </div>

    <!-- Action buttons -->
    <div class="flex items-center gap-2 px-4 py-3">
      <!-- Start -->
      <button
        @click="performAction('start')"
        :disabled="!hasTarget || isActionInProgress || isRunning"
        class="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-md border transition-colors
               text-green-700 border-green-300 bg-green-50 hover:bg-green-100
               disabled:opacity-40 disabled:cursor-not-allowed"
      >
        <svg v-if="currentAction === 'start'" class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
        </svg>
        <svg v-else class="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
          <path d="M8 5v14l11-7z" />
        </svg>
        {{ $t('redisServicePanel.start') }}
      </button>

      <!-- Stop -->
      <button
        @click="requestStop"
        :disabled="!hasTarget || isActionInProgress || !isRunning"
        class="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-md border transition-colors
               text-red-700 border-red-300 bg-red-50 hover:bg-red-100
               disabled:opacity-40 disabled:cursor-not-allowed"
      >
        <svg v-if="currentAction === 'stop'" class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
        </svg>
        <svg v-else class="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
          <rect x="6" y="6" width="12" height="12" />
        </svg>
        {{ $t('redisServicePanel.stop') }}
      </button>

      <!-- Restart -->
      <button
        @click="performAction('restart')"
        :disabled="!hasTarget || isActionInProgress"
        class="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-md border transition-colors
               text-blue-700 border-blue-300 bg-blue-50 hover:bg-blue-100
               disabled:opacity-40 disabled:cursor-not-allowed"
      >
        <svg v-if="currentAction === 'restart'" class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
        </svg>
        <svg v-else class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
            d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
        </svg>
        {{ $t('redisServicePanel.restart') }}
      </button>

      <!-- Logs -->
      <button
        @click="openLogs"
        :disabled="!hasTarget"
        class="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-md border transition-colors
               text-gray-700 border-gray-300 bg-white hover:bg-gray-50
               disabled:opacity-40 disabled:cursor-not-allowed"
      >
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
            d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
        </svg>
        {{ $t('redisServicePanel.viewLogs') }}
      </button>

      <!-- Last checked -->
      <span v-if="service?.last_checked" class="ml-auto text-xs text-gray-400">{{ $t('redisServicePanel.checkedValue0', { value0: new Date(service.last_checked).toLocaleTimeString() }) }}</span>
    </div>

    <!-- Journal for the unit on its node -->
    <ServiceLogsModal
      v-if="nodeId"
      :node-id="nodeId"
      :service-name="logsServiceName"
      @close="logsServiceName = null"
    />

    <!-- Stop confirmation dialog -->
    <teleport to="body">
      <div v-if="showStopConfirm" class="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div class="absolute inset-0 bg-black/50" @click="cancelStop"></div>
        <div class="relative bg-white rounded-lg shadow-xl max-w-sm w-full p-6">
          <h3 class="text-base font-semibold text-gray-900 mb-2">{{ $t('redisServicePanel.stopRedisService') }}</h3>
          <p class="text-sm text-gray-600 mb-5">
            {{ $t('redisServicePanel.stoppingRedisWillInterrupt') }}
          </p>
          <div class="flex justify-end gap-3">
            <button
              @click="cancelStop"
              class="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50"
            >
              {{ $t('redisServicePanel.cancel') }}
            </button>
            <button
              @click="confirmStop"
              class="px-4 py-2 text-sm font-medium text-white bg-red-600 border border-transparent rounded-md hover:bg-red-700"
            >
              {{ $t('redisServicePanel.stopRedis') }}
            </button>
          </div>
        </div>
      </div>
    </teleport>
  </div>
</template>
