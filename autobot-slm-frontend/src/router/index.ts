// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Vue Router Configuration
 *
 * Handles routing and authentication guards.
 */

import { createRouter, createWebHistory } from 'vue-router'
import axios from 'axios'
import { useAuthStore } from '@/stores/auth'
import { getSlmApiBase } from '@/config/ssot-config'

// One-time wizard completion check (Issue #1294)
let wizardCheckDone = false

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/LoginView.vue'),
      meta: { title: 'Login', requiresAuth: false }
    },
    {
      // Issue #576: SSO callback handler for OAuth2/SAML redirects
      path: '/sso-callback',
      name: 'sso-callback',
      component: () => import('@/views/SSOCallbackView.vue'),
      meta: { title: 'SSO Login', requiresAuth: false },
    },
    {
      // Issue #1294: Setup wizard — guided first-run fleet configuration
      path: '/setup',
      name: 'setup',
      component: () => import('@/views/SetupWizardView.vue'),
      meta: { title: 'Setup Wizard' }
    },
    {
      path: '/',
      redirect: '/fleet'
    },
    {
      path: '/fleet/:tab?',
      name: 'fleet',
      component: () => import('@/views/FleetOverview.vue'),
      meta: { title: 'Fleet Overview' },
      beforeEnter: (to) => {
        if (!to.params.tab) {
          return { name: 'fleet', params: { tab: 'nodes' }, replace: true }
        }
      },
    },
    {
      // Issue #4762: Wire ServicesView as direct route (was redirect to /orchestration/per-node)
      path: '/services',
      name: 'services',
      component: () => import('@/views/ServicesView.vue'),
      meta: { title: 'Services' }
    },
    {
      path: '/deployments/:tab?',
      name: 'deployments',
      component: () => import('@/views/DeploymentsView.vue'),
      meta: { title: 'Deployments' },
      beforeEnter: (to) => {
        if (!to.params.tab) {
          return { name: 'deployments', params: { tab: 'standard' }, replace: true }
        }
      },
    },
    {
      path: '/backups/:tab?',
      name: 'backups',
      component: () => import('@/views/BackupsView.vue'),
      meta: { title: 'Backups' },
      beforeEnter: (to) => {
        if (!to.params.tab) {
          return { name: 'backups', params: { tab: 'backups' }, replace: true }
        }
      },
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
      meta: { title: 'Maintenance' },
      children: [
        // Issue #840, #1230: Updates tabs — moved from standalone /updates into maintenance
        {
          path: 'updates',
          name: 'maintenance-updates',
          redirect: { name: 'maintenance-updates-tab', params: { tab: 'system' } },
        },
        {
          path: 'updates/:tab',
          name: 'maintenance-updates-tab',
          component: () => import('@/views/UpdatesView.vue'),
          meta: { title: 'Updates', parent: 'maintenance' }
        },
      ]
    },
    {
      // Issue #741: Code sync — backwards compat redirect
      path: '/code-sync',
      redirect: '/maintenance/updates/code-sync',
    },
    {
      // Issue #760: Agent management - local + external agents
      path: '/agents/:tab?',
      name: 'agents',
      component: () => import('@/views/AgentsView.vue'),
      meta: { title: 'Agents' },
      beforeEnter: (to) => {
        if (!to.params.tab) {
          return { name: 'agents', params: { tab: 'local-agents' }, replace: true }
        }
      },
    },
    {
      path: '/agent-config',
      redirect: '/agents/local-agents',
    },
    {
      // Issue #786: Infrastructure moved to Fleet Overview infrastructure tab
      path: '/infrastructure',
      redirect: '/fleet/infrastructure',
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
          // Issue #4705: Wire InfrastructureSettings view into settings router
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
          // Issue #964: Personality profile management
          path: 'admin/personality',
          name: 'settings-admin-personality',
          component: () => import('@/views/settings/admin/PersonalitySettings.vue'),
          meta: { title: 'Personality', parent: 'settings', admin: true }
        },
        {
          // Issue #1417: System Secrets Management
          path: 'admin/secrets',
          name: 'settings-admin-secrets',
          component: () => import('@/views/settings/admin/SecretsSettings.vue'),
          meta: { title: 'System Secrets', parent: 'settings', admin: true }
        },
        {
          path: 'admin/log-forwarding',
          name: 'settings-admin-log-forwarding',
          component: () => import('@/views/settings/admin/LogForwardingSettings.vue'),
          meta: { title: 'Log Forwarding', parent: 'settings', admin: true }
        },
        {
          // Consolidated to Fleet Overview /fleet/npu Worker Registry sub-tab
          path: 'admin/npu-workers',
          name: 'settings-admin-npu-workers',
          redirect: '/fleet/npu',
          meta: { title: 'NPU Workers', parent: 'settings', admin: true }
        },
        {
          // Issue #839: Config Defaults management
          path: 'admin/config-defaults',
          name: 'settings-admin-config-defaults',
          component: () => import('@/views/settings/admin/ConfigDefaultsSettings.vue'),
          meta: { title: 'Config Defaults', parent: 'settings', admin: true }
        },
        {
          // Issue #2371: LLM configuration moved from main frontend to SLM admin
          path: 'admin/llm',
          name: 'settings-admin-llm',
          component: () => import('@/views/settings/admin/LLMSettings.vue'),
          meta: { title: 'LLM Configuration', parent: 'settings', admin: true }
        },
        {
          // MVA-1735: SSO/OIDC provider configuration
          path: 'admin/sso',
          name: 'settings-admin-sso',
          component: () => import('@/views/settings/admin/SSOSettings.vue'),
          meta: { title: 'SSO / OIDC', parent: 'settings', admin: true }
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
        // Issue #752: Performance — moved from standalone /performance into monitoring
        {
          path: 'performance',
          name: 'monitoring-performance',
          component: () => import('@/views/PerformanceView.vue'),
          meta: { title: 'Performance', parent: 'monitoring' }
        },
        {
          path: 'performance/overview',
          name: 'monitoring-performance-overview',
          component: () => import('@/views/performance/PerformanceOverview.vue'),
          meta: { title: 'Performance Overview', parent: 'monitoring' }
        },
        {
          path: 'performance/traces',
          name: 'monitoring-performance-traces',
          component: () => import('@/views/performance/TracingView.vue'),
          meta: { title: 'Distributed Traces', parent: 'monitoring' }
        },
        {
          path: 'performance/slos',
          name: 'monitoring-performance-slos',
          component: () => import('@/views/performance/SLODashboard.vue'),
          meta: { title: 'SLO Dashboard', parent: 'monitoring' }
        },
        {
          path: 'performance/alerts',
          name: 'monitoring-performance-alerts',
          component: () => import('@/views/performance/AlertRulesView.vue'),
          meta: { title: 'Alert Rules', parent: 'monitoring' }
        },
      ]
    },
    {
      // Issue #838: Service Orchestration management
      // Issue #924: tab subroutes via :tab? param
      path: '/orchestration/:tab?',
      name: 'orchestration',
      component: () => import('@/views/OrchestrationView.vue'),
      meta: { title: 'Orchestration' },
      beforeEnter: (to) => {
        if (!to.params.tab) {
          return { name: 'orchestration', params: { tab: 'per-node' }, replace: true }
        }
      },
    },
    {
      // Issue #841/#1129: Role Registry — standalone CRUD view (wired via #4706)
      path: '/roles',
      name: 'roles',
      component: () => import('@/views/RolesView.vue'),
      meta: { title: 'Role Registry' }
    },
    {
      // Issue #731: Skills system management
      path: '/skills/:tab?',
      name: 'skills',
      component: () => import('@/views/SkillsView.vue'),
      meta: { title: 'Skills' },
      beforeEnter: (to) => {
        if (!to.params.tab) {
          return { name: 'skills', params: { tab: 'active' }, replace: true }
        }
      },
    },
    {
      // Issue #963: External agents moved to /agents/external-agents
      path: '/external-agents',
      redirect: '/agents/external-agents',
    },
    {
      path: '/security/:tab?',
      name: 'security',
      component: () => import('@/views/SecurityView.vue'),
      meta: { title: 'Security Analytics' },
      beforeEnter: (to) => {
        if (!to.params.tab) {
          return { name: 'security', params: { tab: 'overview' }, replace: true }
        }
      },
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
          meta: { title: 'Terminal', parent: 'tools', admin: true }
        },
        {
          path: 'files',
          name: 'tools-files',
          component: () => import('@/views/tools/admin/FileBrowserTool.vue'),
          meta: { title: 'File Browser', parent: 'tools', admin: true }
        },
        {
          path: 'browser',
          name: 'tools-browser',
          component: () => import('@/views/tools/admin/BrowserTool.vue'),
          meta: { title: 'Browser', parent: 'tools', admin: true }
        },
        {
          path: 'novnc',
          name: 'tools-novnc',
          component: () => import('@/views/tools/admin/NoVNCTool.vue'),
          meta: { title: 'noVNC', parent: 'tools', admin: true }
        },
        {
          path: 'voice',
          name: 'tools-voice',
          component: () => import('@/views/tools/admin/VoiceTool.vue'),
          meta: { title: 'Voice', parent: 'tools', admin: true }
        },
        {
          path: 'mcp',
          name: 'tools-mcp',
          component: () => import('@/views/tools/admin/MCPTool.vue'),
          meta: { title: 'MCP Registry', parent: 'tools', admin: true }
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
// Issue #2676: Migrated from next() callback to return-value pattern (vue-router v5)
router.beforeEach(async (to, _from) => {
  const authStore = useAuthStore()

  // Public routes don't need auth (requiresAuth: false)
  if (to.meta.requiresAuth === false) {
    // If already authenticated, redirect to home
    if (authStore.isAuthenticated && to.name === 'login') {
      return { name: 'fleet' }
    }
    return
  }

  // Check if authenticated
  if (!authStore.isAuthenticated) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }

  // Verify token is still valid
  const isValid = await authStore.checkAuth()
  if (!isValid) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }

  // Check admin routes require admin role (Issue #729)
  if (to.meta.admin && !authStore.isAdmin) {
    // Redirect non-admin users to fleet overview
    return { name: 'fleet' }
  }

  // First-run wizard redirect (Issue #1294)
  // Check once per session if the setup wizard has been completed
  if (!wizardCheckDone && to.name !== 'setup') {
    wizardCheckDone = true
    try {
      const token = sessionStorage.getItem('slm_access_token')
      const { data } = await axios.get(`${getSlmApiBase()}/setup/status`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!data.completed) {
        return { name: 'setup' }
      }
    } catch {
      // If setup endpoint fails, skip redirect (endpoint may not exist)
    }
  }

  // Continue navigation (returning undefined allows navigation to proceed)
})

// Update document title on navigation
router.afterEach((to) => {
  document.title = `${to.meta.title || 'SLM Admin'} - Service Lifecycle Manager`
})

export default router
