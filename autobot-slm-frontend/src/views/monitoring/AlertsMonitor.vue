<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * AlertsMonitor - System alerts and recommendations dashboard
 *
 * Displays active alerts, performance warnings, and optimization recommendations.
 */

import { ref, computed, onMounted, onUnmounted } from 'vue'
import { usePrometheusMetrics } from '@/composables/usePrometheusMetrics'
import type { PerformanceAlert, OptimizationRecommendation } from '@/composables/usePrometheusMetrics'

const {
  alerts,
  recommendations,
  fetchAlerts,
  fetchRecommendations,
  isLoading,
} = usePrometheusMetrics({ autoFetch: false })

// State
const activeTab = ref<'alerts' | 'recommendations'>('alerts')
const severityFilter = ref<string>('all')
const acknowledgedAlerts = ref<Set<number>>(new Set())

let refreshInterval: ReturnType<typeof setInterval> | null = null

// Severity levels
const severityLevels = ['all', 'critical', 'high', 'warning', 'info']

// Filtered alerts
const filteredAlerts = computed(() => {
  const alertList = alerts.value?.alerts ?? []
  if (severityFilter.value === 'all') return alertList
  return alertList.filter(a => a.severity === severityFilter.value)
})

// Alert counts by severity
const alertCounts = computed(() => {
  const alertList = alerts.value?.alerts ?? []
  return {
    total: alertList.length,
    critical: alertList.filter(a => a.severity === 'critical').length,
    high: alertList.filter(a => a.severity === 'high').length,
    warning: alertList.filter(a => a.severity === 'warning').length,
    info: alertList.filter(a => a.severity === 'info').length,
  }
})

// Recommendations by priority
const sortedRecommendations = computed(() => {
  const recs = recommendations.value ?? []
  const priorityOrder = { high: 0, medium: 1, low: 2 }
  return [...recs].sort((a, b) => priorityOrder[a.priority] - priorityOrder[b.priority])
})

function getSeverityClass(severity: string): string {
  switch (severity) {
    case 'critical': return 'bg-red-100 text-red-800 border-red-200'
    case 'high': return 'bg-orange-100 text-orange-800 border-orange-200'
    case 'warning': return 'bg-yellow-100 text-yellow-800 border-yellow-200'
    case 'info': return 'bg-blue-100 text-blue-800 border-blue-200'
    default: return 'bg-gray-100 text-gray-800 border-gray-200'
  }
}

function getSeverityIcon(severity: string): string {
  switch (severity) {
    case 'critical':
    case 'high':
      return 'M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z'
    case 'warning':
      return 'M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z'
    case 'info':
    default:
      return 'M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z'
  }
}

function getPriorityClass(priority: string): string {
  switch (priority) {
    case 'high': return 'bg-red-50 border-red-200'
    case 'medium': return 'bg-yellow-50 border-yellow-200'
    case 'low': return 'bg-green-50 border-green-200'
    default: return 'bg-gray-50 border-gray-200'
  }
}

function getPriorityBadgeClass(priority: string): string {
  switch (priority) {
    case 'high': return 'bg-red-100 text-red-700'
    case 'medium': return 'bg-yellow-100 text-yellow-700'
    case 'low': return 'bg-green-100 text-green-700'
    default: return 'bg-gray-100 text-gray-700'
  }
}

function formatTimestamp(ts: number): string {
  const date = new Date(ts * 1000)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMins = Math.floor(diffMs / 60000)

  if (diffMins < 1) return 'Just now'
  if (diffMins < 60) return `${diffMins}m ago`
  const diffHours = Math.floor(diffMins / 60)
  if (diffHours < 24) return `${diffHours}h ago`
  return date.toLocaleDateString()
}

function acknowledgeAlert(index: number) {
  acknowledgedAlerts.value.add(index)
}

function isAcknowledged(index: number): boolean {
  return acknowledgedAlerts.value.has(index)
}

async function refresh() {
  await Promise.all([fetchAlerts(), fetchRecommendations()])
}

onMounted(() => {
  refresh()
  refreshInterval = setInterval(refresh, 30000)
})

onUnmounted(() => {
  if (refreshInterval) {
    clearInterval(refreshInterval)
  }
})
</script>

