<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * ServiceLogsModal - the journal tail of one service on one node.
 *
 * Extracted from NodeServicesPanel (#16245) so the Redis panel shows the same
 * view. Open while `serviceName` is set; fetches
 * GET /nodes/{nodeId}/services/{serviceName}/logs each time it opens.
 */

import { ref, watch } from 'vue'
import { useSlmApi } from '@/composables/useSlmApi'
import { createLogger } from '@/utils/debugUtils'

const props = withDefaults(
  defineProps<{
    nodeId: string
    serviceName: string | null
    lines?: number
  }>(),
  { lines: 100 },
)

const emit = defineEmits<{ close: [] }>()

const api = useSlmApi()
const logger = createLogger('ServiceLogsModal')

const logsContent = ref('')
const isLoading = ref(false)
const loadFailed = ref(false)

async function loadLogs(serviceName: string): Promise<void> {
  logsContent.value = ''
  loadFailed.value = false
  isLoading.value = true
  try {
    const response = await api.getServiceLogs(props.nodeId, serviceName, { lines: props.lines })
    logsContent.value = response.logs
  } catch (error) {
    logger.error('Failed to fetch logs:', error)
    loadFailed.value = true
  } finally {
    isLoading.value = false
  }
}

watch(
  () => props.serviceName,
  (serviceName) => {
    if (serviceName) loadLogs(serviceName)
  },
  { immediate: true },
)
</script>

<template>
  <teleport to="body">
    <div v-if="serviceName" class="fixed inset-0 z-50 flex items-center justify-center p-4">
      <!-- Backdrop -->
      <div class="absolute inset-0 bg-black/50" @click="emit('close')"></div>

      <!-- Modal -->
      <div class="relative bg-white rounded-lg shadow-xl max-w-4xl w-full max-h-[80vh] flex flex-col">
        <!-- Header -->
        <div class="flex items-center justify-between px-4 py-3 border-b border-gray-200">
          <h3 class="text-lg font-semibold text-gray-900">{{ $t('fleet.serviceLogsModal.title', { service: serviceName }) }}</h3>
          <button
            @click="emit('close')"
            class="text-gray-400 hover:text-gray-600 transition-colors"
            :aria-label="$t('fleet.serviceLogsModal.close')"
          >
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <!-- Content -->
        <div class="flex-1 overflow-auto p-4 bg-gray-900">
          <div v-if="isLoading" class="flex items-center justify-center py-12 text-gray-400">
            <svg class="w-6 h-6 animate-spin mr-2" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
            </svg>
            {{ $t('fleet.serviceLogsModal.loading') }}
          </div>
          <p v-else-if="loadFailed" class="text-sm text-red-300">{{ $t('fleet.serviceLogsModal.loadFailed') }}</p>
          <pre v-else class="text-sm text-green-400 font-mono whitespace-pre-wrap">{{ logsContent }}</pre>
        </div>

        <!-- Footer -->
        <div class="px-4 py-3 border-t border-gray-200 flex justify-end">
          <button
            @click="emit('close')"
            class="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50"
          >
            {{ $t('fleet.serviceLogsModal.close') }}
          </button>
        </div>
      </div>
    </div>
  </teleport>
</template>
