import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    // Single route - let App.vue handle all navigation internally
    {
      path: '/:pathMatch(.*)*',
      name: 'app',
      component: () => import('../App.vue')
    }
  ],
})

export default router
