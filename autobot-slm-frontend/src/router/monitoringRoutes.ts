// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * The Monitoring section's child routes, split from `router/index.ts` so that
 * file stays under the frontend size guard (#17885) as sections grow (#18391).
 * `meta.admin` routes are refused to non-admins by the guard in `index.ts`, and
 * MonitoringView does not offer their tabs.
 */

import type { RouteRecordRaw } from 'vue-router'

export const monitoringChildren: RouteRecordRaw[] = [
  {
    path: '',
    name: 'monitoring-default',
    redirect: '/monitoring/system'
  },
  {
    path: 'system',
    name: 'monitoring-system',
    component: () => import('@/views/monitoring/SystemMonitor.vue'),
    meta: { title: 'System Monitor', parent: 'monitoring' }
  },
  {
    path: 'logs',
    name: 'monitoring-logs',
    component: () => import('@/views/monitoring/LogViewer.vue'),
    meta: { title: 'Log Viewer', parent: 'monitoring' }
  },
  {
    path: 'dashboards',
    name: 'monitoring-dashboards',
    component: () => import('@/views/monitoring/GrafanaDashboards.vue'),
    meta: { title: 'Grafana Dashboards', parent: 'monitoring' }
  },
  {
    path: 'alerts',
    name: 'monitoring-alerts',
    component: () => import('@/views/monitoring/AlertsMonitor.vue'),
    meta: { title: 'Alerts', parent: 'monitoring' }
  },
  {
    path: 'errors',
    name: 'monitoring-errors',
    component: () => import('@/views/monitoring/ErrorMonitor.vue'),
    meta: { title: 'Error Monitoring', parent: 'monitoring' }
  },
  // Admin monitoring (migrated from main AutoBot frontend - Issue #729)
  {
    path: 'admin',
    name: 'monitoring-admin',
    component: () => import('@/views/monitoring/admin/AdminMonitoringView.vue'),
    meta: { title: 'Admin Dashboard', parent: 'monitoring', admin: true }
  },
  // #18391 AC2: every company's agent ledger, admin only (the API requires ADMIN_SYSTEM)
  {
    path: 'agent-ledger',
    name: 'monitoring-agent-ledger',
    component: () => import('@/views/monitoring/AgentLedgerMonitor.vue'),
    meta: { title: 'Agent Ledger', parent: 'monitoring', admin: true }
  },
  // Issue #752: Performance — moved from standalone /performance into monitoring
  // #19851: the performance sections are children of PerformanceView, which owns the
  // route's one performance poll; the overview reads it instead of polling again.
  {
    path: 'performance',
    component: () => import('@/views/PerformanceView.vue'),
    meta: { title: 'Performance', parent: 'monitoring' },
    children: [
      {
        path: '',
        name: 'monitoring-performance',
        redirect: '/monitoring/performance/overview'
      },
      {
        path: 'overview',
        name: 'monitoring-performance-overview',
        component: () => import('@/views/performance/PerformanceOverview.vue'),
        meta: { title: 'Performance Overview', parent: 'monitoring' }
      },
      {
        path: 'traces',
        name: 'monitoring-performance-traces',
        component: () => import('@/views/performance/TracingView.vue'),
        meta: { title: 'Distributed Traces', parent: 'monitoring' }
      },
      {
        path: 'slos',
        name: 'monitoring-performance-slos',
        component: () => import('@/views/performance/SLODashboard.vue'),
        meta: { title: 'SLO Dashboard', parent: 'monitoring' }
      },
      {
        path: 'alerts',
        name: 'monitoring-performance-alerts',
        component: () => import('@/views/performance/AlertRulesView.vue'),
        meta: { title: 'Alert Rules', parent: 'monitoring' }
      },
    ]
  },
]
