<template>
  <div class="desktop-view h-full">
    <DesktopInterface />
  </div>
</template>

<script setup lang="ts">
import DesktopInterface from '@/components/desktop/DesktopInterface.vue'
</script>

<style scoped>
.desktop-view {
  @apply bg-gray-50 overflow-hidden;
}
</style>