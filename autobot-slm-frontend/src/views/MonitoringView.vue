<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * MonitoringView - Layout wrapper for monitoring subsections
 *
 * Provides navigation tabs for monitoring sub-routes and displays
 * the active sub-view via router-view.
 *
 * Issue #754: Added ARIA tablist/tab roles, aria-selected,
 * status indicators, accessible labels.
 */

import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import TabbedRouteLayout from '@/components/common/TabbedRouteLayout.vue'
import { useFleetStore } from '@/stores/fleet'
import { useAuthStore } from '@/stores/auth'
import { useFleetMetrics } from '@/composables/useFleetMetrics'
import { provideFleetMetrics } from '@/composables/monitoringPollContext'

const { t } = useI18n()
const fleetStore = useFleetStore()

// #19851: this layout owns the route's one fleet poll; child routes read it
const fleetMetrics = useFleetMetrics({ autoFetch: true, pollInterval: 30000 })
provideFleetMetrics(fleetMetrics)
const { systemHealth, activeAlertCount, poller } = fleetMetrics

// Navigation tabs for monitoring sub-routes (all SLM monitoring - Issue #729)
const tabs = [
  { id: 'system', nameKey: 'monitoringView.tabs.system', path: '/monitoring/system', icon: 'M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z' },
  { id: 'logs', nameKey: 'monitoringView.tabs.logs', path: '/monitoring/logs', icon: 'M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z' },
  { id: 'dashboards', nameKey: 'monitoringView.tabs.dashboards', path: '/monitoring/dashboards', icon: 'M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z' },
  { id: 'alerts', nameKey: 'monitoringView.tabs.alerts', path: '/monitoring/alerts', icon: 'M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9' },
  { id: 'errors', nameKey: 'monitoringView.tabs.errors', path: '/monitoring/errors', icon: 'M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z' },
  // Migrated from main AutoBot frontend - Issue #729
  { id: 'admin-dashboard', nameKey: 'monitoringView.tabs.backendHealth', admin: true, path: '/monitoring/admin', icon: 'M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z M15 12a3 3 0 11-6 0 3 3 0 016 0z' },
  // Issue #752: Performance moved from standalone menu into monitoring
  { id: 'performance', nameKey: 'monitoringView.tabs.performance', path: '/monitoring/performance', icon: 'M13 10V3L4 14h7v7l9-11h-7z' },
  // #18391 AC2: the agent ledger across every company
  { id: 'agent-ledger', nameKey: 'monitoringView.tabs.agentLedger', admin: true, path: '/monitoring/agent-ledger', icon: 'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4' },
  // #18278: the system validation report from the main backend
  { id: 'validation', nameKey: 'monitoringView.tabs.validation', admin: true, path: '/monitoring/validation', icon: 'M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z' },
  // #18277: browser-reported events held by the main backend
  { id: 'rum', nameKey: 'monitoringView.tabs.rum', admin: true, path: '/monitoring/rum', icon: 'M15 12a3 3 0 11-6 0 3 3 0 016 0z M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z' },
]

// Admin-only tabs (route meta `admin`) are hidden from everyone else rather than
// shown as a link the router guard then refuses.
const authStore = useAuthStore()
const visibleTabs = computed(() => tabs.filter(t => !t.admin || authStore.isAdmin))

// Tabs as the shared layout takes them (labels resolved here)
const layoutTabs = computed(() => visibleTabs.value.map(tab => ({ ...tab, label: t(tab.nameKey) })))

// Check if there are critical alerts
const hasCriticalAlerts = computed(() => activeAlertCount.value > 0)

function getStatusColor(status: string): string {
  switch (status) {
    case 'healthy': return 'bg-success-500'
    case 'degraded': return 'bg-warning-500'
    case 'unhealthy':
    case 'critical': return 'bg-error-500'
    default: return 'bg-gray-400'
  }
}
</script>

<template>
  <TabbedRouteLayout
    :title="t('monitoringView.monitoring')"
    :tabs-label="t('monitoringView.monitoringSections')"
    :tabs="layoutTabs"
    default-tab="system"
    :poller="poller"
  >
    <template #title-extra>
      <div class="flex items-center gap-2" role="status" :aria-label="$t('monitoringView.systemHealthStatusAria', { status: systemHealth })">
        <span
          :class="['w-2.5 h-2.5 rounded-full', getStatusColor(systemHealth)]"
          aria-hidden="true"
        ></span>
        <span class="text-sm text-gray-600 capitalize">{{ systemHealth }}</span>
      </div>
    </template>

    <template #header-end>
      <!-- Quick Stats -->
      <div class="flex items-center gap-4 text-sm">
        <div class="flex items-center gap-2 text-gray-600">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2" />
          </svg>
          <span>{{ $t('monitoringView.countNodes', { count: fleetStore.nodeList.length }) }}</span>
        </div>
        <div v-if="hasCriticalAlerts" class="flex items-center gap-2 text-error-600" role="alert">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          <span>{{ $t('monitoringView.value0AlertPlural', { value0: activeAlertCount, plural: activeAlertCount !== 1 ? 's' : '' }) }}</span>
        </div>
      </div>
    </template>

    <template #tab-badge="{ tab }">
      <span
        v-if="tab.id === 'alerts' && activeAlertCount > 0"
        class="px-1.5 py-0.5 text-xs font-bold bg-(--color-error-solid) text-(--text-on-error) rounded-full"
        :aria-label="$t('monitoringView.activeAlertsCountAria', { count: activeAlertCount })"
      >
        {{ activeAlertCount }}
      </span>
    </template>
  </TabbedRouteLayout>
</template>
