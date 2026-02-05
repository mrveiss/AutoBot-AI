<template>
  <div class="analytics-view view-container">
    <div class="w-full px-4 pt-4 pb-6">
      <!-- Sub-navigation for analytics sections -->
      <div class="mb-6">
        <nav class="flex space-x-4 border-b border-blueGray-200">
          <router-link
            to="/analytics/codebase"
            class="px-3 py-2 text-sm font-medium border-b-2 transition-colors"
            :class="isCodebaseActive ? 'border-teal-500 text-teal-600' : 'border-transparent text-blueGray-500 hover:text-blueGray-700 hover:border-blueGray-300'"
          >
            <i class="fas fa-code mr-2"></i>Codebase Analytics
          </router-link>
          <router-link
            to="/analytics/bi"
            class="px-3 py-2 text-sm font-medium border-b-2 transition-colors"
            :class="isBIActive ? 'border-teal-500 text-teal-600' : 'border-transparent text-blueGray-500 hover:text-blueGray-700 hover:border-blueGray-300'"
          >
            <i class="fas fa-chart-line mr-2"></i>Business Intelligence
          </router-link>
          <router-link
            to="/analytics/security"
            class="px-3 py-2 text-sm font-medium border-b-2 transition-colors"
            :class="isSecurityActive ? 'border-teal-500 text-teal-600' : 'border-transparent text-blueGray-500 hover:text-blueGray-700 hover:border-blueGray-300'"
          >
            <i class="fas fa-shield-alt mr-2"></i>Security
          </router-link>
        </nav>
      </div>

      <!-- Router View for Child Components -->
      <router-view />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()

const isCodebaseActive = computed(() => {
  return route.path === '/analytics' || route.path === '/analytics/codebase' || route.path.startsWith('/analytics/codebase/')
})

const isBIActive = computed(() => {
  return route.path === '/analytics/bi' || route.path.startsWith('/analytics/bi/')
})

const isSecurityActive = computed(() => {
  return route.path === '/analytics/security' || route.path.startsWith('/analytics/security/')
})
</script>

<style scoped>
/* View-specific styles only - scroll styling provided by .view-container (Issue #548) */
</style>
