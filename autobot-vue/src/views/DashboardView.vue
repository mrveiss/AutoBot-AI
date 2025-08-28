<template>
  <div class="dashboard-view">
    <div class="container mx-auto px-4 py-6">
      <div class="mb-6">
        <h1 class="text-3xl font-bold text-blueGray-700">Dashboard</h1>
        <p class="text-blueGray-600 mt-2">System overview and performance metrics</p>
      </div>

      <!-- Main Dashboard Component -->
      <DashboardOverview />
    </div>
  </div>
</template>

<script setup lang="ts">
import DashboardOverview from '@/components/DashboardOverview.vue'
</script>

<style scoped>
.dashboard-view {
  min-height: calc(100vh - 80px);
}
</style>
