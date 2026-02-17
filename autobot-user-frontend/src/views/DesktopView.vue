<template>
  <div class="desktop-view view-container-full">
    <DesktopInterface />
  </div>
</template>

<script setup lang="ts">
import DesktopInterface from '@/components/desktop/DesktopInterface.vue'
</script>

<style scoped>
/* View-specific styles - layout provided by .view-container-full (Issue #548) */
.desktop-view {
  @apply bg-autobot-bg-secondary;
}
</style>
