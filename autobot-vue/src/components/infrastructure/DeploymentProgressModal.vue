<template>
  <Teleport to="body">
    <Transition
      enter-active-class="transition duration-300 ease-out"
      enter-from-class="opacity-0"
      enter-to-class="opacity-100"
      leave-active-class="transition duration-200 ease-in"
      leave-from-class="opacity-100"
      leave-to-class="opacity-0"
    >
      <div
        v-if="visible"
        class="fixed inset-0 z-50 overflow-y-auto"
        @click.self="handleClose"
      >
        <div class="flex min-h-full items-end justify-center p-4 text-center sm:items-center sm:p-0">
          <!-- Background overlay -->
          <div class="fixed inset-0 bg-gray-500 bg-opacity-75 transition-opacity"></div>

          <!-- Modal panel -->
          <div
            @click.stop
            class="relative transform overflow-hidden rounded-lg bg-white px-4 pb-4 pt-5 text-left shadow-xl transition-all sm:my-8 sm:w-full sm:max-w-2xl sm:p-6"
          >
            <!-- Header -->
            <div class="flex items-center justify-between border-b border-gray-200 pb-3 mb-4">
              <div class="flex items-center space-x-3">
                <div
                  :class="{
                    'bg-blue-100': deployment?.status === 'running' || deployment?.status === 'pending',
                    'bg-green-100': deployment?.status === 'success',
                    'bg-red-100': deployment?.status === 'failed'
                  }"
                  class="w-10 h-10 rounded-full flex items-center justify-center"
                >
                  <svg
                    v-if="deployment?.status === 'running' || deployment?.status === 'pending'"
                    class="animate-spin h-5 w-5 text-blue-600"
                    fill="none"
                    viewBox="0 0 24 24"
                  >
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  <svg
                    v-else-if="deployment?.status === 'success'"
                    class="h-5 w-5 text-green-600"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>
                  </svg>
                  <svg
                    v-else-if="deployment?.status === 'failed'"
                    class="h-5 w-5 text-red-600"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                  </svg>
                </div>
                <div>
                  <h3 class="text-lg font-medium text-gray-900">Deployment Progress</h3>
                  <p class="text-sm text-gray-500">
                    {{ deployment?.playbook || 'default.yml' }} - {{ deployment?.host_ids?.length || 0 }} host(s)
                  </p>
                </div>
              </div>
              <button
                @click="handleClose"
                :disabled="deployment?.status === 'running' && !allowClose"
                class="rounded-md text-gray-400 hover:text-gray-600 focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <svg class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <!-- Status Banner -->
            <div
              v-if="deployment"
              :class="{
                'bg-blue-50 border-blue-200': deployment.status === 'running' || deployment.status === 'pending',
                'bg-green-50 border-green-200': deployment.status === 'success',
                'bg-red-50 border-red-200': deployment.status === 'failed'
              }"
              class="rounded-lg border p-3 mb-4"
            >
              <div class="flex items-center justify-between">
                <div>
                  <p
                    :class="{
                      'text-blue-800': deployment.status === 'running' || deployment.status === 'pending',
                      'text-green-800': deployment.status === 'success',
                      'text-red-800': deployment.status === 'failed'
                    }"
                    class="font-medium"
                  >
                    {{ getStatusText(deployment.status) }}
                  </p>
                  <p class="text-sm text-gray-600">
                    {{ formatTimestamp(deployment.started_at) }}
                    <span v-if="deployment.completed_at"> - {{ formatTimestamp(deployment.completed_at) }}</span>
                  </p>
                </div>
                <div v-if="deployment.status === 'running'" class="text-blue-600">
                  <svg class="animate-pulse h-8 w-8" fill="currentColor" viewBox="0 0 20 20">
                    <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-11a1 1 0 10-2 0v2H7a1 1 0 100 2h2v2a1 1 0 102 0v-2h2a1 1 0 100-2h-2V7z" clip-rule="evenodd"></path>
                  </svg>
                </div>
              </div>
            </div>

            <!-- Logs -->
            <div class="mb-4">
              <h4 class="text-sm font-medium text-gray-900 mb-2">Deployment Logs</h4>
              <div
                ref="logsContainer"
                class="bg-gray-900 text-gray-100 rounded-lg p-4 h-64 overflow-y-auto font-mono text-sm"
              >
                <div v-if="logs.length === 0" class="text-gray-400">
                  Waiting for logs...
                </div>
                <div v-else>
                  <div
                    v-for="(log, index) in logs"
                    :key="index"
                    class="mb-1"
                  >
                    <span class="text-gray-500">[{{ formatLogTime(log.timestamp) }}]</span>
                    <span
                      :class="{
                        'text-green-400': log.level === 'success',
                        'text-yellow-400': log.level === 'warning',
                        'text-red-400': log.level === 'error',
                        'text-gray-100': !log.level || log.level === 'info'
                      }"
                    >
                      {{ log.message }}
                    </span>
                  </div>
                </div>
              </div>
            </div>

            <!-- Actions -->
            <div class="flex items-center justify-between pt-4 border-t border-gray-100">
              <button
                @click="refreshLogs"
                class="inline-flex items-center px-3 py-2 border border-gray-300 shadow-sm text-sm leading-4 font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
              >
                <svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path>
                </svg>
                Refresh
              </button>
              <button
                @click="handleClose"
                class="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
              >
                {{ deployment?.status === 'running' ? 'Close (Running in Background)' : 'Close' }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, defineProps, defineEmits, watch, nextTick } from 'vue'
import type { Deployment } from '@/composables/useInfrastructure'
import { formatDateTime, formatTime } from '@/utils/formatHelpers'

const props = defineProps<{
  visible: boolean
  deployment: Deployment | null
  allowClose?: boolean
}>()

const emit = defineEmits<{
  close: []
  refresh: []
}>()

const logs = ref<Array<{ timestamp: string; level?: string; message: string }>>([])
const logsContainer = ref<HTMLDivElement>()

// Watch for deployment changes and update logs
watch(() => props.deployment?.logs, (newLogs) => {
  if (newLogs && Array.isArray(newLogs)) {
    logs.value = newLogs.map(log => {
      if (typeof log === 'string') {
        return {
          timestamp: new Date().toISOString(),
          message: log
        }
      }
      return log
    })
    scrollToBottom()
  }
}, { deep: true, immediate: true })

function getStatusText(status?: string): string {
  switch (status) {
    case 'pending':
      return 'Pending - Queued for deployment'
    case 'running':
      return 'Running - Deployment in progress'
    case 'success':
      return 'Success - Deployment completed successfully'
    case 'failed':
      return 'Failed - Deployment encountered errors'
    default:
      return 'Unknown status'
  }
}

// Use shared format utilities instead of duplicating
const formatTimestamp = (timestamp?: string) => formatDateTime(timestamp)
const formatLogTime = (timestamp?: string) => formatTime(timestamp)

function scrollToBottom() {
  nextTick(() => {
    if (logsContainer.value) {
      logsContainer.value.scrollTop = logsContainer.value.scrollHeight
    }
  })
}

function refreshLogs() {
  emit('refresh')
}

function handleClose() {
  if (props.deployment?.status === 'running' && !props.allowClose) {
    // Warn user that deployment is still running
    if (confirm('Deployment is still running. Close anyway? (It will continue in the background)')) {
      emit('close')
    }
  } else {
    emit('close')
  }
}
</script>
