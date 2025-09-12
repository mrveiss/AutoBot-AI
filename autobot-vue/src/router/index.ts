import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { useAppStore } from '@/stores/useAppStore'

// Views (Page-level components)
const ChatView = () => import('@/views/ChatView.vue')
const KnowledgeView = () => import('@/views/KnowledgeView.vue')
const ToolsView = () => import('@/views/ToolsView.vue')
const MonitoringView = () => import('@/views/MonitoringView.vue')
const SecretsView = () => import('@/views/SecretsView.vue')
const SettingsView = () => import('@/views/SettingsView.vue')
const NotFoundView = () => import('@/views/NotFoundView.vue')

// Route configuration
const routes: RouteRecordRaw[] = [
  {
    path: '/',
    redirect: '/chat'
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
        component: () => import('@/components/knowledge/KnowledgeCategories.vue'),
        meta: {
          title: 'Categories',
          parent: 'knowledge'
        }
      },
      {
        path: 'upload',
        name: 'knowledge-upload',
        component: () => import('@/components/knowledge/KnowledgeUpload.vue'),
        meta: {
          title: 'Upload Content',
          parent: 'knowledge'
        }
      },
      {
        path: 'manage',
        name: 'knowledge-manage',
        component: () => import('@/components/knowledge/KnowledgeEntries.vue'),
        meta: {
          title: 'Manage Entries',
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
        name: 'knowledge-manpages',
        component: () => import('@/components/ManPageManager.vue'),
        meta: {
          title: 'Man Pages',
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
        path: 'terminal',
        name: 'tools-terminal',
        component: () => import('@/components/XTerminal.vue'),
        meta: {
          title: 'Terminal',
          parent: 'tools'
        }
      },
      {
        path: 'terminal/:sessionId',
        name: 'tools-terminal-session',
        component: () => import('@/components/XTerminal.vue'),
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
      }
    ]
  },
  {
    path: '/monitoring',
    name: 'monitoring',
    component: MonitoringView,
    meta: {
      title: 'System Monitoring',
      icon: 'fas fa-chart-line',
      description: 'System health and performance monitoring',
      requiresAuth: false
    },
    children: [
      {
        path: '',
        name: 'monitoring-default',
        component: () => import('@/components/SystemMonitor.vue'),
        meta: {
          title: 'System Monitor',
          parent: 'monitoring'
        }
      },
      {
        path: 'system',
        name: 'monitoring-system',
        component: () => import('@/components/SystemMonitor.vue'),
        meta: {
          title: 'System Monitor',
          parent: 'monitoring'
        }
      },
      {
        path: 'analytics',
        name: 'monitoring-analytics',
        component: () => import('@/components/CodebaseAnalytics.vue'),
        meta: {
          title: 'Analytics',
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
        path: 'validation',
        name: 'monitoring-validation',
        component: () => import('@/components/ValidationDashboard.vue'),
        meta: {
          title: 'Validation',
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
      }
    ]
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
    }
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
    }
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

// Global navigation guards
router.beforeEach((to, from, next) => {
  const appStore = useAppStore()
  
  console.log('[Router DEBUG] Navigating to:', to.path)
  console.log('[Router DEBUG] Route matched:', to.matched.length > 0)
  console.log('[Router DEBUG] AppStore.updateRoute type:', typeof appStore?.updateRoute)

  // Update document title
  if (to.meta.title) {
    document.title = `${to.meta.title} - AutoBot Pro`
  }

  // Update active tab in store
  if (to.name && typeof to.name === 'string') {
    const tabName = to.name.split('-')[0] // Extract main section (e.g., 'chat' from 'chat-session')
    if (['chat', 'desktop', 'knowledge', 'tools', 'monitoring', 'secrets', 'settings'].includes(tabName)) {
      appStore.updateRoute(tabName as any)
    }
  }

  // Handle authentication (if needed in future)
  if (to.meta.requiresAuth) {
    // Check authentication status
    // For now, just proceed
    next()
  } else {
    next()
  }
})

router.afterEach((to) => {
  // Track page views for analytics
  if (window.rum) {
    window.rum.trackUserInteraction('page_view', null, {
      page: to.path,
      title: to.meta.title
    })
  }
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
