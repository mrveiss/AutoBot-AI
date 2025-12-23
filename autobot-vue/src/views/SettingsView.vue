<template>
  <div class="settings-view view-container">
    <div class="container mx-auto px-4 py-6">
      <div class="mb-6">
        <h1 class="text-3xl font-bold text-blueGray-700">Settings</h1>
        <p class="text-blueGray-600 mt-2">Application preferences and configuration</p>
      </div>

      <!-- Settings Panel Component -->
      <SettingsPanel />
    </div>
  </div>
</template>

<script setup lang="ts">
// View-level component for settings layout
import SettingsPanel from '@/components/SettingsPanel.vue'
</script>

<style scoped>
/* View-specific styles only - scroll styling provided by .view-container (Issue #548) */
</style>
