import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import TerminalWindow from './components/TerminalWindow.vue'

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
