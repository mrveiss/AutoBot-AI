<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * DeploymentLogViewer - Real-time deployment log viewer with WebSocket.
 *
 * Issue #754: Added role="dialog", aria-modal, aria-labelledby,
 * role="progressbar" with aria-valuenow, role="log" on log container,
 * role="status" on connection indicator, role="alert" on error,
 * accessible labels on close buttons.
 */

import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { BaseAlert, BaseModal, createLogger, createDateFormatter } from '@autobot/ui'
import { getSlmApiBase } from '@/config/ssot-config'
import i18n from '@/i18n'

const logger = createLogger('DeploymentLogViewer')

/**
 * A message received on the deployment log WebSocket — NOT an HTTP response.
 *
 * Renamed from `LogEntry` in #13138: it collided with the generated
 * `components['schemas']['LogEntry']` (api/monitoring.py:128) despite sharing
 * no field with it (`type`/`log_type`, and a `Date` rather than an ISO string).
 */
interface DeploymentLogMessage {
  type: string
  log_type: string
  message: string
  timestamp: Date
}


const props = defineProps<{
  deploymentId: string
  visible: boolean
}>()

const emit = defineEmits<{
  close: []
  statusChange: [status: string]
}>()

const logs = ref<DeploymentLogMessage[]>([])
const status = ref<string>('connecting')
const progress = ref<number>(0)
const error = ref<string | null>(null)
const isConnected = ref(false)
const logContainer = ref<HTMLElement | null>(null)

let ws: WebSocket | null = null
let reconnectTimeout: ReturnType<typeof setTimeout> | null = null

function getLogClass(logType: string): string {
  switch (logType) {
    case 'success':
      return 'text-autobot-success'
    case 'error':
      return 'text-autobot-error'
    case 'warning':
      return 'text-autobot-warning'
    case 'task':
      return 'text-autobot-info font-semibold'
    case 'info':
      return 'text-autobot-info'
    default:
      return 'text-autobot-text-tertiary'
  }
}

function getStatusBadgeClass(s: string): string {
  switch (s) {
    case 'completed':
      return 'bg-autobot-pill-ok-bg text-autobot-pill-ok-fg'
    case 'in_progress':
      return 'bg-autobot-pill-info-bg text-autobot-pill-info-fg'
    case 'pending':
      return 'bg-autobot-pill-warn-bg text-autobot-pill-warn-fg'
    case 'failed':
      return 'bg-autobot-pill-bad-bg text-autobot-pill-bad-fg'
    case 'cancelled':
      return 'bg-autobot-pill-warn-bg text-autobot-pill-warn-fg'
    case 'connecting':
      return 'bg-autobot-bg-tertiary text-autobot-text-primary'
    default:
      return 'bg-autobot-bg-tertiary text-autobot-text-primary'
  }
}

function connect(): void {
  if (ws) {
    ws.close()
  }

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const wsUrl = `${protocol}//${window.location.host}${getSlmApiBase()}/ws/deployments/${props.deploymentId}`

  logs.value.push({
    type: 'log',
    log_type: 'info',
    message: `Connecting to deployment stream...`,
    timestamp: new Date(),
  })

  ws = new WebSocket(wsUrl)

  ws.onopen = () => {
    isConnected.value = true
    logs.value.push({
      type: 'log',
      log_type: 'success',
      message: 'Connected to deployment stream',
      timestamp: new Date(),
    })
  }

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)

      if (data.type === 'log') {
        logs.value.push({
          type: 'log',
          log_type: data.log_type,
          message: data.message,
          timestamp: new Date(),
        })
        scrollToBottom()
      } else if (data.type === 'status') {
        status.value = data.status
        progress.value = data.progress
        if (data.error) {
          error.value = data.error
        }
        emit('statusChange', data.status)
      } else if (data.type === 'connected') {
        status.value = 'connected'
      } else if (data.type === 'ping') {
        // Keep-alive ping, ignore
      }
    } catch (e) {
      logger.error('Failed to parse WebSocket message:', e)
    }
  }

  ws.onclose = () => {
    isConnected.value = false
    if (props.visible && status.value !== 'completed' && status.value !== 'failed') {
      logs.value.push({
        type: 'log',
        log_type: 'warning',
        message: 'Disconnected. Reconnecting in 3 seconds...',
        timestamp: new Date(),
      })
      reconnectTimeout = setTimeout(() => connect(), 3000)
    }
  }

  ws.onerror = () => {
    logs.value.push({
      type: 'log',
      log_type: 'error',
      message: 'WebSocket connection error',
      timestamp: new Date(),
    })
  }
}

