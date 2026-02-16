<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * LLMHealthMonitor - LLM provider health monitoring dashboard
 * Issue #897 - LLM Configuration Panel
 */

import { computed } from 'vue'
import type { LLMHealthSummary, LLMHealthMetrics } from '@/composables/useLlmHealth'

interface Props {
  healthSummary: LLMHealthSummary | null
  healthMetrics: LLMHealthMetrics[]
  loading?: boolean
  lastUpdate: Date | null
}

const props = defineProps<Props>()

const overallStatusColor = computed(() => {
  if (!props.healthSummary) return 'text-gray-500'
  switch (props.healthSummary.overall_status) {
    case 'healthy': return 'text-success-600'
    case 'degraded': return 'text-warning-600'
    case 'critical': return 'text-danger-600'
    default: return 'text-gray-500'
  }
})

const overallStatusText = computed(() => {
  if (!props.healthSummary) return 'Unknown'
  return props.healthSummary.overall_status.charAt(0).toUpperCase() +
         props.healthSummary.overall_status.slice(1)
})

function getHealthColor(score: number): string {
  if (score >= 90) return 'text-success-600'
  if (score >= 70) return 'text-warning-600'
  return 'text-danger-600'
}

function getStatusColor(status: string): string {
  switch (status.toLowerCase()) {
    case 'healthy': return 'bg-success-100 text-success-800'
    case 'degraded': return 'bg-warning-100 text-warning-800'
    case 'unhealthy': return 'bg-danger-100 text-danger-800'
    default: return 'bg-gray-100 text-gray-600'
  }
}

function formatTimestamp(timestamp: string): string {
  return new Date(timestamp).toLocaleString()
}
</script>

<template>
  <div class="space-y-6">
    <!-- Overall Status Card -->
    <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
      <div class="flex items-center justify-between mb-4">
        <h3 class="text-lg font-semibold text-gray-900">LLM Health Status</h3>
        <div v-if="lastUpdate" class="text-sm text-gray-500">
          Updated: {{ lastUpdate.toLocaleTimeString() }}
        </div>
      </div>

      <div v-if="loading" class="flex items-center justify-center py-8">
        <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600"></div>
      </div>

      <div v-else-if="!healthSummary" class="text-center py-8 text-gray-500">
        No health data available
      </div>

      <div v-else class="grid grid-cols-1 md:grid-cols-4 gap-6">
        <!-- Overall Status -->
        <div class="space-y-2">
          <div class="text-sm font-medium text-gray-500">Overall Status</div>
          <div :class="['text-3xl font-bold', overallStatusColor]">
            {{ overallStatusText }}
          </div>
          <div class="text-xs text-gray-600">
            {{ healthSummary.healthy_providers }}/{{ healthSummary.total_providers }} healthy
          </div>
        </div>

        <!-- Healthy Providers -->
        <div class="space-y-2">
          <div class="text-sm font-medium text-gray-500">Healthy</div>
          <div class="text-3xl font-bold text-success-600">
            {{ healthSummary.healthy_providers }}
          </div>
          <div class="text-xs text-gray-600">Providers</div>
        </div>

        <!-- Degraded Providers -->
        <div class="space-y-2">
          <div class="text-sm font-medium text-gray-500">Degraded</div>
          <div class="text-3xl font-bold text-warning-600">
            {{ healthSummary.degraded_providers }}
          </div>
          <div class="text-xs text-gray-600">Providers</div>
        </div>

        <!-- Unhealthy Providers -->
        <div class="space-y-2">
          <div class="text-sm font-medium text-gray-500">Unhealthy</div>
          <div class="text-3xl font-bold text-danger-600">
            {{ healthSummary.unhealthy_providers }}
          </div>
          <div class="text-xs text-gray-600">Providers</div>
        </div>
      </div>
    </div>

    <!-- Provider Health Details -->
    <div v-if="healthSummary && healthSummary.providers.length > 0" class="bg-white rounded-lg shadow-sm border border-gray-200">
      <div class="px-6 py-4 border-b border-gray-200">
        <h3 class="text-lg font-semibold text-gray-900">Provider Details</h3>
      </div>

      <div class="overflow-x-auto">
        <table class="min-w-full divide-y divide-gray-200">
          <thead class="bg-gray-50">
            <tr>
              <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Provider
              </th>
              <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Health Score
              </th>
              <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Latency
              </th>
              <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Errors
              </th>
              <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Last Success
              </th>
            </tr>
          </thead>
          <tbody class="bg-white divide-y divide-gray-200">
            <tr v-for="provider in healthSummary.providers" :key="provider.provider">
              <td class="px-6 py-4 whitespace-nowrap">
                <div class="flex items-center">
                  <div
                    :class="[
                      'w-3 h-3 rounded-full mr-3',
                      provider.is_available ? 'bg-success-500' : 'bg-gray-400'
                    ]"
                  ></div>
                  <div class="text-sm font-medium text-gray-900">
                    {{ provider.provider }}
                  </div>
                </div>
              </td>
              <td class="px-6 py-4 whitespace-nowrap">
                <div :class="['text-sm font-semibold', getHealthColor(provider.health_score)]">
                  {{ provider.health_score }}%
                </div>
              </td>
              <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                {{ provider.latency_ms }}ms
              </td>
              <td class="px-6 py-4 whitespace-nowrap">
                <span :class="[
                  'text-sm',
                  provider.error_count > 0 ? 'text-danger-600 font-semibold' : 'text-gray-500'
                ]">
                  {{ provider.error_count }}
                </span>
              </td>
              <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                <span v-if="provider.last_successful_request">
                  {{ formatTimestamp(provider.last_successful_request) }}
                </span>
                <span v-else class="text-gray-400">Never</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Detailed Metrics -->
    <div v-if="healthMetrics.length > 0" class="bg-white rounded-lg shadow-sm border border-gray-200">
      <div class="px-6 py-4 border-b border-gray-200">
        <h3 class="text-lg font-semibold text-gray-900">Performance Metrics</h3>
      </div>

      <div class="p-6 space-y-6">
        <div
          v-for="metric in healthMetrics"
          :key="metric.provider"
          class="border border-gray-200 rounded-lg p-4"
        >
          <div class="flex items-center justify-between mb-4">
            <div class="text-sm font-semibold text-gray-900">{{ metric.provider }}</div>
            <span :class="['px-2 py-1 text-xs font-medium rounded-full', getStatusColor(metric.status)]">
              {{ metric.status }}
            </span>
          </div>

          <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <div class="text-xs text-gray-500">Response Time</div>
              <div class="text-lg font-semibold text-gray-900">{{ metric.response_time_ms }}ms</div>
            </div>
            <div>
              <div class="text-xs text-gray-500">Success Rate</div>
              <div :class="['text-lg font-semibold', getHealthColor(metric.success_rate)]">
                {{ metric.success_rate.toFixed(1) }}%
              </div>
            </div>
            <div>
              <div class="text-xs text-gray-500">Total Requests</div>
              <div class="text-lg font-semibold text-gray-900">{{ metric.total_requests.toLocaleString() }}</div>
            </div>
            <div>
              <div class="text-xs text-gray-500">Uptime</div>
              <div :class="['text-lg font-semibold', getHealthColor(metric.uptime_percentage)]">
                {{ metric.uptime_percentage.toFixed(1) }}%
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
