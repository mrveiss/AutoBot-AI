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
      // Issue #576: SSO callback handler for OAuth2/SAML redirects
      path: '/sso-callback',
      name: 'sso-callback',
      component: () => import('@/views/SSOCallbackView.vue'),
      meta: { title: 'SSO Login', public: true },
    },
    {
      path: '/',
      name: 'fleet',
      component: () => import('@/views/FleetOverview.vue'),
      meta: { title: 'Fleet Overview' }
    },
    {
      path: '/services',
      name: 'services',
      component: () => import('@/views/ServicesView.vue'),
      meta: { title: 'Services' }
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
      path: '/replications',
      name: 'replications',
      component: () => import('@/views/ReplicationView.vue'),
      meta: { title: 'Replication' }
    },
    {
      path: '/maintenance',
      name: 'maintenance',
      component: () => import('@/views/MaintenanceView.vue'),
      meta: { title: 'Maintenance' }
    },
    {
      // Issue #741: Code sync management for fleet-wide updates
      path: '/code-sync',
      name: 'code-sync',
      component: () => import('@/views/CodeSyncView.vue'),
      meta: { title: 'Code Sync' }
    },
    {
      // Issue #760: Agent LLM configuration management
      path: '/agent-config',
      name: 'agent-config',
      component: () => import('@/views/AgentsView.vue'),
      meta: { title: 'Agent Configuration' }
    },
    {
      // Issue #786: Infrastructure setup wizard
      path: '/infrastructure',
      name: 'infrastructure',
      component: () => import('@/views/InfrastructureView.vue'),
      meta: { title: 'Infrastructure Setup' }
    },
    {
      path: '/settings',
      name: 'settings',
      component: () => import('@/views/SettingsView.vue'),
      meta: { title: 'Settings' },
      children: [
        {
          path: '',
          name: 'settings-default',
          redirect: '/settings/general'
        },
        {
          path: 'general',
          name: 'settings-general',
          component: () => import('@/views/settings/GeneralSettings.vue'),
          meta: { title: 'General Settings', parent: 'settings' }
        },
        {
          path: 'infrastructure',
          name: 'settings-infrastructure',
          component: () => import('@/views/settings/InfrastructureSettings.vue'),
          meta: { title: 'Infrastructure', parent: 'settings' }
        },
        {
          // Issue #737: Consolidated to Fleet Overview - redirect for backwards compatibility
          path: 'nodes',
          name: 'settings-nodes',
          redirect: '/',
          meta: { title: 'Nodes Management', parent: 'settings' }
        },
        {
          path: 'monitoring',
          name: 'settings-monitoring',
          component: () => import('@/views/settings/MonitoringSettings.vue'),
          meta: { title: 'Monitoring Settings', parent: 'settings' }
        },
        {
          path: 'notifications',
          name: 'settings-notifications',
          component: () => import('@/views/settings/NotificationsSettings.vue'),
          meta: { title: 'Notifications', parent: 'settings' }
        },
        {
          path: 'api',
          name: 'settings-api',
          component: () => import('@/views/settings/APISettings.vue'),
          meta: { title: 'API Settings', parent: 'settings' }
        },
        {
          path: 'backend',
          name: 'settings-backend',
          component: () => import('@/views/settings/BackendSettings.vue'),
          meta: { title: 'Backend Settings', parent: 'settings' }
        },
        {
          // Issue #576: Security settings for MFA and API Keys
          path: 'security',
          name: 'settings-security',
          component: () => import('@/views/settings/SecuritySettings.vue'),
          meta: { title: 'Security', parent: 'settings' }
        },
        // Admin settings (migrated from main AutoBot frontend - Issue #729)
        {
          path: 'admin/users',
          name: 'settings-admin-users',
          component: () => import('@/views/settings/admin/UserManagementSettings.vue'),
          meta: { title: 'User Management', parent: 'settings', admin: true }
        },
        {
          path: 'admin/cache',
          name: 'settings-admin-cache',
          component: () => import('@/views/settings/admin/CacheSettings.vue'),
          meta: { title: 'Cache Settings', parent: 'settings', admin: true }
        },
        {
          path: 'admin/prompts',
          name: 'settings-admin-prompts',
          component: () => import('@/views/settings/admin/PromptsSettings.vue'),
          meta: { title: 'Prompts', parent: 'settings', admin: true }
        },
        {
          path: 'admin/log-forwarding',
          name: 'settings-admin-log-forwarding',
          component: () => import('@/views/settings/admin/LogForwardingSettings.vue'),
          meta: { title: 'Log Forwarding', parent: 'settings', admin: true }
        },
        {
          path: 'admin/npu-workers',
          name: 'settings-admin-npu-workers',
          component: () => import('@/views/settings/admin/NPUWorkersSettings.vue'),
          meta: { title: 'NPU Workers', parent: 'settings', admin: true }
        },
        {
          // Issue #839: Config Defaults management
          path: 'admin/config-defaults',
          name: 'settings-admin-config-defaults',
          component: () => import('@/views/settings/admin/ConfigDefaultsSettings.vue'),
          meta: { title: 'Config Defaults', parent: 'settings', admin: true }
        },
      ]
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
        // Admin monitoring (migrated from main AutoBot frontend - Issue #729)
        {
          path: 'admin',
          name: 'monitoring-admin',
          component: () => import('@/views/monitoring/admin/AdminMonitoringView.vue'),
          meta: { title: 'Admin Dashboard', parent: 'monitoring', admin: true }
        },
      ]
    },
    {
      // Issue #752: Comprehensive performance monitoring
      path: '/performance',
      name: 'performance',
      component: () => import('@/views/PerformanceView.vue'),
      meta: { title: 'Performance' },
      children: [
        {
          path: '',
          name: 'performance-default',
          redirect: '/performance/overview'
        },
        {
          path: 'overview',
          name: 'performance-overview',
          component: () => import('@/views/performance/PerformanceOverview.vue'),
          meta: { title: 'Performance Overview', parent: 'performance' }
        },
        {
          path: 'traces',
          name: 'performance-traces',
          component: () => import('@/views/performance/TracingView.vue'),
          meta: { title: 'Distributed Traces', parent: 'performance' }
        },
        {
          path: 'slos',
          name: 'performance-slos',
          component: () => import('@/views/performance/SLODashboard.vue'),
          meta: { title: 'SLO Dashboard', parent: 'performance' }
        },
        {
          path: 'alerts',
          name: 'performance-alerts',
          component: () => import('@/views/performance/AlertRulesView.vue'),
          meta: { title: 'Alert Rules', parent: 'performance' }
        },
      ]
    },
    {
      // Issue #838: Service Orchestration management
      path: '/orchestration',
      name: 'orchestration',
      component: () => import('@/views/OrchestrationView.vue'),
      meta: { title: 'Orchestration' }
    },
    {
      // Issue #840: Update job tracking and checking
      path: '/updates',
      name: 'updates',
      component: () => import('@/views/UpdatesView.vue'),
      meta: { title: 'Updates' }
    },
    {
      // Issue #841: Role Registry management
      path: '/roles',
      name: 'roles',
      component: () => import('@/views/RolesView.vue'),
      meta: { title: 'Role Registry' }
    },
    {
      // Issue #731: Skills system management
      path: '/skills',
      name: 'skills',
      component: () => import('@/views/SkillsView.vue'),
      meta: { title: 'Skills' }
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
      component: () => import('@/views/tools/ToolsLayout.vue'),
      meta: { title: 'Tools' },
      children: [
        {
          path: '',
          name: 'tools-default',
          redirect: '/tools/fleet'
        },
        {
          path: 'fleet',
          name: 'tools-fleet',
          component: () => import('@/views/ToolsView.vue'),
          meta: { title: 'Fleet Tools', parent: 'tools' }
        },
        // Migrated from main AutoBot frontend - Issue #729
        {
          path: 'terminal',
          name: 'tools-terminal',
          component: () => import('@/views/tools/admin/TerminalTool.vue'),
          meta: { title: 'Terminal', parent: 'tools' }
        },
        {
          path: 'files',
          name: 'tools-files',
          component: () => import('@/views/tools/admin/FileBrowserTool.vue'),
          meta: { title: 'File Browser', parent: 'tools' }
        },
        {
          path: 'browser',
          name: 'tools-browser',
          component: () => import('@/views/tools/admin/BrowserTool.vue'),
          meta: { title: 'Browser', parent: 'tools' }
        },
        {
          path: 'novnc',
          name: 'tools-novnc',
          component: () => import('@/views/tools/admin/NoVNCTool.vue'),
          meta: { title: 'noVNC', parent: 'tools' }
        },
        {
          path: 'voice',
          name: 'tools-voice',
          component: () => import('@/views/tools/admin/VoiceTool.vue'),
          meta: { title: 'Voice', parent: 'tools' }
        },
        {
          path: 'mcp',
          name: 'tools-mcp',
          component: () => import('@/views/tools/admin/MCPTool.vue'),
          meta: { title: 'MCP Registry', parent: 'tools' }
        },
        {
          path: 'agents',
          name: 'tools-agents',
          component: () => import('@/views/tools/admin/AgentsTool.vue'),
          meta: { title: 'Agents', parent: 'tools' }
        },
        {
          path: 'vision',
          name: 'tools-vision',
          component: () => import('@/views/tools/admin/VisionTool.vue'),
          meta: { title: 'Vision', parent: 'tools' }
        },
        {
          path: 'batch',
          name: 'tools-batch',
          component: () => import('@/views/tools/admin/BatchTool.vue'),
          meta: { title: 'Batch Processing', parent: 'tools' }
        },
      ]
    },
  ]
})

// Authentication guard with admin role enforcement (Issue #729)
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

  // Check admin routes require admin role (Issue #729)
  if (to.meta.admin && !authStore.isAdmin) {
    // Redirect non-admin users to fleet overview
    next({ name: 'fleet' })
    return
  }

  next()
})

// Update document title on navigation
router.afterEach((to) => {
  document.title = `${to.meta.title || 'SLM Admin'} - Service Lifecycle Manager`
})

export default router
