// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

<script setup lang="ts">
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('MCPTool')
/**
 * MCPTool - MCP Registry Manager
 *
 * Manage and monitor AutoBot's Model Context Protocol (MCP) tools and bridges.
 * Migrated from main AutoBot frontend - Issue #729.
 */

import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useAutobotApi } from '@/composables/useAutobotApi'

const api = useAutobotApi()

// State
const activeTab = ref<'bridges' | 'tools' | 'health'>('bridges')
const loading = ref(false)
const isRefreshing = ref(false)

interface MCPBridge {
  name: string
  description: string
  status: 'healthy' | 'degraded' | 'error'
  tool_count: number
  features: string[]
  endpoint: string
  error?: string
}

interface MCPTool {
  name: string
  description: string
  bridge: string
  endpoint: string
  input_schema: Record<string, unknown>
}

interface HealthCheck {
  bridge: string
  status: 'healthy' | 'degraded' | 'error'
  response_time_ms: number
  tool_count?: number
  error?: string
}

interface HealthData {
  status: string
  checks: HealthCheck[]
  timestamp: string
}

interface MCPStats {
  total_tools: number
  total_bridges: number
  healthy_bridges: number
}

const bridges = ref<MCPBridge[]>([])
const tools = ref<MCPTool[]>([])
const healthData = ref<HealthData>({ status: 'unknown', checks: [], timestamp: '' })
const stats = ref<MCPStats>({ total_tools: 0, total_bridges: 0, healthy_bridges: 0 })
const toolFilter = ref('')
const expandedTools = ref<Set<string>>(new Set())
const lastUpdated = ref<Date | null>(null)
// Issue #986: track load errors so we can show them instead of empty state
const loadError = ref<string | null>(null)

let refreshInterval: ReturnType<typeof setInterval> | null = null
// Issue #986: Safety timeout — force-clear loading if Promise.all hangs (TCP half-open / nginx
// holds connection open longer than axios timeout). 20s covers any realistic API round-trip.
let loadingTimeoutId: ReturnType<typeof setTimeout> | null = null

// Computed
const lastUpdatedTime = computed(() => {
  if (!lastUpdated.value) return 'Never'
  const now = new Date()
  const diff = Math.floor((now.getTime() - lastUpdated.value.getTime()) / 1000)
  if (diff < 60) return `${diff}s ago`
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  return `${Math.floor(diff / 3600)}h ago`
})

const bridgeHealthClass = computed(() => {
  if (!stats.value.total_bridges) return 'text-gray-400'
  const ratio = stats.value.healthy_bridges / stats.value.total_bridges
  if (ratio === 1) return 'text-green-600'
  if (ratio >= 0.5) return 'text-yellow-600'
  return 'text-red-600'
})

const bridgeHealthText = computed(() => {
  if (!stats.value.total_bridges) return 'No bridges configured'
  const ratio = stats.value.healthy_bridges / stats.value.total_bridges
  if (ratio === 1) return 'All systems operational'
  if (ratio >= 0.5) return 'Some systems degraded'
  return 'Multiple systems down'
})

const filteredTools = computed(() => {
  if (!toolFilter.value) return tools.value
  const filter = toolFilter.value.toLowerCase()
  return tools.value.filter(
    tool =>
      tool.name.toLowerCase().includes(filter) ||
      tool.description.toLowerCase().includes(filter) ||
      tool.bridge.toLowerCase().includes(filter)
  )
})

// Methods
function getStatusClass(status: string): string {
  if (status === 'healthy') return 'bg-green-100 text-green-800'
  if (status === 'degraded') return 'bg-yellow-100 text-yellow-800'
  return 'bg-red-100 text-red-800'
}

function getBorderClass(status: string): string {
  if (status === 'healthy') return 'border-green-500'
  if (status === 'degraded') return 'border-yellow-500'
  return 'border-red-500'
}

function toggleToolSchema(toolName: string): void {
  if (expandedTools.value.has(toolName)) {
    expandedTools.value.delete(toolName)
  } else {
    expandedTools.value.add(toolName)
  }
  expandedTools.value = new Set(expandedTools.value)
}

async function fetchBridges(): Promise<void> {
  try {
    // Issue #835 - use named function from useAutobotApi
    bridges.value = (await api.getMCPBridges()) as unknown as MCPBridge[]
  } catch (e) {
    logger.error('Failed to fetch MCP bridges:', e)
  }
}

