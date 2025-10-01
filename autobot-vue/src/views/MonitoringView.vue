<template>
  <div class="monitoring-view">
    <div class="container mx-auto px-4 py-6">
      <div class="mb-6">
        <h1 class="text-3xl font-bold text-blueGray-700">System Monitoring</h1>
        <p class="text-blueGray-600 mt-2">Performance metrics, analytics, and system health</p>
      </div>

      <!-- Sub-navigation for monitoring sections -->
      <div class="mb-6">
        <nav class="flex space-x-4 border-b border-blueGray-200">
          <router-link
            to="/monitoring/system"
            class="px-3 py-2 text-sm font-medium border-b-2 transition-colors"
            :class="$route.name === 'monitoring-system' ? 'border-indigo-500 text-indigo-600' : 'border-transparent text-blueGray-500 hover:text-blueGray-700 hover:border-blueGray-300'"
          >
            <i class="fas fa-server mr-2"></i>System
          </router-link>
          <router-link
            to="/monitoring/analytics"
            class="px-3 py-2 text-sm font-medium border-b-2 transition-colors"
            :class="$route.name === 'monitoring-analytics' ? 'border-indigo-500 text-indigo-600' : 'border-transparent text-blueGray-500 hover:text-blueGray-700 hover:border-blueGray-300'"
          >
            <i class="fas fa-chart-line mr-2"></i>Analytics
          </router-link>
          <router-link
            to="/monitoring/rum"
            class="px-3 py-2 text-sm font-medium border-b-2 transition-colors"
            :class="$route.name === 'monitoring-rum' ? 'border-indigo-500 text-indigo-600' : 'border-transparent text-blueGray-500 hover:text-blueGray-700 hover:border-blueGray-300'"
          >
            <i class="fas fa-users mr-2"></i>RUM
          </router-link>
          <router-link
            to="/monitoring/validation"
            class="px-3 py-2 text-sm font-medium border-b-2 transition-colors"
            :class="$route.name === 'monitoring-validation' ? 'border-indigo-500 text-indigo-600' : 'border-transparent text-blueGray-500 hover:text-blueGray-700 hover:border-blueGray-300'"
          >
            <i class="fas fa-check-circle mr-2"></i>Validation
          </router-link>
          <router-link
            to="/monitoring/logs"
            class="px-3 py-2 text-sm font-medium border-b-2 transition-colors"
            :class="$route.name === 'monitoring-logs' ? 'border-indigo-500 text-indigo-600' : 'border-transparent text-blueGray-500 hover:text-blueGray-700 hover:border-blueGray-300'"
          >
            <i class="fas fa-file-alt mr-2"></i>Logs
          </router-link>
        </nav>
      </div>

      <!-- Monitoring component content -->
      <router-view />
    </div>
  </div>
</template>

<script setup lang="ts">
// View-level component for monitoring layout
</script>

<style scoped>
.monitoring-view {
  min-height: calc(100vh - 80px);
  max-height: calc(100vh - 80px);
  overflow-y: auto;
  overflow-x: hidden;
  scroll-behavior: smooth;
}

/* Custom scrollbar styling for better UX */
.monitoring-view::-webkit-scrollbar {
  width: 8px;
}

.monitoring-view::-webkit-scrollbar-track {
  background: #f1f1f1;
}

.monitoring-view::-webkit-scrollbar-thumb {
  background: #888;
  border-radius: 4px;
}

.monitoring-view::-webkit-scrollbar-thumb:hover {
  background: #555;
}
</style>
