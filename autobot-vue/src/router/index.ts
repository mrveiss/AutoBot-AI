import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { useAppStore } from '@/stores/useAppStore'
import { useUserStore } from '@/stores/useUserStore'
import { setupAsyncComponentErrorHandler } from '@/utils/asyncComponentHelpers'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('Router');

// Initialize global async component error handler
setupAsyncComponentErrorHandler()

// Views (Page-level components) - Use direct imports for simple containers to avoid circular dependencies
import ChatView from '@/views/ChatView.vue'
import KnowledgeView from '@/views/KnowledgeView.vue'
import ToolsView from '@/views/ToolsView.vue'
import MonitoringView from '@/views/MonitoringView.vue'
import SecretsView from '@/views/SecretsView.vue'
import SettingsView from '@/views/SettingsView.vue'
import InfrastructureManager from '@/views/InfrastructureManager.vue'
import AnalyticsView from '@/views/AnalyticsView.vue'
import NotFoundView from '@/views/NotFoundView.vue'

// Route configuration
const routes: RouteRecordRaw[] = [
  {
    path: '/',
    redirect: '/chat'
  },
  {
    path: '/login',
    name: 'login',
    component: () => import('@/components/auth/LoginForm.vue'),
    meta: {
      title: 'Login',
      hideInNav: true,
      requiresAuth: false
    }
  },
  {
    path: '/dashboard',
    redirect: '/monitoring'
  },
  {
    path: '/chat',
    name: 'chat',
    component: ChatView,
    meta: {
      title: 'AI Assistant',
      icon: 'fas fa-robot',
      description: 'Chat with AI assistant',
      requiresAuth: false
    },
    children: [
      {
        path: '',
        name: 'chat-default',
        component: () => import('@/components/chat/ChatInterface.vue')
      },
      {
        path: ':sessionId',
        name: 'chat-session',
        component: () => import('@/components/chat/ChatInterface.vue'),
        props: true,
        meta: {
          title: 'Chat Session',
          parent: 'chat'
        }
      }
    ]
  },
  {
    path: '/knowledge',
    name: 'knowledge',
    component: KnowledgeView,
    meta: {
      title: 'Knowledge Base',
      icon: 'fas fa-database',
      description: 'Manage knowledge and documents',
      requiresAuth: false
    },
    children: [
      {
        path: '',
        name: 'knowledge-default',
        redirect: '/knowledge/search'
      },
      {
        path: 'search',
        name: 'knowledge-search',
        component: () => import('@/components/knowledge/KnowledgeSearch.vue'),
        meta: {
          title: 'Search Knowledge',
          parent: 'knowledge'
        }
      },
      {
        path: 'categories',
        name: 'knowledge-categories',
        component: () => import('@/components/knowledge/KnowledgeBrowser.vue'),
        meta: {
          title: 'Browse Knowledge',
          parent: 'knowledge'
        }
      },
      {
        path: 'upload',
        redirect: '/knowledge/manage'
      },
      {
        path: 'manage',
        name: 'knowledge-manage',
        component: () => import('@/components/knowledge/KnowledgeEntries.vue'),
        meta: {
          title: 'Manage Knowledge',
          parent: 'knowledge'
        }
      },
      {
        path: 'stats',
        name: 'knowledge-stats',
        component: () => import('@/components/knowledge/KnowledgeStats.vue'),
        meta: {
          title: 'Statistics',
          parent: 'knowledge'
        }
      },
      {
        path: 'manpages',
        redirect: () => ({
          path: '/knowledge/categories',
          query: { view: 'system' }
        })
      },
      {
        path: 'system-knowledge',
        redirect: () => ({
          path: '/knowledge/categories',
          query: { view: 'system' }
        })
      },
      {
        path: 'browser/user',
        redirect: '/knowledge/categories'
      },
      {
        path: 'browser/autobot',
        redirect: '/knowledge/categories'
      },
      {
        path: 'graph',
        name: 'knowledge-graph',
        component: () => import('@/components/knowledge/KnowledgeGraph.vue'),
        meta: {
          title: 'Knowledge Graph',
          parent: 'knowledge'
        }
      },
      {
        path: 'maintenance',
        name: 'knowledge-maintenance',
        component: () => import('@/components/knowledge/KnowledgeMaintenance.vue'),
        meta: {
          title: 'Knowledge Maintenance',
          parent: 'knowledge'
        }
      }
    ]
  },
  {
    path: '/tools',
    name: 'tools',
    component: ToolsView,
    meta: {
      title: 'Developer Tools',
      icon: 'fas fa-tools',
      description: 'Terminal, file browser, and dev tools',
      requiresAuth: false
    },
    children: [
      {
        path: '',
        name: 'tools-default',
        redirect: '/tools/terminal'
      },
      {
        // Advanced multi-tab terminal with host switching
        // Note: Terminal.vue still exists for chat integration (see ChatTabContent.vue)
        path: 'terminal',
        name: 'tools-terminal',
        component: () => import('@/components/ToolsTerminal.vue'),
        meta: {
          title: 'Terminal',
          parent: 'tools'
        }
      },
      {
        path: 'terminal/:sessionId',
        name: 'tools-terminal-session',
        component: () => import('@/components/ToolsTerminal.vue'),
        props: true,
        meta: {
          title: 'Terminal Session',
          parent: 'tools'
        }
      },
      {
        path: 'files',
        name: 'tools-files',
        component: () => import('@/components/FileBrowser.vue'),
        meta: {
          title: 'File Browser',
          parent: 'tools'
        }
      },
      {
        path: 'browser',
        name: 'tools-browser',
        component: () => import('@/components/ToolsBrowser.vue'),
        meta: {
          title: 'Browser',
          parent: 'tools'
        }
      },
      {
        path: 'novnc',
        name: 'tools-novnc',
        component: () => import('@/components/NoVNCViewer.vue'),
        meta: {
          title: 'noVNC Remote Desktop',
          parent: 'tools'
        }
      },
      {
        path: 'voice',
        name: 'tools-voice',
        component: () => import('@/components/VoiceInterface.vue'),
        meta: {
          title: 'Voice Interface',
          parent: 'tools'
        }
      },
      {
        path: 'chat-debug',
        name: 'tools-chat-debug',
        component: () => import('@/views/ChatDebugView.vue'),
        meta: {
          title: 'Chat Debug',
          parent: 'tools'
        }
      },
      {
        path: 'mcp',
        name: 'tools-mcp',
        component: () => import('@/components/developer/MCPManager.vue'),
        meta: {
          title: 'MCP Registry',
          parent: 'tools'
        }
      },
      {
        path: 'agents',
        name: 'tools-agents',
        component: () => import('@/components/developer/AgentRegistry.vue'),
        meta: {
          title: 'Agent Registry',
          parent: 'tools'
        }
      }
    ]
  },
  {
    path: '/monitoring',
    name: 'monitoring',
    component: MonitoringView,
    meta: {
      title: 'Monitoring',
      icon: 'fas fa-chart-line',
      description: 'Prometheus, Grafana, logs and alerts',
      requiresAuth: false
    },
    children: [
      {
        path: '',
        name: 'monitoring-default',
        redirect: '/monitoring/system'
      },
      {
        path: 'system',
        name: 'monitoring-system',
        component: () => import('@/components/GrafanaSystemMonitor.vue'),
        meta: {
          title: 'System Monitor',
          parent: 'monitoring'
        }
      },
      {
        path: 'rum',
        name: 'monitoring-rum',
        component: () => import('@/components/RumDashboard.vue'),
        meta: {
          title: 'RUM Dashboard',
          parent: 'monitoring'
        }
      },
      {
        path: 'logs',
        name: 'monitoring-logs',
        component: () => import('@/components/LogViewer.vue'),
        meta: {
          title: 'Log Viewer',
          parent: 'monitoring'
        }
      },
      {
        path: 'dashboards',
        name: 'monitoring-dashboards',
        component: () => import('@/views/GrafanaDashboardsView.vue'),
        meta: {
          title: 'Grafana Dashboards',
          parent: 'monitoring'
        }
      },
      {
        path: 'operations',
        name: 'monitoring-operations',
        component: () => import('@/views/OperationsView.vue'),
        meta: {
          title: 'Operations',
          parent: 'monitoring'
        }
      }
    ]
  },
  {
    path: '/analytics',
    name: 'analytics',
    component: AnalyticsView,
    meta: {
      title: 'Analytics',
      icon: 'fas fa-chart-pie',
      description: 'Codebase analytics and business intelligence',
      requiresAuth: false
    },
    children: [
      {
        path: '',
        name: 'analytics-default',
        redirect: '/analytics/codebase'
      },
      {
        path: 'codebase',
        name: 'analytics-codebase',
        component: () => import('@/components/CodebaseAnalytics.vue'),
        meta: {
          title: 'Codebase Analytics',
          parent: 'analytics'
        }
      },
      {
        path: 'bi',
        name: 'analytics-bi',
        component: () => import('@/views/BusinessIntelligenceView.vue'),
        meta: {
          title: 'Business Intelligence',
          parent: 'analytics'
        }
      },
      {
        path: 'security',
        name: 'analytics-security',
        component: () => import('@/components/security/ThreatIntelligenceDashboard.vue'),
        meta: {
          title: 'Security Analytics',
          parent: 'analytics'
        }
      },
      {
        path: 'security/settings',
        name: 'analytics-security-settings',
        component: () => import('@/components/security/ThreatIntelligenceSettings.vue'),
        meta: {
          title: 'Threat Intelligence Settings',
          parent: 'analytics'
        }
      }
    ]
  },
  {
    path: '/infrastructure',
    name: 'infrastructure',
    component: InfrastructureManager,
    meta: {
      title: 'Infrastructure',
      icon: 'fas fa-server',
      description: 'Manage hosts and deploy configurations',
      requiresAuth: false
    }
  },
  {
    path: '/secrets',
    name: 'secrets',
    component: SecretsView,
    meta: {
      title: 'Secrets Manager',
      icon: 'fas fa-key',
      description: 'Manage API keys and secrets',
      requiresAuth: true
    },
    children: [
      {
        path: '',
        name: 'secrets-manager',
        component: () => import('@/components/SecretsManager.vue'),
        meta: {
          title: 'Secrets Manager',
          hideInNav: true
        }
      }
    ]
  },
  {
    path: '/settings',
    name: 'settings',
    component: SettingsView,
    meta: {
      title: 'Settings',
      icon: 'fas fa-cog',
      description: 'Application settings and preferences',
      requiresAuth: false
    },
    children: [
      {
        path: '',
        name: 'settings-default',
        redirect: '/settings/backend'
      },
      {
        path: 'user',
        name: 'settings-user',
        component: () => import('@/components/settings/UserManagementSettings.vue'),
        meta: {
          title: 'User Management',
          parent: 'settings'
        }
      },
      {
        path: 'chat',
        name: 'settings-chat',
        component: () => import('@/components/settings/ChatSettings.vue'),
        meta: {
          title: 'Chat Settings',
          parent: 'settings'
        }
      },
      {
        path: 'backend',
        name: 'settings-backend',
        component: () => import('@/components/settings/BackendSettings.vue'),
        meta: {
          title: 'Backend Settings',
          parent: 'settings'
        }
      },
      {
        path: 'ui',
        name: 'settings-ui',
        component: () => import('@/components/settings/UISettings.vue'),
        meta: {
          title: 'UI Settings',
          parent: 'settings'
        }
      },
      {
        path: 'logging',
        name: 'settings-logging',
        component: () => import('@/components/settings/LoggingSettings.vue'),
        meta: {
          title: 'Logging',
          parent: 'settings'
        }
      },
      {
        path: 'log-forwarding',
        name: 'settings-log-forwarding',
        component: () => import('@/components/settings/LogForwardingSettings.vue'),
        meta: {
          title: 'Log Forwarding',
          parent: 'settings'
        }
      },
      {
        path: 'cache',
        name: 'settings-cache',
        component: () => import('@/components/settings/CacheSettings.vue'),
        meta: {
          title: 'Cache',
          parent: 'settings'
        }
      },
      {
        // Redirect data-storage to infrastructure (data-storage is now a subtab)
        path: 'data-storage',
        name: 'settings-data-storage',
        redirect: '/settings/infrastructure'
      },
      {
        path: 'prompts',
        name: 'settings-prompts',
        component: () => import('@/components/settings/PromptsSettings.vue'),
        meta: {
          title: 'Prompts',
          parent: 'settings'
        }
      },
      {
        // Redirect services to infrastructure (services is now a subtab)
        path: 'services',
        name: 'settings-services',
        redirect: '/settings/infrastructure'
      },
      {
        path: 'infrastructure',
        name: 'settings-infrastructure',
        component: () => import('@/components/settings/InfrastructureSettings.vue'),
        meta: {
          title: 'Infrastructure & Updates',
          parent: 'settings'
        }
      },
      {
        path: 'developer',
        name: 'settings-developer',
        component: () => import('@/components/settings/DeveloperSettings.vue'),
        meta: {
          title: 'Developer',
          parent: 'settings'
        }
      },
      {
        path: 'permissions',
        name: 'settings-permissions',
        component: () => import('@/components/settings/PermissionSettings.vue'),
        meta: {
          title: 'Permissions',
          parent: 'settings',
          icon: 'fas fa-shield-halved',
          description: 'Claude Code-style permission system'
        }
      }
    ]
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'not-found',
    component: NotFoundView,
    meta: {
      title: 'Page Not Found',
      hideInNav: true
    }
  }
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
  scrollBehavior(to, from, savedPosition) {
    // Restore scroll position when navigating back
    if (savedPosition) {
      return savedPosition
    }
    // Scroll to top for new pages
    if (to.hash) {
      return { el: to.hash, behavior: 'smooth' }
    }
    return { top: 0, behavior: 'smooth' }
  }
})

