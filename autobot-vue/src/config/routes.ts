/**
 * Route Configuration
 * Centralized route definitions for the AutoBot application
 */

export interface RouteConfig {
  path: string
  name?: string
  component?: string
  redirectTo?: string
  description: string
  icon?: string
  requiresAuth?: boolean
  children?: RouteConfig[]
}

export const routeConfig: RouteConfig[] = [
  {
    path: '/',
    redirectTo: '/dashboard',
    description: 'Root redirect'
  },
  {
    path: '/dashboard',
    name: 'dashboard',
    component: 'DashboardView',
    description: 'Dashboard main page',
    icon: 'fas fa-tachometer-alt'
  },
  {
    path: '/chat',
    name: 'chat',
    component: 'ChatView',
    description: 'Chat interface',
    icon: 'fas fa-comments'
  },
  {
    path: '/knowledge',
    redirectTo: '/knowledge/search',
    description: 'Knowledge base',
    icon: 'fas fa-brain',
    children: [
      {
        path: '/knowledge/search',
        name: 'knowledge-search',
        component: 'KnowledgeSearch',
        description: 'Knowledge search',
        icon: 'fas fa-search'
      },
      {
        path: '/knowledge/categories',
        name: 'knowledge-categories',
        component: 'KnowledgeCategories',
        description: 'Categories management',
        icon: 'fas fa-folder-tree'
      },
      {
        path: '/knowledge/upload',
        name: 'knowledge-upload',
        component: 'KnowledgeUpload',
        description: 'Content upload',
        icon: 'fas fa-upload'
      },
      {
        path: '/knowledge/manage',
        name: 'knowledge-manage',
        component: 'KnowledgeEntries',
        description: 'Document management',
        icon: 'fas fa-file-alt'
      },
      {
        path: '/knowledge/stats',
        name: 'knowledge-stats',
        component: 'KnowledgeStats',
        description: 'Knowledge statistics',
        icon: 'fas fa-chart-bar'
      }
    ]
  },
  {
    path: '/tools',
    redirectTo: '/tools/terminal',
    description: 'Developer tools',
    icon: 'fas fa-tools',
    children: [
      {
        path: '/tools/terminal',
        name: 'tools-terminal',
        component: 'Terminal',
        description: 'Terminal interface',
        icon: 'fas fa-terminal'
      },
      {
        path: '/tools/files',
        name: 'tools-files',
        component: 'FileBrowser',
        description: 'File browser',
        icon: 'fas fa-folder-open'
      },
      {
        path: '/tools/voice',
        name: 'tools-voice',
        component: 'VoiceInterface',
        description: 'Voice interface',
        icon: 'fas fa-microphone'
      }
    ]
  },
  {
    path: '/monitoring',
    redirectTo: '/monitoring/system',
    description: 'System monitoring',
    icon: 'fas fa-desktop',
    children: [
      {
        path: '/monitoring/system',
        name: 'monitoring-system',
        component: 'SystemMonitor',
        description: 'System health',
        icon: 'fas fa-heartbeat'
      },
      {
        path: '/monitoring/analytics',
        name: 'monitoring-analytics',
        component: 'CodebaseAnalytics',
        description: 'Code analytics',
        icon: 'fas fa-chart-line'
      },
      {
        path: '/monitoring/rum',
        name: 'monitoring-rum',
        component: 'RumDashboard',
        description: 'RUM monitoring',
        icon: 'fas fa-tachometer-alt'
      },
      {
        path: '/monitoring/validation',
        name: 'monitoring-validation',
        component: 'ValidationDashboard',
        description: 'Validation dashboard',
        icon: 'fas fa-check-circle'
      }
    ]
  },
  {
    path: '/secrets',
    name: 'secrets',
    component: 'SecretsView',
    description: 'Secrets management',
    icon: 'fas fa-key',
    requiresAuth: true
  },
  {
    path: '/settings',
    name: 'settings',
    component: 'SettingsView',
    description: 'Application settings',
    icon: 'fas fa-cog'
  }
]

// Helper function to get all routes in a flat structure
export function getAllRoutes(): RouteConfig[] {
  const flatRoutes: RouteConfig[] = []
  
  function flatten(routes: RouteConfig[]) {
    routes.forEach(route => {
      flatRoutes.push(route)
      if (route.children) {
        flatten(route.children)
      }
    })
  }
  
  flatten(routeConfig)
  return flatRoutes
}

// Helper function to find a route by path
export function findRouteByPath(path: string): RouteConfig | undefined {
  return getAllRoutes().find(route => route.path === path)
}

// Helper function to get navigation menu structure
export function getNavigationMenus(): RouteConfig[] {
  return routeConfig.filter(route => !route.redirectTo && route.component)
}