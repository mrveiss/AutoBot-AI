import { createRouter, createWebHistory, defineAsyncComponent } from 'vue-router'
import App from './App.vue'
// Issue #4003: Lazy-load TerminalWindow (2261 lines) to reduce initial bundle parse time
const TerminalWindow = defineAsyncComponent(() => import('./components/terminal/TerminalWindow.vue'))

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
    }
  ]
})

export default router
