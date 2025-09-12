<template>
  <div class="chat-view h-full flex flex-col">
    <!-- Chat interface container - Debugging Router -->
    <div class="p-4 bg-yellow-100 border border-yellow-400 text-yellow-800">
      <p>ChatView Component Loaded Successfully</p>
      <p>Current Route: {{ $route.path }}</p>
      <p>Route Name: {{ $route.name }}</p>
    </div>
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
