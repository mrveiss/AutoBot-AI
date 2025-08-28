import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import TerminalWindow from './components/TerminalWindow.vue'
import MCPDashboard from './components/MCPDashboard.vue'

// Since this is a single page application, we just need basic routing
// for components that expect route parameters
const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'home',
      component: App
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