async function fetchTools(): Promise<void> {
  try {
    // Issue #835 - use named function from useAutobotApi
    tools.value = (await api.getMCPTools()) as unknown as MCPTool[]
  } catch (e) {
    logger.error('Failed to fetch MCP tools:', e)
  }
}

async function fetchHealth(): Promise<void> {
  try {
    // Issue #835 - use named function from useAutobotApi
    healthData.value = (await api.getMCPHealth()) as unknown as HealthData
  } catch (e) {
    logger.error('Failed to fetch MCP health:', e)
  }
}

async function fetchStats(): Promise<void> {
  try {
    // Issue #835 - use named function from useAutobotApi
    const data = await api.getMCPStats()
    stats.value = ((data.overview || data) as unknown as MCPStats) || { total_tools: 0, total_bridges: 0, healthy_bridges: 0 }
  } catch (e) {
    logger.error('Failed to fetch MCP stats:', e)
  }
}

async function refreshData(): Promise<void> {
  isRefreshing.value = true
  loading.value = true
  loadError.value = null

  // Issue #986: Safety timeout — if the AutoBot backend TCP connection hangs
  // (nginx holds it open past the axios client timeout), force-clear the
  // loading state after 20 s so the user sees an error instead of a spinner.
  if (loadingTimeoutId) clearTimeout(loadingTimeoutId)
  loadingTimeoutId = setTimeout(() => {
    if (loading.value) {
      loading.value = false
      isRefreshing.value = false
      loadError.value = 'AutoBot backend did not respond in time. Is it reachable?'
    }
  }, 20000)

  try {
    // Fetch bridges, tools, stats in parallel — fast endpoints.
    // Health check is slow (checks all 10 bridges, ~60s) — load it
    // in the background so it doesn't block the loading state. (#986)
    await Promise.all([fetchBridges(), fetchTools(), fetchStats()])
    lastUpdated.value = new Date()
  } finally {
    if (loadingTimeoutId) {
      clearTimeout(loadingTimeoutId)
      loadingTimeoutId = null
    }
    loading.value = false
    isRefreshing.value = false
  }
  // Load health data after UI is visible
  fetchHealth()
}

onMounted(() => {
  refreshData()
  refreshInterval = setInterval(() => refreshData(), 30000)
})

onUnmounted(() => {
  if (refreshInterval) clearInterval(refreshInterval)
  if (loadingTimeoutId) clearTimeout(loadingTimeoutId)
})
</script>

