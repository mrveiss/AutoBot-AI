<template>
  <div class="p-6 max-w-7xl mx-auto">
    <div class="flex items-center justify-between mb-6">
      <h1 class="text-2xl font-bold text-gray-900 dark:text-white">
        LLM Providers & Fallback Status
      </h1>
      <button
        class="btn-primary flex items-center gap-2"
        @click="fetchFallbackStatus"
        :disabled="loading"
      >
        <svg
          class="w-4 h-4"
          :class="{ 'animate-spin': loading }"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            stroke-width="2"
            d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
          />
        </svg>
        Refresh
      </button>
    </div>

    <!-- Error display -->
    <div
      v-if="error"
      class="mb-4 p-4 bg-red-50 dark:bg-red-900/20 border border-red-300 dark:border-red-700 rounded-lg"
    >
      <p class="text-sm font-semibold text-red-800 dark:text-red-200">
        {{ error }}
      </p>
    </div>

    <!-- Configured Fallback Chains Section -->
    <div class="mb-8">
      <h2 class="text-xl font-semibold text-gray-900 dark:text-white mb-4">
        Configured Fallback Chains
      </h2>
      <div class="bg-white dark:bg-gray-800 rounded-lg shadow overflow-x-auto">
        <table class="w-full text-sm">
          <thead class="bg-gray-50 dark:bg-gray-700 text-gray-500 dark:text-gray-400 uppercase text-xs">
            <tr>
              <th class="px-4 py-3 text-left">Primary Model</th>
              <th class="px-4 py-3 text-left">Fallback Chain</th>
              <th class="px-4 py-3 text-left">Provider</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-100 dark:divide-gray-700">
            <tr v-if="loading && configuredChains.length === 0">
              <td colspan="3" class="px-4 py-8 text-center text-gray-400">
                Loading...
              </td>
            </tr>
            <tr v-else-if="configuredChains.length === 0">
              <td colspan="3" class="px-4 py-8 text-center text-gray-400">
                No fallback chains configured
              </td>
            </tr>
            <tr
              v-for="chain in configuredChains"
              :key="chain.primary_model"
              class="hover:bg-gray-50 dark:hover:bg-gray-750"
            >
              <td class="px-4 py-3 font-mono text-xs">
                {{ chain.primary_model }}
              </td>
              <td class="px-4 py-3 text-gray-600 dark:text-gray-300">
                {{ chain.fallback_chain }}
              </td>
              <td class="px-4 py-3">
                <span
                  class="px-2 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400"
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
        <h2 class="text-xl font-semibold text-gray-900 dark:text-white">
          Active Fallbacks
        </h2>
        <span class="text-sm text-gray-500 dark:text-gray-400">
          Auto-refreshes every 10s
        </span>
      </div>
      <div class="bg-white dark:bg-gray-800 rounded-lg shadow overflow-x-auto">
        <table class="w-full text-sm">
          <thead class="bg-gray-50 dark:bg-gray-700 text-gray-500 dark:text-gray-400 uppercase text-xs">
            <tr>
              <th class="px-4 py-3 text-left">Conversation ID</th>
              <th class="px-4 py-3 text-left">Primary Model</th>
              <th class="px-4 py-3 text-left">Fallback Model</th>
              <th class="px-4 py-3 text-left">Primary Provider</th>
              <th class="px-4 py-3 text-left">Fallback Provider</th>
              <th class="px-4 py-3 text-left">Time</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-100 dark:divide-gray-700">
            <tr v-if="loading && activeFallbacks.length === 0">
              <td colspan="6" class="px-4 py-8 text-center text-gray-400">
                Loading...
              </td>
            </tr>
            <tr v-else-if="activeFallbacks.length === 0">
              <td colspan="6" class="px-4 py-8 text-center text-gray-400">
                No active fallbacks (all models operating normally)
              </td>
            </tr>
            <tr
              v-for="(fallback, index) in activeFallbacks"
              :key="`${fallback.conversation_id}-${fallback.timestamp}-${index}`"
              class="hover:bg-gray-50 dark:hover:bg-gray-750"
            >
              <td class="px-4 py-3 font-mono text-xs">
                {{ fallback.conversation_id }}
              </td>
              <td class="px-4 py-3 font-mono text-xs text-red-600 dark:text-red-400">
                {{ fallback.primary_model }}
              </td>
              <td class="px-4 py-3 font-mono text-xs text-green-600 dark:text-green-400">
                {{ fallback.fallback_model }}
              </td>
              <td class="px-4 py-3">
                <span
                  class="px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300"
                >
                  {{ fallback.primary_provider }}
                </span>
              </td>
              <td class="px-4 py-3">
                <span
                  class="px-2 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400"
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

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { getBackendUrl } from '@/config/ssot-config'

interface FallbackChain {
  primary_model: string
  fallback_chain: string
  provider: string
}

interface ActiveFallback {
  conversation_id: string
  primary_model: string
  fallback_model: string
  primary_provider: string
  fallback_provider: string
  timestamp: number
}

const configuredChains = ref<FallbackChain[]>([])
const activeFallbacks = ref<ActiveFallback[]>([])
const loading = ref(false)
const error = ref('')
let refreshInterval: number | null = null

const fetchFallbackStatus = async () => {
  loading.value = true
  error.value = ''

  try {
    const response = await fetch(`${getBackendUrl()}/api/llm-providers/fallback-status`, {
      credentials: 'include',
    })

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`)
    }

    const data = await response.json()
    configuredChains.value = data.configured_chains || []
    activeFallbacks.value = data.active_fallbacks || []
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Failed to fetch fallback status'
    console.error('Error fetching fallback status:', err)
  } finally {
    loading.value = false
  }
}

const formatTime = (timestamp: number): string => {
  const date = new Date(timestamp * 1000)
  const now = new Date()
  const diffSeconds = Math.floor((now.getTime() - date.getTime()) / 1000)

  if (diffSeconds < 60) {
    return `${diffSeconds}s ago`
  } else if (diffSeconds < 3600) {
    return `${Math.floor(diffSeconds / 60)}m ago`
  } else {
    return date.toLocaleTimeString()
  }
}

onMounted(() => {
  fetchFallbackStatus()
  // Auto-refresh every 10 seconds
  refreshInterval = window.setInterval(fetchFallbackStatus, 10000)
})

onUnmounted(() => {
  if (refreshInterval) {
    clearInterval(refreshInterval)
  }
})
</script>

<style scoped>
@reference "../assets/tailwind.css";

.btn-primary {
  @apply px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed;
}
</style>