// Enhanced error handling for routing failures
router.onError((error) => {
  logger.error('Navigation error:', error)

  // Handle chunk loading failures with enhanced error recovery
  if (error.message.includes('Loading chunk') ||
      error.message.includes('Loading CSS chunk') ||
      error.message.includes('ChunkLoadError')) {

    logger.warn('Chunk loading failed, attempting recovery...', {
      error: error.message,
      url: window.location.href,
      timestamp: new Date().toISOString()
    })

    // Track chunk loading failures
    if (window.rum) {
      window.rum.trackError('router_chunk_load_failed', {
        message: error.message,
        stack: error.stack,
        url: window.location.href,
        userAgent: navigator.userAgent,
        timestamp: new Date().toISOString()
      })
    }

    // Enhanced recovery strategy
    const handleChunkError = () => {
      const reloadAttempted = sessionStorage.getItem('chunk-reload-attempted')
      const reloadCount = parseInt(sessionStorage.getItem('chunk-reload-count') || '0', 10)

      if (!reloadAttempted && reloadCount < 2) {
        // First attempt: Try page reload
        sessionStorage.setItem('chunk-reload-attempted', 'true')
        sessionStorage.setItem('chunk-reload-count', (reloadCount + 1).toString())

        logger.debug('Attempting page reload for chunk recovery...')

        // Clear service worker cache if available
        if ('serviceWorker' in navigator) {
          navigator.serviceWorker.getRegistrations().then(registrations => {
            registrations.forEach(registration => registration.unregister())
          }).finally(() => {
            window.location.reload()
          })
        } else {
          window.location.reload()
        }
      } else {
        // Fallback: Navigate to safe route
        logger.debug('Max reload attempts reached, navigating to fallback route...')
        sessionStorage.removeItem('chunk-reload-attempted')
        sessionStorage.removeItem('chunk-reload-count')

        router.push('/chat').catch((fallbackError) => {
          logger.error('Failed to navigate to fallback route, hard redirect:', fallbackError)
          window.location.href = '/chat'
        })
      }
    }

    handleChunkError()
  } else {
    // Handle other router errors
    logger.error('Non-chunk error occurred:', error)

    if (window.rum) {
      window.rum.trackError('router_navigation_error', {
        message: error.message,
        stack: error.stack,
        url: window.location.href
      })
    }
  }
})

