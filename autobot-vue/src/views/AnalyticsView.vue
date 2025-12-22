<template>
  <div class="analytics-view">
    <div class="container mx-auto px-4 py-6">
      <div class="mb-6">
        <h1 class="text-3xl font-bold text-blueGray-700">Analytics</h1>
        <p class="text-blueGray-600 mt-2">Codebase metrics and business intelligence</p>
      </div>

      <!-- Sub-navigation for analytics sections -->
      <div class="mb-6">
        <nav class="flex space-x-4 border-b border-blueGray-200">
          <router-link
            to="/analytics/codebase"
            class="px-3 py-2 text-sm font-medium border-b-2 transition-colors"
            :class="isCodebaseActive ? 'border-indigo-500 text-indigo-600' : 'border-transparent text-blueGray-500 hover:text-blueGray-700 hover:border-blueGray-300'"
          >
            <i class="fas fa-code mr-2"></i>Codebase Analytics
          </router-link>
          <router-link
            to="/analytics/bi"
            class="px-3 py-2 text-sm font-medium border-b-2 transition-colors"
            :class="isBIActive ? 'border-indigo-500 text-indigo-600' : 'border-transparent text-blueGray-500 hover:text-blueGray-700 hover:border-blueGray-300'"
          >
            <i class="fas fa-chart-line mr-2"></i>Business Intelligence
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
</script>

<style scoped>
.analytics-view {
  min-height: calc(100vh - 80px);
  max-height: calc(100vh - 80px);
  overflow-y: auto;
  overflow-x: hidden;
  scroll-behavior: smooth;
}

/* Custom scrollbar styling for better UX */
.analytics-view::-webkit-scrollbar {
  width: 8px;
}

.analytics-view::-webkit-scrollbar-track {
  background: #f1f1f1;
}

.analytics-view::-webkit-scrollbar-thumb {
  background: #888;
  border-radius: 4px;
}

.analytics-view::-webkit-scrollbar-thumb:hover {
  background: #555;
}
</style>
