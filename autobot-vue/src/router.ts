import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import TerminalWindow from './components/TerminalWindow.vue'
import MCPDashboard from './components/MCPDashboard.vue'

// Import view components
import DashboardView from './views/DashboardView.vue'
import ChatView from './views/ChatView.vue'
import KnowledgeView from './views/KnowledgeView.vue'
import ToolsView from './views/ToolsView.vue'
import MonitoringView from './views/MonitoringView.vue'
import SettingsView from './views/SettingsView.vue'
import SecretsView from './views/SecretsView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'home',
      redirect: '/dashboard'
    },
    {
      path: '/dashboard',
      name: 'dashboard',
      component: DashboardView
    },
    {
      path: '/chat',
      name: 'chat',
      component: ChatView
    },
    {
      path: '/knowledge',
      name: 'knowledge',
      component: KnowledgeView
    },
    {
      path: '/tools',
      name: 'tools',
      component: ToolsView
    },
    {
      path: '/monitoring',
      name: 'monitoring',
      component: MonitoringView
    },
    {
      path: '/settings',
      name: 'settings',
      component: SettingsView
    },
    {
      path: '/secrets',
      name: 'secrets',
      component: SecretsView
    },
    {
      path: '/terminal/:sessionId?',
      name: 'terminal',
      component: TerminalWindow,
      props: true
    },
    {
      path: '/mcp-dashboard',
      name: 'mcp-dashboard',
      component: MCPDashboard
    }
  ]
})

export default router