function disconnect(): void {
  if (reconnectTimeout) {
    clearTimeout(reconnectTimeout)
    reconnectTimeout = null
  }
  if (ws) {
    ws.close()
    ws = null
  }
  isConnected.value = false
}

function scrollToBottom(): void {
  nextTick(() => {
    if (logContainer.value) {
      logContainer.value.scrollTop = logContainer.value.scrollHeight
    }
  })
}

const formatTime = createDateFormatter({ kind: 'time', locale: () => String(i18n.global.locale), intl: { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' } })

watch(
  () => props.visible,
  (visible) => {
    if (visible) {
      connect()
    } else {
      disconnect()
    }
  }
)

watch(
  () => props.deploymentId,
  () => {
    if (props.visible) {
      logs.value = []
      status.value = 'connecting'
      progress.value = 0
      error.value = null
      connect()
    }
  }
)

onMounted(() => {
  if (props.visible) {
    connect()
  }
})

onUnmounted(() => {
  disconnect()
})
</script>

<template>
  <BaseModal
    v-if="visible"
    :model-value="true"
    :title="$t('deploymentLogViewer.deploymentLog')"
    width="56rem"
    :close-label="$t('deploymentLogViewer.closeDeploymentLog')"
    @close="emit('close')"
  >
    <template #subtitle>
      <span class="text-sm text-muted">{{ deploymentId }}</span>
      <span
        :class="[
          'ml-2 px-2 py-0.5 text-xs font-medium rounded-full',
          getStatusBadgeClass(status),
        ]"
        role="status"
      >
        {{ status }}
      </span>
    </template>

    <!-- Progress Bar -->
    <div v-if="progress > 0" class="pb-3">
      <div class="flex items-center gap-3">
        <div
          class="flex-1 bg-tertiary rounded-full h-2"
          role="progressbar"
          :aria-valuenow="progress"
          aria-valuemin="0"
          aria-valuemax="100"
          :aria-label="$t('deploymentLogViewer.deploymentProgressAria', { percent: progress })"
        >
          <div
            class="bg-primary-600 h-2 rounded-full transition-all duration-300"
            :style="{ width: `${progress}%` }"
          />
        </div>
        <span class="text-sm text-muted w-12 text-right" aria-hidden="true">{{ progress }}%</span>
      </div>
    </div>

    <!-- Log Container -->
    <div
      ref="logContainer"
      class="max-h-[60vh] overflow-y-auto p-4 font-mono text-sm bg-autobot-bg-tertiary rounded"
      role="log"
      :aria-label="$t('deploymentLogViewer.deploymentLogOutput')"
      aria-live="polite"
    >
      <div
        v-for="(log, index) in logs"
        :key="index"
        class="flex gap-2 py-0.5"
      >
        <span class="text-autobot-text-tertiary shrink-0">{{ formatTime(log.timestamp) }}</span>
        <span :class="getLogClass(log.log_type)">{{ log.message }}</span>
      </div>
      <div v-if="logs.length === 0" class="text-autobot-text-tertiary italic">
        {{ $t('deploymentLogViewer.waitingForDeploymentLogs') }}
      </div>
    </div>

    <!-- Error -->
    <BaseAlert v-if="error" variant="error" class="mt-3" :message="error" />

    <template #actions>
      <div class="flex w-full items-center justify-between">
        <div class="flex items-center gap-2" role="status" :aria-label="isConnected ? 'WebSocket connected' : 'WebSocket disconnected'">
          <span
            :class="[
              'w-2 h-2 rounded-full',
              isConnected ? 'bg-autobot-dot-ok' : 'bg-autobot-dot-bad',
            ]"
            aria-hidden="true"
          />
          <span class="text-sm text-muted">
            {{ isConnected ? $t('deploymentLogViewer.connected') : $t('deploymentLogViewer.disconnected') }}
          </span>
        </div>
        <button
          @click="emit('close')"
          class="btn btn-secondary"
        >
          {{ $t('deploymentLogViewer.close') }}
        </button>
      </div>
    </template>
  </BaseModal>
</template>
