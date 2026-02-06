<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('DeploymentLogViewer')

interface LogEntry {
  type: string
  log_type: string
  message: string
  timestamp: Date
}

interface StatusUpdate {
  type: string
  status: string
  progress: number
  error?: string
}

const props = defineProps<{
  deploymentId: string
  visible: boolean
}>()

const emit = defineEmits<{
  close: []
  statusChange: [status: string]
}>()

const logs = ref<LogEntry[]>([])
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
      return 'text-green-400'
    case 'error':
      return 'text-red-400'
    case 'warning':
      return 'text-yellow-400'
    case 'task':
      return 'text-blue-400 font-semibold'
    case 'info':
      return 'text-cyan-400'
    default:
      return 'text-gray-300'
  }
}

function getStatusBadgeClass(s: string): string {
  switch (s) {
    case 'completed':
      return 'bg-green-100 text-green-800'
    case 'in_progress':
      return 'bg-blue-100 text-blue-800'
    case 'pending':
      return 'bg-yellow-100 text-yellow-800'
    case 'failed':
      return 'bg-red-100 text-red-800'
    case 'cancelled':
      return 'bg-orange-100 text-orange-800'
    case 'connecting':
      return 'bg-gray-100 text-gray-800'
    default:
      return 'bg-gray-100 text-gray-800'
  }
}

function connect(): void {
  if (ws) {
    ws.close()
  }

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const wsUrl = `${protocol}//${window.location.host}/api/ws/deployments/${props.deploymentId}`

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

function formatTime(date: Date): string {
  return date.toLocaleTimeString('en-US', {
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

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
  <div
    v-if="visible"
    class="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"
    @click.self="emit('close')"
  >
    <div class="bg-gray-900 rounded-lg shadow-xl w-full max-w-4xl mx-4 max-h-[80vh] flex flex-col">
      <!-- Header -->
      <div class="flex items-center justify-between px-4 py-3 border-b border-gray-700">
        <div class="flex items-center gap-3">
          <h3 class="text-lg font-semibold text-white">Deployment Log</h3>
          <span class="text-sm text-gray-400">{{ deploymentId }}</span>
          <span
            :class="[
              'px-2 py-0.5 text-xs font-medium rounded-full',
              getStatusBadgeClass(status),
            ]"
          >
            {{ status }}
          </span>
        </div>
        <button
          @click="emit('close')"
          class="text-gray-400 hover:text-white transition-colors"
        >
          <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M6 18L18 6M6 6l12 12"
            />
          </svg>
        </button>
      </div>

      <!-- Progress Bar -->
      <div v-if="progress > 0" class="px-4 py-2 border-b border-gray-700">
        <div class="flex items-center gap-3">
          <div class="flex-1 bg-gray-700 rounded-full h-2">
            <div
              class="bg-blue-500 h-2 rounded-full transition-all duration-300"
              :style="{ width: `${progress}%` }"
            />
          </div>
          <span class="text-sm text-gray-400 w-12 text-right">{{ progress }}%</span>
        </div>
      </div>

      <!-- Log Container -->
      <div
        ref="logContainer"
        class="flex-1 overflow-y-auto p-4 font-mono text-sm bg-gray-950"
      >
        <div
          v-for="(log, index) in logs"
          :key="index"
          class="flex gap-2 py-0.5"
        >
          <span class="text-gray-500 shrink-0">{{ formatTime(log.timestamp) }}</span>
          <span :class="getLogClass(log.log_type)">{{ log.message }}</span>
        </div>
        <div v-if="logs.length === 0" class="text-gray-500 italic">
          Waiting for deployment logs...
        </div>
      </div>

      <!-- Error Footer -->
      <div
        v-if="error"
        class="px-4 py-3 bg-red-900 border-t border-red-700 text-red-200"
      >
        <div class="flex items-center gap-2">
          <svg class="w-5 h-5 shrink-0" fill="currentColor" viewBox="0 0 20 20">
            <path
              fill-rule="evenodd"
              d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z"
              clip-rule="evenodd"
            />
          </svg>
          <span>{{ error }}</span>
        </div>
      </div>

      <!-- Footer -->
      <div class="flex items-center justify-between px-4 py-3 border-t border-gray-700">
        <div class="flex items-center gap-2">
          <span
            :class="[
              'w-2 h-2 rounded-full',
              isConnected ? 'bg-green-500' : 'bg-red-500',
            ]"
          />
          <span class="text-sm text-gray-400">
            {{ isConnected ? 'Connected' : 'Disconnected' }}
          </span>
        </div>
        <button
          @click="emit('close')"
          class="px-4 py-2 text-sm font-medium text-gray-300 bg-gray-700 rounded-lg hover:bg-gray-600 transition-colors"
        >
          Close
        </button>
      </div>
    </div>
  </div>
</template>
