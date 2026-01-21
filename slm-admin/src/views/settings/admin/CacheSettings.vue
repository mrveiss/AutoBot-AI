// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

<script setup lang="ts">
/**
 * CacheSettings - Cache Management Component
 *
 * Migrated from main AutoBot frontend for Issue #729.
 * Provides cache configuration, Redis database management, and cache statistics.
 */

import { ref, reactive, computed, onMounted } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { useAutobotApi, type CacheConfig, type CacheStats } from '@/composables/useAutobotApi'

const authStore = useAuthStore()
const api = useAutobotApi()

// State
const loading = ref(false)
const saving = ref(false)
const clearing = ref(false)
const error = ref<string | null>(null)
const success = ref<string | null>(null)
const cacheApiAvailable = ref(false)

// Cache configuration
const cacheConfig = reactive<CacheConfig>({
  enabled: true,
  ttl_seconds: 3600,
  max_size_mb: 100,
  eviction_policy: 'lru',
})

// Cache statistics
const cacheStats = ref<CacheStats | null>(null)

// Redis database info
interface RedisDbInfo {
  database: number
  key_count: number
  memory_usage: string
  connected: boolean
}

const redisStats = ref<Record<string, RedisDbInfo>>({})

// Cache activity log
interface CacheActivity {
  id: string
  timestamp: string
  operation: string
  key?: string
  result: string
}

const cacheActivity = ref<CacheActivity[]>([])

// Computed
const hitRate = computed(() => {
  if (!cacheStats.value) return 0
  const total = cacheStats.value.hits + cacheStats.value.misses
  if (total === 0) return 0
  return (cacheStats.value.hits / total) * 100
})

// Methods
async function checkCacheApiAvailability(): Promise<void> {
  try {
    const response = await api.getCacheStats()
    cacheApiAvailable.value = response.status === 200
  } catch {
    cacheApiAvailable.value = false
  }
}

async function fetchCacheConfig(): Promise<void> {
  loading.value = true
  error.value = null

  try {
    const response = await api.getCacheConfig()
    if (response.data) {
      Object.assign(cacheConfig, response.data)
    }
  } catch (e) {
    // Cache API may not be available
    cacheApiAvailable.value = false
  } finally {
    loading.value = false
  }
}

async function fetchCacheStats(): Promise<void> {
  try {
    const response = await api.getCacheStats()
    cacheStats.value = response.data

    // Extract Redis stats if available
    if (response.data?.redis_databases) {
      redisStats.value = response.data.redis_databases
    }
  } catch (e) {
    // Silently fail - stats may not be available
  }
}

async function saveCacheConfig(): Promise<void> {
  saving.value = true
  error.value = null

  try {
    await api.updateCacheConfig(cacheConfig)
    success.value = 'Cache configuration saved successfully'
    setTimeout(() => { success.value = null }, 3000)
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to save cache configuration'
  } finally {
    saving.value = false
  }
}

async function clearCache(type: string = 'all'): Promise<void> {
  if (!confirm(`Are you sure you want to clear the ${type} cache?`)) return

  clearing.value = true
  error.value = null

  try {
    await api.clearCache(type)
    success.value = `${formatCacheType(type)} cache cleared successfully`
    await fetchCacheStats()
    setTimeout(() => { success.value = null }, 3000)
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to clear cache'
  } finally {
    clearing.value = false
  }
}