<template>
  <div class="p-6">
    <!-- Header -->
    <div class="flex items-center justify-between mb-6">
      <h2 class="text-xl font-bold text-gray-900">Alerts & Recommendations</h2>
      <button
        @click="refresh"
        :disabled="isLoading"
        class="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50 flex items-center gap-2"
      >
        <svg
          class="w-4 h-4"
          :class="{ 'animate-spin': isLoading }"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
        </svg>
        Refresh
      </button>
    </div>

    <!-- Summary Cards -->
    <div class="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
      <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
        <p class="text-sm text-gray-500">Total Alerts</p>
        <p class="text-2xl font-bold text-gray-900">{{ alertCounts.total }}</p>
      </div>
      <div class="bg-white rounded-lg shadow-sm border border-red-200 p-4">
        <p class="text-sm text-red-600">Critical</p>
        <p class="text-2xl font-bold text-red-700">{{ alertCounts.critical }}</p>
      </div>
      <div class="bg-white rounded-lg shadow-sm border border-orange-200 p-4">
        <p class="text-sm text-orange-600">High</p>
        <p class="text-2xl font-bold text-orange-700">{{ alertCounts.high }}</p>
      </div>
      <div class="bg-white rounded-lg shadow-sm border border-yellow-200 p-4">
        <p class="text-sm text-yellow-600">Warning</p>
        <p class="text-2xl font-bold text-yellow-700">{{ alertCounts.warning }}</p>
      </div>
      <div class="bg-white rounded-lg shadow-sm border border-blue-200 p-4">
        <p class="text-sm text-blue-600">Info</p>
        <p class="text-2xl font-bold text-blue-700">{{ alertCounts.info }}</p>
      </div>
    </div>

    <!-- Tabs -->
    <div class="flex gap-2 mb-4">
      <button
        @click="activeTab = 'alerts'"
        :class="[
          'px-4 py-2 text-sm font-medium rounded-lg transition-colors',
          activeTab === 'alerts'
            ? 'bg-gray-900 text-white'
            : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
        ]"
      >
        Active Alerts ({{ alertCounts.total }})
      </button>
      <button
        @click="activeTab = 'recommendations'"
        :class="[
          'px-4 py-2 text-sm font-medium rounded-lg transition-colors',
          activeTab === 'recommendations'
            ? 'bg-gray-900 text-white'
            : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
        ]"
      >
        Recommendations ({{ recommendations?.length ?? 0 }})
      </button>
    </div>

    <!-- Alerts Tab -->
    <div v-if="activeTab === 'alerts'" class="space-y-4">
      <!-- Severity Filter -->
      <div class="flex items-center gap-2">
        <label class="text-sm text-gray-600">Filter by severity:</label>
        <select
          v-model="severityFilter"
          class="px-3 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
        >
          <option v-for="level in severityLevels" :key="level" :value="level">
            {{ level === 'all' ? 'All Severities' : level.charAt(0).toUpperCase() + level.slice(1) }}
          </option>
        </select>
      </div>

      <!-- Alert List -->
      <div class="space-y-3">
        <div
          v-for="(alert, index) in filteredAlerts"
          :key="index"
          :class="[
            'rounded-lg border p-4 transition-opacity',
            getSeverityClass(alert.severity),
            { 'opacity-50': isAcknowledged(index) }
          ]"
        >
          <div class="flex items-start justify-between">
            <div class="flex items-start gap-3">
              <svg class="w-5 h-5 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" :d="getSeverityIcon(alert.severity)" />
              </svg>
              <div>
                <div class="flex items-center gap-2">
                  <span class="text-xs font-medium uppercase">{{ alert.category }}</span>
                  <span class="text-xs">{{ formatTimestamp(alert.timestamp) }}</span>
                </div>
                <p class="font-medium mt-1">{{ alert.message }}</p>
                <p class="text-sm mt-1 opacity-80">{{ alert.recommendation }}</p>
              </div>
            </div>
            <button
              v-if="!isAcknowledged(index)"
              @click="acknowledgeAlert(index)"
              class="px-3 py-1 text-xs font-medium bg-white bg-opacity-50 rounded hover:bg-opacity-75 transition-colors"
            >
              Acknowledge
            </button>
            <span v-else class="px-3 py-1 text-xs font-medium bg-white bg-opacity-30 rounded">
              Acknowledged
            </span>
          </div>
        </div>

        <div v-if="filteredAlerts.length === 0" class="text-center py-8 text-gray-500">
          <svg class="w-12 h-12 mx-auto mb-3 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <p>No active alerts</p>
        </div>
      </div>
    </div>

    <!-- Recommendations Tab -->
    <div v-if="activeTab === 'recommendations'" class="space-y-3">
      <div
        v-for="(rec, index) in sortedRecommendations"
        :key="index"
        :class="['rounded-lg border p-4', getPriorityClass(rec.priority)]"
      >
        <div class="flex items-start justify-between">
          <div class="flex-1">
            <div class="flex items-center gap-2 mb-2">
              <span :class="['px-2 py-0.5 text-xs font-medium rounded', getPriorityBadgeClass(rec.priority)]">
                {{ rec.priority.toUpperCase() }}
              </span>
              <span class="text-xs text-gray-500">{{ rec.category }}</span>
            </div>
            <p class="font-medium text-gray-900">{{ rec.recommendation }}</p>
            <p class="text-sm text-gray-600 mt-1">{{ rec.action }}</p>
            <p class="text-sm text-green-600 mt-2">
              <span class="font-medium">Expected improvement:</span> {{ rec.expected_improvement }}
            </p>
          </div>
        </div>
      </div>

      <div v-if="sortedRecommendations.length === 0" class="text-center py-8 text-gray-500">
        <svg class="w-12 h-12 mx-auto mb-3 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
        </svg>
        <p>No recommendations at this time</p>
      </div>
    </div>
  </div>
</template>
