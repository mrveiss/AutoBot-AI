<template>
  <div class="chat-view h-full flex flex-col">
    <!-- Main chat interface container -->
    <router-view class="flex-1 min-h-0" />
  </div>
</template>

<script setup lang="ts">
// View-level component for chat layout
</script>

<style scoped>
/* CRITICAL FIX: Remove conflicting height calculation */
/* App.vue already handles header height in its flex layout */
/* Using h-full class to inherit full height from parent flex container */
.chat-view {
  /* REMOVED: height: calc(100vh - 64px); - This conflicted with App.vue flex layout */
  /* Now relies on parent flex container for proper height calculation */
}
</style>