// Global navigation guards with enhanced error handling
router.beforeEach(async (to, from, next) => {
  try {
    const appStore = useAppStore()
    const userStore = useUserStore()

    logger.debug('Navigating to:', to.path)
    logger.debug('Route matched:', to.matched.length > 0)

    // Clear chunk reload flags on successful navigation
    if (to.matched.length > 0) {
      sessionStorage.removeItem('chunk-reload-attempted')
      sessionStorage.removeItem('chunk-reload-count')
    }

    // Initialize user store from storage if not already done
    if (!userStore.isAuthenticated) {
      userStore.initializeFromStorage()
    }

    // Check authentication requirements
    const requiresAuth = to.matched.some(record => record.meta.requiresAuth === true)

    // If route requires auth and user not authenticated, try backend check first
    // This handles single_user mode where backend auto-authenticates
    if (requiresAuth && !userStore.isAuthenticated) {
      logger.debug('Route requires auth, checking backend for auto-auth (single_user mode)')
      const backendAuthenticated = await userStore.checkAuthFromBackend()
      if (backendAuthenticated) {
        logger.debug('Backend auto-authenticated user (single_user mode)')
        // Continue to route - user is now authenticated
        next()
        return
      }
    }

    if (requiresAuth && !userStore.isAuthenticated) {
      logger.debug('Authentication required, redirecting to login')

      // Track authentication redirect
      if (window.rum) {
        window.rum.trackUserInteraction('auth_redirect', null, {
          from: from.path,
          to: to.path,
          reason: 'authentication_required'
        })
      }

      // Redirect to login with intended destination
      next({
        name: 'login',
        query: { redirect: to.fullPath }
      })
      return
    }

    // If user is authenticated and trying to access login page, redirect to dashboard
    if (to.name === 'login' && userStore.isAuthenticated) {
      logger.debug('User already authenticated, redirecting to dashboard')
      next({ path: '/dashboard' })
      return
    }

    // Check for expired tokens
    if (userStore.isAuthenticated && userStore.isTokenExpired) {
      logger.debug('Token expired, logging out user')
      userStore.logout()

      // If the route requires auth, redirect to login
      if (requiresAuth) {
        next({
          name: 'login',
          query: { redirect: to.fullPath, reason: 'token_expired' }
        })
        return
      }
    }

    // Update document title
    if (to.meta.title) {
      document.title = `${to.meta.title} - AutoBot Pro`
    }

    // Update active tab in store (with null safety)
    if (to.name && typeof to.name === 'string' && appStore && typeof appStore.updateRoute === 'function') {
      const tabName = to.name.split('-')[0] // Extract main section
      const validTabs = ['chat', 'knowledge', 'tools', 'monitoring', 'operations', 'analytics', 'infrastructure', 'secrets', 'settings'] as const
      type ValidTab = typeof validTabs[number]

      if ((validTabs as readonly string[]).includes(tabName)) {
        appStore.updateRoute(tabName as ValidTab)
      }
    }

    // Track navigation attempt
    if (window.rum) {
      window.rum.trackUserInteraction('route_navigation_start', null, {
        from: from.path,
        to: to.path,
        routeName: to.name?.toString(),
        authenticated: userStore.isAuthenticated,
        requiresAuth: requiresAuth
      })
    }

    // Continue navigation
    next()

  } catch (error: unknown) {
    logger.error('Navigation guard error:', error)

    // Issue #156 Fix: Type guard for error handling
    const errorMessage = error instanceof Error ? error.message : String(error)
    const errorStack = error instanceof Error ? error.stack : undefined

    if (window.rum) {
      window.rum.trackError('navigation_guard_error', {
        message: errorMessage,
        stack: errorStack,
        from: from.path,
        to: to.path
      })
    }

    // Even on error, continue navigation to prevent blocking
    next()
  }
})

router.afterEach((to, from) => {
  // Track successful page views for analytics
  if (window.rum) {
    window.rum.trackUserInteraction('page_view', null, {
      page: to.path,
      title: to.meta.title,
      from: from.path,
      routeName: to.name?.toString()
    })
  }

  // Log successful navigation
  logger.debug('Successfully navigated to:', to.path)
})

// Route helper functions
export const getMainRoutes = () => {
  return routes.filter(route =>
    !route.meta?.hideInNav &&
    route.path !== '/' &&
    !route.path.includes('*')
  )
}

export const getBreadcrumbs = (route: any) => {
  const breadcrumbs = []

  if (route.meta?.parent) {
    const parentRoute = routes.find(r => r.name === route.meta.parent)
    if (parentRoute) {
      breadcrumbs.push({
        name: parentRoute.meta?.title,
        path: parentRoute.path
      })
    }
  }

  breadcrumbs.push({
    name: route.meta?.title || route.name,
    path: route.path
  })

  return breadcrumbs
}

export default router
