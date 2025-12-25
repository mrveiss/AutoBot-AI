<template>
  <div class="settings-view view-container">
    <div class="container mx-auto px-4 pt-4 pb-6">
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
