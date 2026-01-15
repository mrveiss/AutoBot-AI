// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Vue Router Configuration
 *
 * Handles routing and authentication guards.
 */

import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/LoginView.vue'),
      meta: { title: 'Login', public: true }
    },
    {
      path: '/',
      name: 'fleet',
      component: () => import('@/views/FleetOverview.vue'),
      meta: { title: 'Fleet Overview' }
    },
    {
      path: '/deployments',
      name: 'deployments',
      component: () => import('@/views/DeploymentsView.vue'),
      meta: { title: 'Deployments' }
    },
    {
      path: '/backups',
      name: 'backups',
      component: () => import('@/views/BackupsView.vue'),
      meta: { title: 'Backups' }
    },
    {
      path: '/maintenance',
      name: 'maintenance',
      component: () => import('@/views/MaintenanceView.vue'),
      meta: { title: 'Maintenance' }
    },
    {
      path: '/settings',
      name: 'settings',
      component: () => import('@/views/SettingsView.vue'),
      meta: { title: 'Settings' }
    },
    {
      path: '/monitoring',
      name: 'monitoring',
      component: () => import('@/views/MonitoringView.vue'),
      meta: { title: 'Monitoring' },
      children: [
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
          path: 'infrastructure',
          name: 'monitoring-infrastructure',
          component: () => import('@/views/monitoring/InfrastructureMonitor.vue'),
          meta: { title: 'Infrastructure', parent: 'monitoring' }
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
      ]
    },
    {
      path: '/security',
      name: 'security',
      component: () => import('@/views/SecurityView.vue'),
      meta: { title: 'Security Analytics' }
    },
    {
      path: '/tools',
      name: 'tools',
      component: () => import('@/views/ToolsView.vue'),
      meta: { title: 'Infrastructure Tools' }
    },
  ]
})

// Authentication guard
router.beforeEach(async (to, _from, next) => {
  const authStore = useAuthStore()

  // Public routes don't need auth
  if (to.meta.public) {
    // If already authenticated, redirect to home
    if (authStore.isAuthenticated && to.name === 'login') {
      next({ name: 'fleet' })
      return
    }
    next()
    return
  }

  // Check if authenticated
  if (!authStore.isAuthenticated) {
    next({ name: 'login', query: { redirect: to.fullPath } })
    return
  }

  // Verify token is still valid
  const isValid = await authStore.checkAuth()
  if (!isValid) {
    next({ name: 'login', query: { redirect: to.fullPath } })
    return
  }

  next()
})

// Update document title on navigation
router.afterEach((to) => {
  document.title = `${to.meta.title || 'SLM Admin'} - Service Lifecycle Manager`
})

export default router
