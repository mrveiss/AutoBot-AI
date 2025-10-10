<template>
  <div class="services-settings p-6">
    <h3 class="text-2xl font-semibold text-gray-900 mb-6">Service Management</h3>
    <p class="text-sm text-gray-600 mb-6">
      Control critical infrastructure services running across the AutoBot distributed VM network.
    </p>

    <!-- Redis Service Control Section -->
    <div class="service-section mb-8">
      <RedisServiceControl />
    </div>

    <!-- Future service controls can be added here -->
    <div class="future-services mt-8 p-4 bg-blue-50 border border-blue-200 rounded-lg">
      <h4 class="text-sm font-semibold text-blue-900 mb-2">
        <i class="fas fa-info-circle mr-1"></i>
        Additional Services
      </h4>
      <p class="text-sm text-blue-700">
        Additional service controls (NPU Worker, AI Stack, Browser Service) will be added in future updates.
      </p>
    </div>
  </div>
</template>

<script setup>
import RedisServiceControl from '../services/RedisServiceControl.vue'
</script>

<style scoped>
.services-settings {
  min-height: 400px;
}

.service-section {
  /* Additional spacing if needed */
}
</style>