<template>
  <div class="p-6">
    <!-- Overview Cards -->
    <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
      <!-- Total Tools Card -->
      <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6 border-l-4 border-l-blue-500">
        <div class="flex items-center justify-between">
          <div>
            <h3 class="text-sm font-medium text-gray-500 uppercase">Total MCP Tools</h3>
            <p class="mt-2 text-3xl font-bold text-gray-900">{{ stats.total_tools || 0 }}</p>
            <p class="mt-1 text-sm text-gray-600">Across {{ stats.total_bridges || 0 }} bridges</p>
          </div>
          <svg class="w-8 h-8 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" />
          </svg>
        </div>
      </div>

      <!-- Healthy Bridges Card -->
      <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6 border-l-4 border-l-green-500">
        <div class="flex items-center justify-between">
          <div>
            <h3 class="text-sm font-medium text-gray-500 uppercase">Healthy Bridges</h3>
            <p class="mt-2 text-3xl font-bold text-gray-900">
              {{ stats.healthy_bridges || 0 }}/{{ stats.total_bridges || 0 }}
            </p>
            <p class="mt-1 text-sm" :class="bridgeHealthClass">
              {{ bridgeHealthText }}
            </p>
          </div>
          <svg class="w-8 h-8 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" />
          </svg>
        </div>
      </div>

      <!-- Last Updated Card -->
      <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6 border-l-4 border-l-purple-500">
        <div class="flex items-center justify-between">
          <div>
            <h3 class="text-sm font-medium text-gray-500 uppercase">Last Updated</h3>
            <p class="mt-2 text-lg font-bold text-gray-900">{{ lastUpdatedTime }}</p>
            <button
              @click="refreshData"
              class="mt-2 text-sm text-purple-600 hover:text-purple-700 flex items-center gap-1"
              :disabled="isRefreshing"
            >
              <svg class="w-4 h-4" :class="{ 'animate-spin': isRefreshing }" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
              Refresh Now
            </button>
          </div>
          <svg class="w-8 h-8 text-purple-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        </div>
      </div>
    </div>

    <!-- Tabs -->
    <div class="mb-6 border-b border-gray-200">
      <nav class="-mb-px flex space-x-8">
        <button
          @click="activeTab = 'bridges'"
          :class="[
            'whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm',
            activeTab === 'bridges'
              ? 'border-primary-500 text-primary-600'
              : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
          ]"
        >
          <svg class="w-4 h-4 inline mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
          </svg>
          MCP Bridges
        </button>
        <button
          @click="activeTab = 'tools'"
          :class="[
            'whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm',
            activeTab === 'tools'
              ? 'border-primary-500 text-primary-600'
              : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
          ]"
        >
          <svg class="w-4 h-4 inline mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
          </svg>
          Available Tools
        </button>
        <button
          @click="activeTab = 'health'"
          :class="[
            'whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm',
            activeTab === 'health'
              ? 'border-primary-500 text-primary-600'
              : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
          ]"
        >
          <svg class="w-4 h-4 inline mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" />
          </svg>
          Health Status
        </button>
      </nav>
    </div>

    <!-- Loading State -->
    <div v-if="loading" class="text-center py-12">
      <svg class="animate-spin w-8 h-8 mx-auto text-primary-500" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
      </svg>
      <p class="mt-4 text-gray-600">Loading MCP data...</p>
    </div>

    <!-- Error State (#986) -->
    <div v-else-if="loadError" class="text-center py-12">
      <svg class="w-12 h-12 mx-auto text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
      </svg>
      <p class="mt-4 text-red-600 font-medium">{{ loadError }}</p>
      <button
        @click="refreshData"
        class="mt-4 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 text-sm"
      >
        Retry
      </button>
    </div>

    <!-- Bridges Tab -->
    <div v-else-if="activeTab === 'bridges'">
      <div v-if="bridges.length === 0" class="text-center py-12">
        <svg class="w-12 h-12 mx-auto text-yellow-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
        </svg>
        <p class="mt-4 text-gray-600">No MCP bridges found</p>
      </div>

      <div v-else class="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div
          v-for="bridge in bridges"
          :key="bridge.name"
          class="bg-white rounded-lg shadow-sm border border-gray-200 p-6 border-l-4"
          :class="getBorderClass(bridge.status)"
        >
          <div class="flex items-start justify-between mb-4">
            <div class="flex-1">
              <h3 class="text-lg font-bold text-gray-900 flex items-center gap-2">
                {{ bridge.name }}
                <span class="px-2 py-1 text-xs font-medium rounded-full" :class="getStatusClass(bridge.status)">
                  {{ bridge.status }}
                </span>
              </h3>
              <p class="text-sm text-gray-600 mt-1">{{ bridge.description }}</p>
            </div>
          </div>

          <div class="grid grid-cols-2 gap-4 mb-4">
            <div>
              <p class="text-xs text-gray-500 uppercase">Tools</p>
              <p class="text-2xl font-bold text-gray-900">{{ bridge.tool_count }}</p>
            </div>
            <div>
              <p class="text-xs text-gray-500 uppercase">Features</p>
              <p class="text-2xl font-bold text-gray-900">{{ bridge.features?.length || 0 }}</p>
            </div>
          </div>

          <div class="mb-4">
            <p class="text-xs font-medium text-gray-700 mb-2">FEATURES:</p>
            <div class="flex flex-wrap gap-1">
              <span
                v-for="feature in bridge.features"
                :key="feature"
                class="px-2 py-1 text-xs bg-blue-100 text-blue-800 rounded"
              >
                {{ feature }}
              </span>
            </div>
          </div>

          <div class="mt-4 pt-4 border-t border-gray-200">
            <p class="text-xs text-gray-500">ENDPOINT:</p>
            <code class="text-xs text-gray-700 bg-gray-100 px-2 py-1 rounded">
              {{ bridge.endpoint }}
            </code>
          </div>

          <div v-if="bridge.error" class="mt-4 p-3 bg-red-50 border border-red-200 rounded">
            <p class="text-xs text-red-700">{{ bridge.error }}</p>
          </div>
        </div>
      </div>
    </div>

    <!-- Tools Tab -->
    <div v-else-if="activeTab === 'tools'">
      <div v-if="tools.length === 0" class="text-center py-12">
        <svg class="w-12 h-12 mx-auto text-yellow-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
        </svg>
        <p class="mt-4 text-gray-600">No MCP tools found</p>
      </div>

      <div v-else>
        <!-- Search -->
        <div class="mb-4">
          <input
            v-model="toolFilter"
            type="text"
            placeholder="Search tools..."
            class="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
          />
        </div>

        <!-- Tools List -->
        <div class="space-y-3">
          <div
            v-for="tool in filteredTools"
            :key="tool.name"
            class="bg-white rounded-lg shadow-sm border border-gray-200 p-5 hover:shadow-md transition-shadow"
          >
            <div class="flex items-start justify-between mb-3">
              <div class="flex-1">
                <h4 class="text-base font-bold text-gray-900 flex items-center gap-2">
                  <svg class="w-4 h-4 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                  </svg>
                  {{ tool.name }}
                </h4>
                <p class="text-sm text-gray-600 mt-1">{{ tool.description }}</p>
              </div>
              <button
                @click="toggleToolSchema(tool.name)"
                class="px-3 py-1 text-xs bg-gray-100 hover:bg-gray-200 rounded flex items-center gap-1"
              >
                <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    stroke-width="2"
                    :d="expandedTools.has(tool.name) ? 'M5 15l7-7 7 7' : 'M19 9l-7 7-7-7'"
                  />
                </svg>
                Schema
              </button>
            </div>

            <div class="flex items-center gap-4 text-xs text-gray-600 mb-3">
              <span class="flex items-center gap-1">
                Bridge: <strong class="text-gray-900">{{ tool.bridge }}</strong>
              </span>
              <span class="flex items-center gap-1">
                <code class="text-xs bg-gray-100 px-2 py-0.5 rounded">{{ tool.endpoint }}</code>
              </span>
            </div>

            <div v-if="expandedTools.has(tool.name)" class="mt-4 pt-4 border-t border-gray-200">
              <p class="text-xs font-medium text-gray-700 mb-2">INPUT SCHEMA:</p>
              <pre class="bg-gray-900 text-green-400 p-4 rounded text-xs overflow-x-auto">{{ JSON.stringify(tool.input_schema, null, 2) }}</pre>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Health Tab -->
    <div v-else-if="activeTab === 'health'">
      <!-- Overall Health Status -->
      <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6 mb-6">
        <div class="flex items-center justify-between">
          <div>
            <h3 class="text-lg font-bold text-gray-900">Overall MCP System Health</h3>
            <p class="text-sm text-gray-600 mt-1">{{ healthData.timestamp }}</p>
          </div>
          <span class="px-4 py-2 text-lg font-bold rounded-full" :class="getStatusClass(healthData.status)">
            {{ healthData.status }}
          </span>
        </div>
      </div>

      <!-- Individual Bridge Health Checks -->
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div
          v-for="check in healthData.checks"
          :key="check.bridge"
          class="bg-white rounded-lg shadow-sm border border-gray-200 p-5"
        >
          <div class="flex items-start justify-between mb-3">
            <h4 class="text-base font-bold text-gray-900">{{ check.bridge }}</h4>
            <span class="px-2 py-1 text-xs font-medium rounded-full" :class="getStatusClass(check.status)">
              {{ check.status }}
            </span>
          </div>

          <div class="grid grid-cols-2 gap-4">
            <div>
              <p class="text-xs text-gray-500">Response Time</p>
              <p class="text-lg font-bold text-gray-900">{{ check.response_time_ms }}ms</p>
            </div>
            <div v-if="check.tool_count">
              <p class="text-xs text-gray-500">Tools Available</p>
              <p class="text-lg font-bold text-gray-900">{{ check.tool_count }}</p>
            </div>
          </div>

          <div v-if="check.error" class="mt-3 p-2 bg-red-50 border border-red-200 rounded">
            <p class="text-xs text-red-700">{{ check.error }}</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