async function clearRedisCache(database: string): Promise<void> {
  if (!confirm(`Are you sure you want to clear the ${database} Redis database?`)) return

  clearing.value = true
  error.value = null

  try {
    await fetch(`/autobot-api/cache/redis/clear/${database}`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${authStore.token}`,
      },
    })
    success.value = `Redis ${database} database cleared successfully`
    await fetchCacheStats()
    setTimeout(() => { success.value = null }, 3000)
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to clear Redis database'
  } finally {
    clearing.value = false
  }
}

async function warmupCaches(): Promise<void> {
  clearing.value = true
  error.value = null

  try {
    await api.warmupCache()
    success.value = 'Cache warmup completed successfully'
    await fetchCacheStats()
    setTimeout(() => { success.value = null }, 3000)
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to warm up caches'
  } finally {
    clearing.value = false
  }
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

function formatCacheType(type: string): string {
  return type.charAt(0).toUpperCase() + type.slice(1)
}

function formatDbName(name: string): string {
  return name.charAt(0).toUpperCase() + name.slice(1)
}

// Initialize
onMounted(async () => {
  await checkCacheApiAvailability()
  if (cacheApiAvailable.value) {
    await Promise.all([
      fetchCacheConfig(),
      fetchCacheStats(),
    ])
  }
})
</script>

<template>
  <div class="p-6 space-y-6">
    <!-- Messages -->
    <div v-if="error" class="p-4 bg-red-50 border border-red-200 rounded-lg text-red-700 flex items-center gap-3">
      <svg class="w-5 h-5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
      {{ error }}
      <button @click="error = null" class="ml-auto text-red-500 hover:text-red-700">
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>

    <div v-if="success" class="p-4 bg-green-50 border border-green-200 rounded-lg text-green-700 flex items-center gap-3">
      <svg class="w-5 h-5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
      {{ success }}
    </div>

    <!-- Cache API Unavailable Warning -->
    <div v-if="!cacheApiAvailable && !loading" class="bg-yellow-50 border border-yellow-200 rounded-lg p-6">
      <div class="flex gap-4">
        <svg class="w-6 h-6 text-yellow-500 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
        </svg>
        <div>
          <h3 class="font-semibold text-yellow-800">Cache API Unavailable</h3>
          <p class="text-yellow-700 mt-1">
            The cache management API is not available in the current backend configuration.
            Cache features are disabled to prevent errors.
          </p>
          <p class="text-sm text-yellow-600 mt-2">
            This is normal when using the fast backend for development.
            Cache functionality would be available in the full backend configuration.
          </p>
        </div>
      </div>

      <!-- Alternative Info -->
      <div class="mt-6 space-y-3">
        <h4 class="font-medium text-yellow-800">Alternative Cache Information</h4>
        <div class="grid gap-3">
          <div class="flex items-start gap-3 p-3 bg-white/50 rounded-lg">
            <svg class="w-5 h-5 text-yellow-600 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <div class="text-sm text-yellow-700">
              <strong>Browser Cache:</strong> Your browser is still caching API responses and static assets automatically.
            </div>
          </div>
          <div class="flex items-start gap-3 p-3 bg-white/50 rounded-lg">
            <svg class="w-5 h-5 text-yellow-600 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4" />
            </svg>
            <div class="text-sm text-yellow-700">
              <strong>Redis Cache:</strong> Redis databases are still operational for session storage and data persistence.
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="flex items-center justify-center py-12">
      <svg class="animate-spin w-8 h-8 text-primary-600" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
      </svg>
    </div>

    <template v-if="cacheApiAvailable && !loading">
      <!-- Cache Configuration -->
      <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        <h2 class="text-lg font-semibold text-gray-900 mb-4">Cache Configuration</h2>

        <div class="space-y-4">
          <!-- Enable Caching -->
          <div class="flex items-center justify-between pb-4 border-b border-gray-100">
            <div>
              <label class="block text-sm font-medium text-gray-900">Enable Caching</label>
              <p class="text-xs text-gray-500 mt-1">Turn caching on or off globally</p>
            </div>
            <label class="relative inline-flex items-center cursor-pointer">
              <input type="checkbox" v-model="cacheConfig.enabled" class="sr-only peer" />
              <div class="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-primary-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary-600"></div>
            </label>
          </div>

          <!-- Default TTL -->
          <div class="flex items-center justify-between pb-4 border-b border-gray-100">
            <div>
              <label class="block text-sm font-medium text-gray-900">Default TTL</label>
              <p class="text-xs text-gray-500 mt-1">Time to live in seconds (10-86400)</p>
            </div>
            <input
              v-model.number="cacheConfig.ttl_seconds"
              type="number"
              min="10"
              max="86400"
              class="w-32 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
            />
          </div>

          <!-- Max Cache Size -->
          <div class="flex items-center justify-between pb-4 border-b border-gray-100">
            <div>
              <label class="block text-sm font-medium text-gray-900">Max Cache Size</label>
              <p class="text-xs text-gray-500 mt-1">Maximum size in MB (10-1000)</p>
            </div>
            <input
              v-model.number="cacheConfig.max_size_mb"
              type="number"
              min="10"
              max="1000"
              class="w-32 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
            />
          </div>

          <!-- Eviction Policy -->
          <div class="flex items-center justify-between">
            <div>
              <label class="block text-sm font-medium text-gray-900">Eviction Policy</label>
              <p class="text-xs text-gray-500 mt-1">How to remove items when cache is full</p>
            </div>
            <select
              v-model="cacheConfig.eviction_policy"
              class="w-40 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
            >
              <option value="lru">LRU (Least Recently Used)</option>
              <option value="lfu">LFU (Least Frequently Used)</option>
              <option value="fifo">FIFO (First In First Out)</option>
            </select>
          </div>
        </div>

        <div class="mt-6 flex justify-end">
          <button
            @click="saveCacheConfig"
            :disabled="saving"
            class="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50 flex items-center gap-2"
          >
            <svg v-if="saving" class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            <svg v-else class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
            </svg>
            Save Configuration
          </button>
        </div>
      </div>

      <!-- Cache Statistics -->
      <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        <div class="flex items-center justify-between mb-4">
          <h2 class="text-lg font-semibold text-gray-900">Cache Statistics</h2>
          <button
            @click="fetchCacheStats"
            class="px-3 py-1.5 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 flex items-center gap-2 text-sm"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            Refresh
          </button>
        </div>

        <div v-if="cacheStats" class="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div class="p-4 bg-gray-50 rounded-lg">
            <p class="text-sm text-gray-500">Total Entries</p>
            <p class="text-2xl font-semibold text-gray-900">{{ cacheStats.entries || 0 }}</p>
          </div>
          <div class="p-4 bg-gray-50 rounded-lg">
            <p class="text-sm text-gray-500">Cache Size</p>
            <p class="text-2xl font-semibold text-gray-900">{{ formatBytes((cacheStats.size_mb || 0) * 1024 * 1024) }}</p>
          </div>
          <div class="p-4 bg-gray-50 rounded-lg">
            <p class="text-sm text-gray-500">Hit Rate</p>
            <p class="text-2xl font-semibold" :class="hitRate >= 80 ? 'text-green-600' : hitRate >= 50 ? 'text-yellow-600' : 'text-red-600'">
              {{ hitRate.toFixed(1) }}%
            </p>
          </div>
          <div class="p-4 bg-gray-50 rounded-lg">
            <p class="text-sm text-gray-500">Cache Hits</p>
            <p class="text-2xl font-semibold text-primary-600">{{ cacheStats.hits || 0 }}</p>
          </div>
        </div>

        <div v-else class="text-center py-8 text-gray-500">
          No statistics available
        </div>
      </div>

      <!-- Redis Database Caches -->
      <div class="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
        <div class="p-4 bg-gray-50 border-b border-gray-200">
          <h2 class="text-lg font-semibold text-gray-900">Redis Database Caches</h2>
        </div>

        <div class="p-6">
          <div v-if="Object.keys(redisStats).length > 0" class="grid md:grid-cols-2 gap-4">
            <div
              v-for="(dbInfo, dbName) in redisStats"
              :key="dbName"
              class="flex items-center justify-between p-4 bg-gray-50 rounded-lg border border-gray-200"
            >
              <div>
                <h3 class="font-medium text-gray-900">{{ formatDbName(String(dbName)) }} (DB {{ dbInfo.database }})</h3>
                <div class="flex items-center gap-3 mt-2 text-sm">
                  <span class="text-gray-600">{{ dbInfo.key_count || 0 }} keys</span>
                  <span class="text-gray-400">|</span>
                  <span class="text-gray-600">{{ dbInfo.memory_usage || '0B' }}</span>
                  <span
                    :class="[
                      'px-2 py-0.5 rounded-full text-xs font-medium',
                      dbInfo.connected ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700',
                    ]"
                  >
                    {{ dbInfo.connected ? 'Connected' : 'Disconnected' }}
                  </span>
                </div>
              </div>
              <button
                @click="clearRedisCache(String(dbName))"
                :disabled="clearing || !dbInfo.connected"
                class="px-3 py-1.5 bg-red-500 text-white rounded-lg hover:bg-red-600 disabled:opacity-50 text-sm flex items-center gap-1"
              >
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
                Clear
              </button>
            </div>
          </div>

          <div v-else class="text-center py-8 text-gray-500">
            No Redis databases available
          </div>

          <!-- Clear All Redis -->
          <div class="mt-4 pt-4 border-t border-gray-200 text-center">
            <button
              @click="clearRedisCache('all')"
              :disabled="clearing"
              class="px-4 py-2 bg-red-500 text-white rounded-lg hover:bg-red-600 disabled:opacity-50 flex items-center gap-2 mx-auto"
            >
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4" />
              </svg>
              Clear All Redis Databases
            </button>
          </div>
        </div>
      </div>

      <!-- Application Caches -->
      <div class="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
        <div class="p-4 bg-gray-50 border-b border-gray-200">
          <h2 class="text-lg font-semibold text-gray-900">Application Caches</h2>
        </div>

        <div class="p-6">
          <div class="flex flex-wrap gap-3">
            <button
              @click="clearCache('knowledge')"
              :disabled="clearing"
              class="px-4 py-2 bg-purple-500 text-white rounded-lg hover:bg-purple-600 disabled:opacity-50 flex items-center gap-2"
            >
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
              </svg>
              Clear Knowledge Cache
            </button>

            <button
              @click="clearCache('llm')"
              :disabled="clearing"
              class="px-4 py-2 bg-teal-500 text-white rounded-lg hover:bg-teal-600 disabled:opacity-50 flex items-center gap-2"
            >
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
              </svg>
              Clear LLM Cache
            </button>

            <button
              @click="clearCache('config')"
              :disabled="clearing"
              class="px-4 py-2 bg-orange-500 text-white rounded-lg hover:bg-orange-600 disabled:opacity-50 flex items-center gap-2"
            >
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
              Clear Config Cache
            </button>
          </div>

          <!-- Cache Actions -->
          <div class="mt-6 pt-4 border-t border-gray-200 flex gap-3">
            <button
              @click="fetchCacheStats"
              class="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 flex items-center gap-2"
            >
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
              Refresh Stats
            </button>
            <button
              @click="warmupCaches"
              :disabled="clearing"
              class="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50 flex items-center gap-2"
            >
              <svg v-if="clearing" class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              <svg v-else class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17.657 18.657A8 8 0 016.343 7.343S7 9 9 10c0-2 .5-5 2.986-7C14 5 16.09 5.777 17.656 7.343A7.975 7.975 0 0120 13a7.975 7.975 0 01-2.343 5.657z" />
              </svg>
              Warm Up Caches
            </button>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
