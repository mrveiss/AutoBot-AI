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
  if (!props.healthSummary) return 'text-secondary'
  switch (props.healthSummary.overall_status) {
    case 'healthy': return 'text-autobot-success'
    case 'degraded': return 'text-autobot-warning'
    case 'critical': return 'text-autobot-error'
    default: return 'text-secondary'
  }
})

const overallStatusText = computed(() => {
  if (!props.healthSummary) return 'Unknown'
  return props.healthSummary.overall_status.charAt(0).toUpperCase() +
         props.healthSummary.overall_status.slice(1)
})

function getHealthColor(score: number): string {
  if (score >= 90) return 'text-autobot-success'
  if (score >= 70) return 'text-autobot-warning'
  return 'text-autobot-error'
}

function getStatusColor(status: string): string {
  switch (status.toLowerCase()) {
    case 'healthy': return 'bg-autobot-success-bg text-autobot-success'
    case 'degraded': return 'bg-autobot-warning-bg text-autobot-warning'
    case 'unhealthy': return 'bg-autobot-error-bg text-autobot-error'
    default: return 'bg-autobot-bg-secondary text-secondary'
  }
}

function formatTimestamp(timestamp: string): string {
  return new Date(timestamp).toLocaleString()
}
</script>

<template>
  <div class="space-y-6">
    <!-- Overall Status Card -->
    <div class="bg-autobot-bg-card rounded shadow-sm border border-default p-6">
      <div class="flex items-center justify-between mb-4">
        <h3 class="text-lg font-semibold text-primary">LLM Health Status</h3>
        <div v-if="lastUpdate" class="text-sm text-secondary">
          Updated: {{ lastUpdate.toLocaleTimeString() }}
        </div>
      </div>

      <div v-if="loading" class="flex items-center justify-center py-8">
        <div class="animate-spin rounded-sm h-8 w-8 border-b-2 border-primary-600"></div>
      </div>

      <div v-else-if="!healthSummary" class="text-center py-8 text-secondary">
        No health data available
      </div>

      <div v-else class="grid grid-cols-1 md:grid-cols-4 gap-6">
        <!-- Overall Status -->
        <div class="space-y-2">
          <div class="text-sm font-medium text-secondary">Overall Status</div>
          <div :class="['text-3xl font-bold', overallStatusColor]">
            {{ overallStatusText }}
          </div>
          <div class="text-xs text-secondary">
            {{ healthSummary.healthy_providers }}/{{ healthSummary.total_providers }} healthy
          </div>
        </div>

        <!-- Healthy Providers -->
        <div class="space-y-2">
          <div class="text-sm font-medium text-secondary">Healthy</div>
          <div class="text-3xl font-bold text-autobot-success">
            {{ healthSummary.healthy_providers }}
          </div>
          <div class="text-xs text-secondary">Providers</div>
        </div>

        <!-- Degraded Providers -->
        <div class="space-y-2">
          <div class="text-sm font-medium text-secondary">Degraded</div>
          <div class="text-3xl font-bold text-autobot-warning">
            {{ healthSummary.degraded_providers }}
          </div>
          <div class="text-xs text-secondary">Providers</div>
        </div>

        <!-- Unhealthy Providers -->
        <div class="space-y-2">
          <div class="text-sm font-medium text-secondary">Unhealthy</div>
          <div class="text-3xl font-bold text-autobot-error">
            {{ healthSummary.unhealthy_providers }}
          </div>
          <div class="text-xs text-secondary">Providers</div>
        </div>
      </div>
    </div>

    <!-- Provider Health Details -->
    <div v-if="healthSummary && healthSummary.providers.length > 0" class="bg-autobot-bg-card rounded shadow-sm border border-default">
      <div class="px-6 py-4 border-b border-default">
        <h3 class="text-lg font-semibold text-primary">Provider Details</h3>
      </div>

      <div class="overflow-x-auto">
        <table class="min-w-full divide-y divide-autobot-border">
          <thead class="bg-autobot-bg-secondary">
            <tr>
              <th class="px-6 py-3 text-left text-xs font-medium text-secondary uppercase tracking-wider">
                Provider
              </th>
              <th class="px-6 py-3 text-left text-xs font-medium text-secondary uppercase tracking-wider">
                Health Score
              </th>
              <th class="px-6 py-3 text-left text-xs font-medium text-secondary uppercase tracking-wider">
                Latency
              </th>
              <th class="px-6 py-3 text-left text-xs font-medium text-secondary uppercase tracking-wider">
                Errors
              </th>
              <th class="px-6 py-3 text-left text-xs font-medium text-secondary uppercase tracking-wider">
                Last Success
              </th>
            </tr>
          </thead>
          <tbody class="bg-autobot-bg-card divide-y divide-autobot-border">
            <tr v-for="provider in healthSummary.providers" :key="provider.provider">
              <td class="px-6 py-4 whitespace-nowrap">
                <div class="flex items-center">
                  <div
                    :class="[
                      'w-3 h-3 rounded-sm mr-3',
                      provider.is_available ? 'bg-success-500' : 'bg-autobot-text-muted'
                    ]"
                  ></div>
                  <div class="text-sm font-medium text-primary">
                    {{ provider.provider }}
                  </div>
                </div>
              </td>
              <td class="px-6 py-4 whitespace-nowrap">
                <div :class="['text-sm font-semibold', getHealthColor(provider.health_score)]">
                  {{ provider.health_score }}%
                </div>
              </td>
              <td class="px-6 py-4 whitespace-nowrap text-sm text-primary">
                {{ provider.latency_ms }}ms
              </td>
              <td class="px-6 py-4 whitespace-nowrap">
                <span :class="[
                  'text-sm',
                  provider.error_count > 0 ? 'text-autobot-error font-semibold' : 'text-secondary'
                ]">
                  {{ provider.error_count }}
                </span>
              </td>
              <td class="px-6 py-4 whitespace-nowrap text-sm text-secondary">
                <span v-if="provider.last_successful_request">
                  {{ formatTimestamp(provider.last_successful_request) }}
                </span>
                <span v-else class="text-autobot-text-muted">Never</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Detailed Metrics -->
    <div v-if="healthMetrics.length > 0" class="bg-autobot-bg-card rounded shadow-sm border border-default">
      <div class="px-6 py-4 border-b border-default">
        <h3 class="text-lg font-semibold text-primary">Performance Metrics</h3>
      </div>

      <div class="p-6 space-y-6">
        <div
          v-for="metric in healthMetrics"
          :key="metric.provider"
          class="border border-default rounded p-4"
        >
          <div class="flex items-center justify-between mb-4">
            <div class="text-sm font-semibold text-primary">{{ metric.provider }}</div>
            <span :class="['px-2 py-1 text-xs font-medium rounded-sm', getStatusColor(metric.status)]">
              {{ metric.status }}
            </span>
          </div>

          <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <div class="text-xs text-secondary">Response Time</div>
              <div class="text-lg font-semibold text-primary">{{ metric.response_time_ms }}ms</div>
            </div>
            <div>
              <div class="text-xs text-secondary">Success Rate</div>
              <div :class="['text-lg font-semibold', getHealthColor(metric.success_rate)]">
                {{ metric.success_rate.toFixed(1) }}%
              </div>
            </div>
            <div>
              <div class="text-xs text-secondary">Total Requests</div>
              <div class="text-lg font-semibold text-primary">{{ metric.total_requests.toLocaleString() }}</div>
            </div>
            <div>
              <div class="text-xs text-secondary">Uptime</div>
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
