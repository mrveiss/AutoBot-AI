<template>
  <div class="settings-view">
    <!-- Settings Panel Component with sidebar layout -->
    <SettingsPanel />
  </div>
</template>

<script setup lang="ts">
// View-level component for settings layout
import SettingsPanel from '@/components/SettingsPanel.vue'
</script>

<style scoped>
/* Full height layout for sidebar navigation */
.settings-view {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
</style>
