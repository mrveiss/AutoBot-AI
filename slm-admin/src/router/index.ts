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
      meta: { title: 'Monitoring' }
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
