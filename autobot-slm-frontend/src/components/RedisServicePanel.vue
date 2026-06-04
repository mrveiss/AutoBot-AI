<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * RedisServicePanel - Start/Stop/Restart controls for the Redis service
 *
 * Polls GET /api/redis-service/status every 10 seconds and displays
 * status, uptime, and memory usage. Provides Start, Stop (with confirm
 * dialog), and Restart action buttons.
 *
 * Related to Issue #3381
 */

import { ref, onMounted, onUnmounted } from 'vue'
import { getBackendUrl } from '@/config/ssot-config'
import { useAuthStore } from '@/stores/auth'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('RedisServicePanel')
const authStore = useAuthStore()

// -----------------------------------------------------------------------
// Types
// -----------------------------------------------------------------------

interface RedisStatus {
  status: 'running' | 'stopped' | 'unknown'
  uptime_seconds: number | null
  memory_used_bytes: number | null
  memory_peak_bytes: number | null
  connected_clients: number | null
  last_checked: string | null
  error?: string
}

// -----------------------------------------------------------------------
// State
// -----------------------------------------------------------------------

const redisStatus = ref<RedisStatus | null>(null)
const isLoading = ref(true)
const isActionInProgress = ref(false)
const currentAction = ref<'start' | 'stop' | 'restart' | null>(null)
const errorMessage = ref<string | null>(null)
const successMessage = ref<string | null>(null)
const showStopConfirm = ref(false)

let pollInterval: ReturnType<typeof setInterval> | null = null

// -----------------------------------------------------------------------
// Helpers
// -----------------------------------------------------------------------

function authHeaders(): Record<string, string> {
  return { Authorization: `Bearer ${authStore.token}` }
}

function formatUptime(seconds: number | null): string {
  if (seconds === null || seconds === undefined) return '-'
  if (seconds < 60) return `${seconds}s`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  return `${h}h ${m}m`
}

function formatBytes(bytes: number | null): string {
  if (bytes === null || bytes === undefined) return '-'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function statusDotClass(status: string | undefined): string {
  switch (status) {
    case 'running': return 'bg-green-500'
    case 'stopped': return 'bg-gray-400'
    default: return 'bg-yellow-400'
  }
}

function statusTextClass(status: string | undefined): string {
  switch (status) {
    case 'running': return 'text-green-700'
    case 'stopped': return 'text-gray-600'
    default: return 'text-yellow-700'
  }
}

// -----------------------------------------------------------------------
// API calls
// -----------------------------------------------------------------------

async function fetchStatus(): Promise<void> {
  try {
    const response = await fetch(`${getBackendUrl()}/api/redis-service/status`)
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }
    redisStatus.value = await response.json()
    errorMessage.value = null
  } catch (err) {
    logger.error('Failed to fetch Redis status:', err)
    errorMessage.value = 'Failed to fetch Redis service status'
  } finally {
    isLoading.value = false
  }
}

async function performAction(action: 'start' | 'stop' | 'restart'): Promise<void> {
  if (isActionInProgress.value) return
  isActionInProgress.value = true
  currentAction.value = action
  errorMessage.value = null
  successMessage.value = null

  try {
    const response = await fetch(`${getBackendUrl()}/api/redis-service/${action}`, {
      method: 'POST',
      headers: authHeaders(),
    })
    if (!response.ok) {
      const body = await response.json().catch(() => ({}))
      throw new Error(body.detail ?? `HTTP ${response.status}`)
    }
    successMessage.value = `Redis service ${action} succeeded`
    // Refresh status after action
    await fetchStatus()
    setTimeout(() => { successMessage.value = null }, 4000)
  } catch (err) {
    logger.error(`Failed to ${action} Redis service:`, err)
    errorMessage.value = err instanceof Error ? err.message : `Failed to ${action} Redis service`
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

// -----------------------------------------------------------------------
// Lifecycle
// -----------------------------------------------------------------------

onMounted(() => {
  fetchStatus()
  pollInterval = setInterval(fetchStatus, 10000)
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
        <div v-if="redisStatus && !isLoading" class="flex items-center gap-1.5">
          <span :class="['w-2.5 h-2.5 rounded-full', statusDotClass(redisStatus.status)]"></span>
          <span :class="['text-sm font-medium capitalize', statusTextClass(redisStatus.status)]">
            {{ redisStatus.status }}
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
        :disabled="isLoading || isActionInProgress"
        class="p-1.5 text-gray-400 hover:text-gray-600 disabled:opacity-40 transition-colors"
        title="Refresh status"
        aria-label="Refresh status"
      >
        <svg :class="['w-4 h-4', isLoading ? 'animate-spin' : '']" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
            d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
        </svg>
      </button>
    </div>

    <!-- Success / Error banners -->
    <div v-if="successMessage" class="px-4 py-2 bg-green-50 border-b border-green-100 text-sm text-green-700 flex items-center justify-between">
      <span>{{ successMessage }}</span>
      <button @click="successMessage = null" class="text-green-500 hover:text-green-700" aria-label="Dismiss">
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>
    <div v-if="errorMessage" class="px-4 py-2 bg-red-50 border-b border-red-100 text-sm text-red-700 flex items-center justify-between">
      <span>{{ errorMessage }}</span>
      <button @click="errorMessage = null" class="text-red-500 hover:text-red-700" aria-label="Dismiss">
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>

    <!-- Metrics grid -->
    <div class="grid grid-cols-2 sm:grid-cols-4 gap-px bg-gray-100 border-b border-gray-200">
      <div class="bg-white px-4 py-3">
        <div class="text-xs text-gray-500 mb-0.5">{{ $t('redisServicePanel.uptime') }}</div>
        <div class="text-sm font-semibold text-gray-900">
          {{ redisStatus ? formatUptime(redisStatus.uptime_seconds) : '-' }}
        </div>
      </div>
      <div class="bg-white px-4 py-3">
        <div class="text-xs text-gray-500 mb-0.5">{{ $t('redisServicePanel.memoryUsed') }}</div>
        <div class="text-sm font-semibold text-gray-900">
          {{ redisStatus ? formatBytes(redisStatus.memory_used_bytes) : '-' }}
        </div>
      </div>
      <div class="bg-white px-4 py-3">
        <div class="text-xs text-gray-500 mb-0.5">{{ $t('redisServicePanel.peakMemory') }}</div>
        <div class="text-sm font-semibold text-gray-900">
          {{ redisStatus ? formatBytes(redisStatus.memory_peak_bytes) : '-' }}
        </div>
      </div>
      <div class="bg-white px-4 py-3">
        <div class="text-xs text-gray-500 mb-0.5">{{ $t('redisServicePanel.clients') }}</div>
        <div class="text-sm font-semibold text-gray-900">
          {{ redisStatus?.connected_clients ?? '-' }}
        </div>
      </div>
    </div>

    <!-- Action buttons -->
    <div class="flex items-center gap-2 px-4 py-3">
      <!-- Start -->
      <button
        @click="performAction('start')"
        :disabled="isActionInProgress || redisStatus?.status === 'running'"
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
        :disabled="isActionInProgress || redisStatus?.status !== 'running'"
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
        :disabled="isActionInProgress"
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

      <!-- Last checked -->
      <span v-if="redisStatus?.last_checked" class="ml-auto text-xs text-gray-400">
        Checked {{ new Date(redisStatus.last_checked).toLocaleTimeString() }}
      </span>
    </div>

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
