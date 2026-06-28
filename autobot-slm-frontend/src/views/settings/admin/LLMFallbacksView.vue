// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

<script setup lang="ts">
/**
 * LLMFallbacksView - LLM Fallback Monitoring (GH#8998 / #10488).
 *
 * Operator observability: which models fall back to which (configured chains)
 * and which fallbacks are currently active. Moved from the user frontend
 * (LLMProvidersView) into the SLM operator console. Provider CONFIG lives in
 * the separate LLMSettings admin view and is not duplicated here.
 *
 * Reads the main AutoBot backend via the /autobot-api proxy
 * (-> /api/llm-providers/fallback-status).
 */

import { ref, onMounted, onUnmounted } from 'vue'
import {
  useAutobotApi,
  type LLMFallbackChain,
  type LLMActiveFallback,
} from '@/composables/useAutobotApi'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('LLMFallbacksView')
const api = useAutobotApi()

// Auto-refresh interval for active fallbacks (ms).
const REFRESH_INTERVAL_MS = 10000

const configuredChains = ref<LLMFallbackChain[]>([])
const activeFallbacks = ref<LLMActiveFallback[]>([])
const loading = ref(false)
const error = ref('')
let refreshTimer: number | null = null

async function fetchFallbackStatus(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const data = await api.getLLMFallbackStatus()
    configuredChains.value = data.configured_chains
    activeFallbacks.value = data.active_fallbacks
  } catch (err) {
    error.value =
      err instanceof Error ? err.message : 'Failed to fetch fallback status'
    logger.error('Error fetching fallback status:', err)
  } finally {
    loading.value = false
  }
}

function formatTime(timestamp: number): string {
  const date = new Date(timestamp * 1000)
  const now = new Date()
  const diffSeconds = Math.floor((now.getTime() - date.getTime()) / 1000)
  if (diffSeconds < 60) {
    return `${diffSeconds}s ago`
  } else if (diffSeconds < 3600) {
    return `${Math.floor(diffSeconds / 60)}m ago`
  }
  return date.toLocaleTimeString()
}

onMounted(() => {
  fetchFallbackStatus()
  refreshTimer = window.setInterval(fetchFallbackStatus, REFRESH_INTERVAL_MS)
})

onUnmounted(() => {
  if (refreshTimer !== null) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
})
</script>

<template>
  <div class="p-6 max-w-7xl mx-auto">
    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-2xl font-bold text-gray-900">
          {{ $t('llmFallbacks.title') }}
        </h1>
        <p class="text-sm text-gray-500 mt-1">
          {{ $t('llmFallbacks.subtitle') }}
        </p>
      </div>
      <button
        class="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
        :disabled="loading"
        @click="fetchFallbackStatus"
      >
        <svg
          class="w-4 h-4"
          :class="{ 'animate-spin': loading }"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          aria-hidden="true"
        >
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            stroke-width="2"
            d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
          />
        </svg>
        {{ $t('llmFallbacks.refresh') }}
      </button>
    </div>

    <!-- Error display -->
    <div
      v-if="error"
      class="mb-4 p-4 bg-red-50 border border-red-200 rounded-lg"
      role="alert"
    >
      <p class="text-sm font-semibold text-red-700">{{ error }}</p>
    </div>

    <!-- Configured Fallback Chains Section -->
    <div class="mb-8">
      <h2 class="text-xl font-semibold text-gray-900 mb-4">
        {{ $t('llmFallbacks.configuredChains') }}
      </h2>
      <div class="bg-white rounded-lg shadow overflow-x-auto">
        <table class="w-full text-sm">
          <thead class="bg-gray-50 text-gray-500 uppercase text-xs">
            <tr>
              <th class="px-4 py-3 text-left">{{ $t('llmFallbacks.primaryModel') }}</th>
              <th class="px-4 py-3 text-left">{{ $t('llmFallbacks.fallbackChain') }}</th>
              <th class="px-4 py-3 text-left">{{ $t('llmFallbacks.provider') }}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-100">
            <tr v-if="loading && configuredChains.length === 0">
              <td colspan="3" class="px-4 py-8 text-center text-gray-400">
                {{ $t('llmFallbacks.loading') }}
              </td>
            </tr>
            <tr v-else-if="configuredChains.length === 0">
              <td colspan="3" class="px-4 py-8 text-center text-gray-400">
                {{ $t('llmFallbacks.noChains') }}
              </td>
            </tr>
            <tr
              v-for="chain in configuredChains"
              :key="chain.primary_model"
              class="hover:bg-gray-50"
            >
              <td class="px-4 py-3 font-mono text-xs">{{ chain.primary_model }}</td>
              <td class="px-4 py-3 text-gray-600">{{ chain.fallback_chain }}</td>
              <td class="px-4 py-3">
                <span
                  class="px-2 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-700"
                >
                  {{ chain.provider }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Active Fallbacks Section -->
    <div>
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-xl font-semibold text-gray-900">
          {{ $t('llmFallbacks.activeFallbacks') }}
        </h2>
        <span class="text-sm text-gray-500">
          {{ $t('llmFallbacks.autoRefresh') }}
        </span>
      </div>
      <div class="bg-white rounded-lg shadow overflow-x-auto">
        <table class="w-full text-sm">
          <thead class="bg-gray-50 text-gray-500 uppercase text-xs">
            <tr>
              <th class="px-4 py-3 text-left">{{ $t('llmFallbacks.conversationId') }}</th>
              <th class="px-4 py-3 text-left">{{ $t('llmFallbacks.primaryModel') }}</th>
              <th class="px-4 py-3 text-left">{{ $t('llmFallbacks.fallbackModel') }}</th>
              <th class="px-4 py-3 text-left">{{ $t('llmFallbacks.primaryProvider') }}</th>
              <th class="px-4 py-3 text-left">{{ $t('llmFallbacks.fallbackProvider') }}</th>
              <th class="px-4 py-3 text-left">{{ $t('llmFallbacks.time') }}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-100">
            <tr v-if="loading && activeFallbacks.length === 0">
              <td colspan="6" class="px-4 py-8 text-center text-gray-400">
                {{ $t('llmFallbacks.loading') }}
              </td>
            </tr>
            <tr v-else-if="activeFallbacks.length === 0">
              <td colspan="6" class="px-4 py-8 text-center text-gray-400">
                {{ $t('llmFallbacks.noActiveFallbacks') }}
              </td>
            </tr>
            <tr
              v-for="(fallback, index) in activeFallbacks"
              :key="`${fallback.conversation_id}-${fallback.timestamp}-${index}`"
              class="hover:bg-gray-50"
            >
              <td class="px-4 py-3 font-mono text-xs">{{ fallback.conversation_id }}</td>
              <td class="px-4 py-3 font-mono text-xs text-red-600">
                {{ fallback.primary_model }}
              </td>
              <td class="px-4 py-3 font-mono text-xs text-green-600">
                {{ fallback.fallback_model }}
              </td>
              <td class="px-4 py-3">
                <span
                  class="px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-700"
                >
                  {{ fallback.primary_provider }}
                </span>
              </td>
              <td class="px-4 py-3">
                <span
                  class="px-2 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-700"
                >
                  {{ fallback.fallback_provider }}
                </span>
              </td>
              <td class="px-4 py-3 text-xs text-gray-500">
                {{ formatTime(fallback.timestamp) }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
