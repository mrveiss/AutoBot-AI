<template>
  <div class="monitoring-view view-container">
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
          <router-link
            to="/monitoring/dashboards"
            class="px-3 py-2 text-sm font-medium border-b-2 transition-colors"
            :class="$route.name === 'monitoring-dashboards' ? 'border-indigo-500 text-indigo-600' : 'border-transparent text-blueGray-500 hover:text-blueGray-700 hover:border-blueGray-300'"
          >
            <i class="fas fa-tachometer-alt mr-2"></i>Dashboards
          </router-link>
          <router-link
            to="/monitoring/operations"
            class="px-3 py-2 text-sm font-medium border-b-2 transition-colors"
            :class="$route.name === 'monitoring-operations' ? 'border-indigo-500 text-indigo-600' : 'border-transparent text-blueGray-500 hover:text-blueGray-700 hover:border-blueGray-300'"
          >
            <i class="fas fa-tasks mr-2"></i>Operations
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
/* View-specific styles only - scroll styling provided by .view-container (Issue #548) */
</style>
