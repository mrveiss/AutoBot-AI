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
.chat-view {
  height: calc(100vh - 80px);
}
</style>
